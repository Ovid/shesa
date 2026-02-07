"""RLM engine - the core REPL+LLM loop."""

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shesha.llm.client import LLMClient
from shesha.models import QueryContext
from shesha.prompts import PromptLoader
from shesha.rlm.prompts import MAX_SUBCALL_CHARS, wrap_repl_output, wrap_subcall_content
from shesha.rlm.semantic_verification import (
    SemanticVerificationReport,
    detect_content_type,
    gather_cited_documents,
    parse_verification_response,
)
from shesha.rlm.trace import StepType, TokenUsage, Trace, TraceStep
from shesha.rlm.trace_writer import IncrementalTraceWriter, TraceWriter
from shesha.rlm.verification import (
    VerificationResult,
    build_verification_code,
    parse_verification_output,
)
from shesha.sandbox.executor import ContainerExecutor, SubcallContentError
from shesha.sandbox.pool import ContainerPool
from shesha.storage.base import StorageBackend

# Callback type for progress notifications
ProgressCallback = Callable[[StepType, int, str], None]


@dataclass
class QueryResult:
    """Result of an RLM query."""

    answer: str
    trace: Trace
    token_usage: TokenUsage
    execution_time: float
    verification: VerificationResult | None = field(default=None)
    semantic_verification: SemanticVerificationReport | None = field(default=None)


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
        prompts_dir: Path | None = None,
        pool: ContainerPool | None = None,
        max_traces_per_project: int = 50,
        verify_citations: bool = True,
        verify: bool = False,
    ) -> None:
        """Initialize the RLM engine."""
        self.model = model
        self.api_key = api_key
        self.max_iterations = max_iterations
        self.max_output_chars = max_output_chars
        self.execution_timeout = execution_timeout
        self.max_subcall_content_chars = max_subcall_content_chars
        self.prompt_loader = PromptLoader(prompts_dir)
        self._pool = pool
        self.max_traces_per_project = max_traces_per_project
        self.verify_citations = verify_citations
        self.verify = verify

    def _handle_llm_query(
        self,
        instruction: str,
        content: str,
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
        on_step: Callable[[TraceStep], None] | None = None,
    ) -> str:
        """Handle a sub-LLM query from the sandbox."""
        # Record the request
        step_content = f"instruction: {instruction}\ncontent: [{len(content)} chars]"
        step = trace.add_step(
            type=StepType.SUBCALL_REQUEST,
            content=step_content,
            iteration=iteration,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(StepType.SUBCALL_REQUEST, iteration, step_content)

        # Check content size limit
        if len(content) > self.max_subcall_content_chars:
            error_msg = (
                f"Content size ({len(content):,} chars) exceeds the sub-LLM limit "
                f"of {self.max_subcall_content_chars:,} chars. Please chunk the content "
                f"into smaller pieces and make multiple llm_query calls."
            )
            step = trace.add_step(
                type=StepType.SUBCALL_RESPONSE,
                content=error_msg,
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(StepType.SUBCALL_RESPONSE, iteration, error_msg)
            raise SubcallContentError(error_msg)

        # Wrap content in untrusted tags (code-level security boundary)
        wrapped_content = wrap_subcall_content(content)

        # Build prompt and call LLM
        prompt = self.prompt_loader.render_subcall_prompt(instruction, wrapped_content)
        sub_llm = LLMClient(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])

        # Track tokens
        token_usage.prompt_tokens += response.prompt_tokens
        token_usage.completion_tokens += response.completion_tokens

        # Record the response
        step = trace.add_step(
            type=StepType.SUBCALL_RESPONSE,
            content=response.content,
            iteration=iteration,
            tokens_used=response.total_tokens,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(StepType.SUBCALL_RESPONSE, iteration, response.content)

        return response.content

    def _run_semantic_verification(
        self,
        final_answer: str,
        documents: list[str],
        doc_names: list[str],
        trace: Trace,
        token_usage: TokenUsage,
        iteration: int,
        on_progress: ProgressCallback | None = None,
        on_step: Callable[[TraceStep], None] | None = None,
    ) -> SemanticVerificationReport | None:
        """Run semantic verification on the final answer.

        Returns SemanticVerificationReport or None if verification fails.
        """
        # Gather cited documents
        cited_docs_text = gather_cited_documents(final_answer, documents, doc_names)
        if not cited_docs_text:
            return None

        # Layer 1: Adversarial verification
        prompt = self.prompt_loader.render_verify_adversarial_prompt(
            findings=final_answer,
            documents=cited_docs_text,
        )

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content="Starting adversarial verification (Layer 1)",
            iteration=iteration,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(StepType.SEMANTIC_VERIFICATION, iteration, "Adversarial verification")

        sub_llm = LLMClient(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])
        token_usage.prompt_tokens += response.prompt_tokens
        token_usage.completion_tokens += response.completion_tokens

        findings = parse_verification_response(response.content)

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content=f"Layer 1 complete: {len(findings)} findings reviewed",
            iteration=iteration,
            tokens_used=response.total_tokens,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(
                StepType.SEMANTIC_VERIFICATION,
                iteration,
                f"Layer 1 complete: {len(findings)} findings",
            )

        # Layer 2: Code-specific checks (only for code projects)
        content_type = detect_content_type(doc_names)
        if content_type == "code":
            layer1_json = json.dumps(
                {
                    "findings": [
                        {
                            "finding_id": f.finding_id,
                            "original_claim": f.original_claim,
                            "confidence": f.confidence,
                            "reason": f.reason,
                            "evidence_classification": f.evidence_classification,
                            "flags": f.flags,
                        }
                        for f in findings
                    ]
                },
                indent=2,
            )

            prompt = self.prompt_loader.render_verify_code_prompt(
                previous_results=layer1_json,
                findings=final_answer,
                documents=cited_docs_text,
            )

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content="Starting code-specific verification (Layer 2)",
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION,
                    iteration,
                    "Code-specific verification",
                )

            sub_llm2 = LLMClient(model=self.model, api_key=self.api_key)
            response2 = sub_llm2.complete(messages=[{"role": "user", "content": prompt}])
            token_usage.prompt_tokens += response2.prompt_tokens
            token_usage.completion_tokens += response2.completion_tokens

            findings = parse_verification_response(response2.content)

            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content=f"Layer 2 complete: {len(findings)} findings reviewed",
                iteration=iteration,
                tokens_used=response2.total_tokens,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SEMANTIC_VERIFICATION,
                    iteration,
                    f"Layer 2 complete: {len(findings)} findings",
                )

        return SemanticVerificationReport(
            findings=findings,
            content_type=content_type,
        )

    def query(
        self,
        documents: list[str],
        question: str,
        doc_names: list[str] | None = None,
        on_progress: ProgressCallback | None = None,
        storage: StorageBackend | None = None,
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

        # Build document sizes list
        size_lines = []
        for i, (name, size) in enumerate(zip(doc_names, doc_sizes)):
            warning = " EXCEEDS LIMIT - must chunk" if size > MAX_SUBCALL_CHARS else ""
            size_lines.append(f"    - context[{i}] ({name}): {size:,} chars{warning}")
        doc_sizes_list = "\n".join(size_lines)

        system_prompt = self.prompt_loader.render_system_prompt(
            doc_count=len(documents),
            total_chars=total_chars,
            doc_sizes_list=doc_sizes_list,
            max_subcall_chars=MAX_SUBCALL_CHARS,
        )

        # Set up incremental trace writer
        inc_writer = (
            IncrementalTraceWriter(storage, suppress_errors=True) if storage is not None else None
        )
        trace_finalized = False
        if inc_writer is not None and project_id is not None:
            trace_id = str(uuid.uuid4())
            context = QueryContext(
                trace_id=trace_id,
                question=question,
                document_ids=doc_names or [f"doc_{i}" for i in range(len(documents))],
                model=self.model,
                system_prompt=system_prompt,
                subcall_prompt=self.prompt_loader.get_raw_template("subcall.md"),
            )
            inc_writer.start(project_id, context)

        def _write_step(step: TraceStep) -> None:
            if inc_writer is not None:
                inc_writer.write_step(step)

        def _finalize_trace(answer: str, status: str) -> None:
            nonlocal trace_finalized
            if trace_finalized or inc_writer is None:
                return
            trace_finalized = True
            inc_writer.finalize(
                answer=answer,
                token_usage=token_usage,
                execution_time=time.time() - start_time,
                status=status,
            )
            if storage is not None and project_id is not None:
                TraceWriter(storage, suppress_errors=True).cleanup_old_traces(
                    project_id, max_count=self.max_traces_per_project
                )

        # Initialize LLM client
        llm = LLMClient(model=self.model, system_prompt=system_prompt, api_key=self.api_key)

        # Initialize conversation
        messages: list[dict[str, str]] = [{"role": "user", "content": question}]

        # Track current iteration for llm_query callback
        current_iteration = 0

        # Create executor with callback for llm_query
        def llm_query_callback(instruction: str, content: str) -> str:
            return self._handle_llm_query(
                instruction,
                content,
                trace,
                token_usage,
                current_iteration,
                on_progress,
                on_step=_write_step,
            )

        # Acquire executor from pool or create standalone
        if self._pool is not None:
            executor = self._pool.acquire()
            executor.llm_query_handler = llm_query_callback
            owns_executor = False
        else:
            executor = ContainerExecutor(llm_query_handler=llm_query_callback)
            executor.start()
            owns_executor = True

        try:
            # Set up context in sandbox
            executor.setup_context(documents)

            for iteration in range(self.max_iterations):
                current_iteration = iteration
                # Get LLM response
                response = llm.complete(messages=messages)
                token_usage.prompt_tokens += response.prompt_tokens
                token_usage.completion_tokens += response.completion_tokens

                step = trace.add_step(
                    type=StepType.CODE_GENERATED,
                    content=response.content,
                    iteration=iteration,
                    tokens_used=response.total_tokens,
                )
                _write_step(step)
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
                            "content": self.prompt_loader.render_code_required(),
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

                    step = trace.add_step(
                        type=StepType.CODE_OUTPUT,
                        content=output,
                        iteration=iteration,
                        duration_ms=exec_duration,
                    )
                    _write_step(step)
                    if on_progress:
                        on_progress(StepType.CODE_OUTPUT, iteration, output)

                    all_output.append(output)

                    # Check for final answer
                    if result.final_answer:
                        final_answer = result.final_answer
                        step = trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=final_answer,
                            iteration=iteration,
                        )
                        _write_step(step)
                        if on_progress:
                            on_progress(StepType.FINAL_ANSWER, iteration, final_answer)
                        break

                if final_answer:
                    verification = None
                    if self.verify_citations and executor.is_alive:
                        try:
                            code = build_verification_code(final_answer)
                            vresult = executor.execute(code, timeout=self.execution_timeout)
                            if vresult.status == "ok" and vresult.stdout:
                                verification = parse_verification_output(vresult.stdout)
                                step = trace.add_step(
                                    type=StepType.VERIFICATION,
                                    content=vresult.stdout,
                                    iteration=iteration,
                                )
                                _write_step(step)
                                if on_progress:
                                    on_progress(StepType.VERIFICATION, iteration, vresult.stdout)
                        except Exception as exc:
                            # Verification failure doesn't affect answer delivery,
                            # but record the error for diagnostics.
                            step = trace.add_step(
                                type=StepType.VERIFICATION,
                                content=f"Verification error: {exc}",
                                iteration=iteration,
                            )
                            _write_step(step)
                            if on_progress:
                                on_progress(
                                    StepType.VERIFICATION,
                                    iteration,
                                    f"Verification error: {exc}",
                                )

                    semantic_verification = None
                    if self.verify:
                        try:
                            semantic_verification = self._run_semantic_verification(
                                final_answer=final_answer,
                                documents=documents,
                                doc_names=doc_names or [],
                                trace=trace,
                                token_usage=token_usage,
                                iteration=iteration,
                                on_progress=on_progress,
                                on_step=_write_step,
                            )
                        except Exception as exc:
                            step = trace.add_step(
                                type=StepType.SEMANTIC_VERIFICATION,
                                content=f"Semantic verification error: {exc}",
                                iteration=iteration,
                            )
                            _write_step(step)
                            if on_progress:
                                on_progress(
                                    StepType.SEMANTIC_VERIFICATION,
                                    iteration,
                                    f"Semantic verification error: {exc}",
                                )

                    query_result = QueryResult(
                        answer=final_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                        verification=verification,
                        semantic_verification=semantic_verification,
                    )
                    _finalize_trace(final_answer, "success")
                    return query_result

                # Recover from dead executor mid-loop
                if not executor.is_alive and self._pool is not None:
                    executor.stop()
                    self._pool.discard(executor)
                    executor = self._pool.acquire()
                    executor.llm_query_handler = llm_query_callback
                    executor.setup_context(documents)
                elif not executor.is_alive:
                    answer = "[Executor died — cannot continue]"
                    query_result = QueryResult(
                        answer=answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                    )
                    _finalize_trace(answer, "executor_died")
                    return query_result

                # Add output to conversation
                combined_output = "\n\n".join(all_output)
                wrapped_output = wrap_repl_output(combined_output, self.max_output_chars)

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": wrapped_output})

            # Max iterations reached
            answer = "[Max iterations reached without final answer]"
            query_result = QueryResult(
                answer=answer,
                trace=trace,
                token_usage=token_usage,
                execution_time=time.time() - start_time,
            )
            _finalize_trace(answer, "max_iterations")
            return query_result

        finally:
            _finalize_trace("[interrupted]", "interrupted")
            if owns_executor:
                executor.stop()
            else:
                executor.llm_query_handler = None
                try:
                    executor.reset_namespace()
                except Exception:
                    # Executor is broken (e.g., socket closed after protocol error).
                    # Stop it and discard from pool — don't return a broken executor.
                    executor.stop()
                    self._pool.discard(executor)  # type: ignore[union-attr]
                else:
                    self._pool.release(executor)  # type: ignore[union-attr]
