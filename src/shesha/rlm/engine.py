"""RLM engine - the core REPL+LLM loop."""

import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from shesha.llm.client import LLMClient
from shesha.models import QueryContext
from shesha.rlm.prompts import (
    SUBCALL_PROMPT_TEMPLATE,
    build_subcall_prompt,
    build_system_prompt,
    wrap_repl_output,
)
from shesha.rlm.trace import StepType, TokenUsage, Trace
from shesha.rlm.trace_writer import TraceWriter
from shesha.sandbox.executor import ContainerExecutor
from shesha.storage.filesystem import FilesystemStorage

# Callback type for progress notifications
ProgressCallback = Callable[[StepType, int, str], None]


@dataclass
class QueryResult:
    """Result of an RLM query."""

    answer: str
    trace: Trace
    token_usage: TokenUsage
    execution_time: float


def extract_code_blocks(text: str) -> list[str]:
    """Extract code from ```repl or ```python blocks."""
    pattern = r"```(?:repl|python)\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


class RLMEngine:
    """The RLM engine - runs the REPL+LLM loop."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_iterations: int = 20,
        max_output_chars: int = 50000,
        execution_timeout: int = 30,
        max_subcall_content_chars: int = 500_000,
    ) -> None:
        """Initialize the RLM engine."""
        self.model = model
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.max_output_chars = max_output_chars
        self.execution_timeout = execution_timeout
        self.max_subcall_content_chars = max_subcall_content_chars

    def _handle_llm_query(
        self,
        instruction: str,
        content: str,
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Handle a sub-LLM query from the sandbox."""
        # Record the request
        step_content = f"instruction: {instruction}\ncontent: [{len(content)} chars]"
        trace.add_step(
            type=StepType.SUBCALL_REQUEST,
            content=step_content,
            iteration=iteration,
        )
        if on_progress:
            on_progress(StepType.SUBCALL_REQUEST, iteration, step_content)

        # Check content size limit
        if len(content) > self.max_subcall_content_chars:
            error_msg = (
                f"Error: Content size ({len(content):,} chars) exceeds the sub-LLM limit "
                f"of {self.max_subcall_content_chars:,} chars. Please chunk the content "
                f"into smaller pieces and make multiple llm_query calls."
            )
            trace.add_step(
                type=StepType.SUBCALL_RESPONSE,
                content=error_msg,
                iteration=iteration,
            )
            if on_progress:
                on_progress(StepType.SUBCALL_RESPONSE, iteration, error_msg)
            return error_msg

        # Build prompt and call LLM
        prompt = build_subcall_prompt(instruction, content)
        sub_llm = LLMClient(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])

        # Track tokens
        token_usage.prompt_tokens += response.prompt_tokens
        token_usage.completion_tokens += response.completion_tokens

        # Record the response
        trace.add_step(
            type=StepType.SUBCALL_RESPONSE,
            content=response.content,
            iteration=iteration,
            tokens_used=response.total_tokens,
        )
        if on_progress:
            on_progress(StepType.SUBCALL_RESPONSE, iteration, response.content)

        return response.content

    def query(
        self,
        documents: list[str],
        question: str,
        doc_names: list[str] | None = None,
        on_progress: ProgressCallback | None = None,
        storage: FilesystemStorage | None = None,
        project_id: str | None = None,
    ) -> QueryResult:
        """Run an RLM query against documents."""
        start_time = time.time()
        trace = Trace()
        token_usage = TokenUsage()

        if doc_names is None:
            doc_names = [f"doc_{i}" for i in range(len(documents))]

        # Build system prompt with per-document sizes
        doc_sizes = [len(d) for d in documents]
        total_chars = sum(doc_sizes)
        system_prompt = build_system_prompt(
            doc_count=len(documents),
            total_chars=total_chars,
            doc_names=doc_names,
            doc_sizes=doc_sizes,
        )

        # Helper to write trace
        def _write_trace(result: QueryResult, status: str) -> None:
            if storage is not None and project_id is not None:
                trace_id = str(uuid.uuid4())
                context = QueryContext(
                    trace_id=trace_id,
                    question=question,
                    document_ids=doc_names or [f"doc_{i}" for i in range(len(documents))],
                    model=self.model,
                    system_prompt=system_prompt,
                    subcall_prompt=SUBCALL_PROMPT_TEMPLATE,
                )
                writer = TraceWriter(storage)
                writer.write_trace(
                    project_id=project_id,
                    trace=result.trace,
                    context=context,
                    answer=result.answer,
                    token_usage=result.token_usage,
                    execution_time=result.execution_time,
                    status=status,
                )
                writer.cleanup_old_traces(project_id)

        # Initialize LLM client
        llm = LLMClient(model=self.model, system_prompt=system_prompt, api_key=self.api_key)

        # Initialize conversation
        messages: list[dict[str, str]] = [{"role": "user", "content": question}]

        # Track current iteration for llm_query callback
        current_iteration = 0

        # Create executor with callback for llm_query
        def llm_query_callback(instruction: str, content: str) -> str:
            return self._handle_llm_query(
                instruction, content, trace, token_usage, current_iteration, on_progress
            )

        executor = ContainerExecutor(llm_query_handler=llm_query_callback)
        executor.start()

        try:
            # Set up context in sandbox
            executor.setup_context(documents)

            for iteration in range(self.max_iterations):
                current_iteration = iteration
                # Get LLM response
                response = llm.complete(messages=messages)
                token_usage.prompt_tokens += response.prompt_tokens
                token_usage.completion_tokens += response.completion_tokens

                trace.add_step(
                    type=StepType.CODE_GENERATED,
                    content=response.content,
                    iteration=iteration,
                    tokens_used=response.total_tokens,
                )
                if on_progress:
                    on_progress(StepType.CODE_GENERATED, iteration, response.content)

                # Extract code blocks
                code_blocks = extract_code_blocks(response.content)
                if not code_blocks:
                    # No code - add assistant response and prompt for code
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your response must contain a ```repl block with Python code. "
                                "Write code now to explore the documents."
                            ),
                        }
                    )
                    continue

                # Execute code blocks
                all_output = []
                final_answer = None

                for code in code_blocks:
                    exec_start = time.time()
                    result = executor.execute(code, timeout=self.execution_timeout)
                    exec_duration = int((time.time() - exec_start) * 1000)

                    output_parts = []
                    if result.stdout:
                        output_parts.append(result.stdout)
                    if result.stderr:
                        output_parts.append(f"STDERR: {result.stderr}")
                    if result.error:
                        output_parts.append(f"ERROR: {result.error}")

                    output = "\n".join(output_parts) if output_parts else "(no output)"

                    trace.add_step(
                        type=StepType.CODE_OUTPUT,
                        content=output,
                        iteration=iteration,
                        duration_ms=exec_duration,
                    )
                    if on_progress:
                        on_progress(StepType.CODE_OUTPUT, iteration, output)

                    all_output.append(output)

                    # Check for final answer
                    if result.final_answer:
                        final_answer = result.final_answer
                        trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=final_answer,
                            iteration=iteration,
                        )
                        if on_progress:
                            on_progress(StepType.FINAL_ANSWER, iteration, final_answer)
                        break

                if final_answer:
                    query_result = QueryResult(
                        answer=final_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                    )
                    _write_trace(query_result, "success")
                    return query_result

                # Add output to conversation
                combined_output = "\n\n".join(all_output)
                wrapped_output = wrap_repl_output(combined_output, self.max_output_chars)

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": wrapped_output})

            # Max iterations reached
            query_result = QueryResult(
                answer="[Max iterations reached without final answer]",
                trace=trace,
                token_usage=token_usage,
                execution_time=time.time() - start_time,
            )
            _write_trace(query_result, "max_iterations")
            return query_result

        finally:
            executor.stop()
