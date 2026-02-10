"""RLM engine - the core REPL+LLM loop."""

import copy
import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shesha.llm.client import LLMClient
from shesha.models import QueryContext
from shesha.prompts import PromptLoader
from shesha.rlm.prompts import (
    format_code_echo,
    truncate_code_output,
    wrap_subcall_content,
)
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
ProgressCallback = Callable[[StepType, int, str, TokenUsage], None]


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
    """Extract code from ```repl blocks."""
    pattern = r"```repl\s*\n(.*?)\n```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches


def find_final_answer(text: str) -> tuple[str, str] | None:
    """Find bare FINAL(...) or FINAL_VAR(...) in response text outside code blocks.

    Matches the reference RLM's find_final_answer (rlm/rlm/utils/parsing.py:29-63).
    The model sometimes outputs FINAL_VAR(x) as bare text instead of inside a
    ```repl block. This function catches those cases.

    Returns:
        ("final", answer_string) for FINAL(...)
        ("final_var", variable_name) for FINAL_VAR(...)
        None if no pattern found
    """
    # Strip code blocks so we don't match FINAL inside ```repl blocks
    # (those are handled by the executor)
    stripped = re.sub(r"```repl\s*\n.*?\n```", "", text, flags=re.DOTALL)

    # Check FINAL_VAR first (more specific pattern)
    final_var_pattern = r"^\s*FINAL_VAR\((.*?)\)"
    match = re.search(final_var_pattern, stripped, re.MULTILINE | re.DOTALL)
    if match:
        var_name = match.group(1).strip().strip('"').strip("'")
        return ("final_var", var_name)

    # Check FINAL pattern — greedy match to handle nested parentheses,
    # no quote requirement (aligned with reference RLM rlm/utils/parsing.py:58)
    final_pattern = r"^\s*FINAL\((.*)\)\s*$"
    match = re.search(final_pattern, stripped, re.MULTILINE | re.DOTALL)
    if match:
        return ("final", match.group(1).strip())

    return None


class RLMEngine:
    """The RLM engine - runs the REPL+LLM loop."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_iterations: int = 20,
        # 20K per-block limit matches reference RLM (rlm/rlm/utils/parsing.py:67).
        # This is a forcing function: when context exceeds the truncation limit,
        # the model must use llm_query() to analyze content it cannot see.
        max_output_chars: int = 20_000,
        execution_timeout: int = 30,
        max_subcall_content_chars: int = 500_000,
        prompts_dir: Path | None = None,
        pool: ContainerPool | None = None,
        max_traces_per_project: int = 50,
        verify_citations: bool = True,
        verify: bool = False,
        execution_mode: str = "fast",
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
        self.execution_mode = execution_mode
        self._subcall_lock = threading.Lock()

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
        """Handle a sub-LLM query from the sandbox.

        Thread-safe: uses _subcall_lock to protect shared trace and token state
        when called concurrently from batched executor dispatch.
        """
        # Record the request (lock protects trace and token_usage mutations)
        step_content = f"instruction: {instruction}\ncontent: [{len(content)} chars]"
        with self._subcall_lock:
            step = trace.add_step(
                type=StepType.SUBCALL_REQUEST,
                content=step_content,
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SUBCALL_REQUEST, iteration, step_content, copy.copy(token_usage)
                )

        # Check size limit on the total payload (instruction + content).
        # Single-arg llm_query passes everything in instruction with content="",
        # so checking content alone would miss oversized single-arg calls.
        payload_size = len(instruction) + len(content)
        if payload_size > self.max_subcall_content_chars:
            error_msg = (
                f"Payload size ({payload_size:,} chars) exceeds the sub-LLM limit "
                f"of {self.max_subcall_content_chars:,} chars. Please chunk the content "
                f"into smaller pieces and make multiple llm_query calls."
            )
            with self._subcall_lock:
                step = trace.add_step(
                    type=StepType.SUBCALL_RESPONSE,
                    content=error_msg,
                    iteration=iteration,
                )
                if on_step:
                    on_step(step)
                if on_progress:
                    on_progress(
                        StepType.SUBCALL_RESPONSE, iteration, error_msg, copy.copy(token_usage)
                    )
            raise SubcallContentError(error_msg)

        # Build prompt: when content is empty (single-arg llm_query), send
        # instruction directly. When content is provided, wrap in untrusted tags.
        if content:
            wrapped_content = wrap_subcall_content(content)
            prompt = self.prompt_loader.render_subcall_prompt(instruction, wrapped_content)
        else:
            prompt = instruction

        # LLM call runs outside lock — this is the I/O-bound work we parallelize
        sub_llm = LLMClient(model=self.model, api_key=self.api_key)
        response = sub_llm.complete(messages=[{"role": "user", "content": prompt}])

        # Record response and update tokens (lock protects shared state)
        with self._subcall_lock:
            token_usage.prompt_tokens += response.prompt_tokens
            token_usage.completion_tokens += response.completion_tokens

            step = trace.add_step(
                type=StepType.SUBCALL_RESPONSE,
                content=response.content,
                iteration=iteration,
                tokens_used=response.total_tokens,
            )
            if on_step:
                on_step(step)
            if on_progress:
                on_progress(
                    StepType.SUBCALL_RESPONSE, iteration, response.content, copy.copy(token_usage)
                )

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

        # Check cited docs size limit
        if len(cited_docs_text) > self.max_subcall_content_chars:
            step = trace.add_step(
                type=StepType.SEMANTIC_VERIFICATION,
                content=(
                    f"Skipping verification: cited documents ({len(cited_docs_text):,} chars) "
                    f"exceed limit of {self.max_subcall_content_chars:,} chars"
                ),
                iteration=iteration,
            )
            if on_step:
                on_step(step)
            return None

        # Wrap cited docs in untrusted content tags (security boundary)
        wrapped_docs = wrap_subcall_content(cited_docs_text)

        # Layer 1: Adversarial verification
        prompt = self.prompt_loader.render_verify_adversarial_prompt(
            findings=final_answer,
            documents=wrapped_docs,
        )

        step = trace.add_step(
            type=StepType.SEMANTIC_VERIFICATION,
            content="Starting adversarial verification (Layer 1)",
            iteration=iteration,
        )
        if on_step:
            on_step(step)
        if on_progress:
            on_progress(
                StepType.SEMANTIC_VERIFICATION,
                iteration,
                "Adversarial verification",
                copy.copy(token_usage),
            )

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
                copy.copy(token_usage),
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
                documents=wrapped_docs,
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
                    copy.copy(token_usage),
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
                    copy.copy(token_usage),
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

        # Build system prompt (no variables — 500K hardcoded in template)
        doc_sizes = [len(d) for d in documents]
        total_chars = sum(doc_sizes)

        system_prompt = self.prompt_loader.render_system_prompt()

        # Context metadata as assistant message: primes the model to
        # continue working rather than start fresh. Matches reference
        # rlm/rlm/utils/prompts.py:119-122.
        # Always "list" — the sandbox sets context as list[str] regardless of count.
        # Matches reference RLM (rlm/core/types.py:244-245).
        context_type = "list"
        context_lengths = str(doc_sizes)
        context_metadata = self.prompt_loader.render_context_metadata(
            context_type=context_type,
            context_total_length=total_chars,
            context_lengths=context_lengths,
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

        # Iteration-0 safeguard: prevent model from jumping to FINAL()
        # without exploring. Matches reference rlm/rlm/utils/prompts.py:136.
        first_user_msg = self.prompt_loader.render_iteration_zero(question=question)
        messages: list[dict[str, str]] = [
            {"role": "assistant", "content": context_metadata},
            {"role": "user", "content": first_user_msg},
        ]

        # Factory to create a callback with a frozen iteration value.
        # Without this, a closure over a mutable variable risks capturing
        # a stale iteration if the callback were ever invoked after the loop
        # advances (e.g., async execution, deferred calls).
        def _make_llm_callback(frozen_iteration: int) -> Callable[[str, str], str]:
            def llm_query_callback(instruction: str, content: str) -> str:
                return self._handle_llm_query(
                    instruction,
                    content,
                    trace,
                    token_usage,
                    frozen_iteration,
                    on_progress,
                    on_step=_write_step,
                )

            return llm_query_callback

        # Acquire executor from pool or create standalone
        if self._pool is not None:
            executor = self._pool.acquire()
            executor.llm_query_handler = _make_llm_callback(0)
            executor.execution_mode = self.execution_mode
            owns_executor = False
        else:
            executor = ContainerExecutor(llm_query_handler=_make_llm_callback(0))
            executor.execution_mode = self.execution_mode
            executor.start()
            owns_executor = True

        try:
            # Set up context in sandbox
            executor.setup_context(documents)

            for iteration in range(self.max_iterations):
                executor.llm_query_handler = _make_llm_callback(iteration)
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
                    on_progress(
                        StepType.CODE_GENERATED,
                        iteration,
                        response.content,
                        copy.copy(token_usage),
                    )

                # Check for bare FINAL/FINAL_VAR in response text (outside code blocks).
                # The model sometimes outputs FINAL_VAR(x) as bare text without a
                # ```repl block. Matches reference rlm/rlm/core/rlm.py:240.
                bare_final = find_final_answer(response.content)
                if bare_final is not None:
                    final_type, final_value = bare_final
                    if final_type == "final_var":
                        # Retrieve variable value from sandbox
                        retrieve_result = executor.execute(
                            f"print({final_value})", timeout=self.execution_timeout
                        )
                        bare_answer = (
                            retrieve_result.stdout.strip() if retrieve_result.stdout else ""
                        )
                    else:
                        bare_answer = final_value

                    step = trace.add_step(
                        type=StepType.FINAL_ANSWER,
                        content=bare_answer,
                        iteration=iteration,
                    )
                    _write_step(step)
                    if on_progress:
                        on_progress(
                            StepType.FINAL_ANSWER,
                            iteration,
                            bare_answer,
                            copy.copy(token_usage),
                        )

                    query_result = QueryResult(
                        answer=bare_answer,
                        trace=trace,
                        token_usage=token_usage,
                        execution_time=time.time() - start_time,
                    )
                    _finalize_trace(bare_answer, "success")
                    return query_result

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
                exec_results = []
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

                    # Truncate each code block's output individually (forcing function)
                    output = truncate_code_output(output, self.max_output_chars)

                    step = trace.add_step(
                        type=StepType.CODE_OUTPUT,
                        content=output,
                        iteration=iteration,
                        duration_ms=exec_duration,
                    )
                    _write_step(step)
                    if on_progress:
                        on_progress(StepType.CODE_OUTPUT, iteration, output, copy.copy(token_usage))

                    all_output.append(output)
                    exec_results.append(result)

                    # Check for final answer (use `is not None` to catch falsy
                    # values like FINAL(0), FINAL(""), FINAL(False))
                    if result.final_answer is not None:
                        # Sandbox FINAL() can receive any type; coerce to str
                        # so trace steps and QueryResult.answer stay str.
                        final_answer = (
                            result.final_answer
                            if isinstance(result.final_answer, str)
                            else str(result.final_answer)
                        )
                        step = trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=final_answer,
                            iteration=iteration,
                        )
                        _write_step(step)
                        if on_progress:
                            on_progress(
                                StepType.FINAL_ANSWER,
                                iteration,
                                final_answer,
                                copy.copy(token_usage),
                            )
                        break
                    elif result.final_var is not None:
                        final_answer = result.final_value or ""
                        step = trace.add_step(
                            type=StepType.FINAL_ANSWER,
                            content=final_answer,
                            iteration=iteration,
                        )
                        _write_step(step)
                        if on_progress:
                            on_progress(
                                StepType.FINAL_ANSWER,
                                iteration,
                                final_answer,
                                copy.copy(token_usage),
                            )
                        break

                if final_answer is not None:
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
                                    on_progress(
                                        StepType.VERIFICATION,
                                        iteration,
                                        vresult.stdout,
                                        copy.copy(token_usage),
                                    )
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
                                    copy.copy(token_usage),
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
                                    copy.copy(token_usage),
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
                    executor.llm_query_handler = _make_llm_callback(iteration)
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

                # Add assistant response, then per-block code echo messages
                messages.append({"role": "assistant", "content": response.content})
                for code_block, output, exec_result in zip(code_blocks, all_output, exec_results):
                    messages.append(
                        {
                            "role": "user",
                            "content": format_code_echo(code_block, output, exec_result.vars),
                        }
                    )

                # Per-iteration continuation prompt re-instructs sub-LLM usage
                messages.append(
                    {
                        "role": "user",
                        "content": self.prompt_loader.render_iteration_continue(
                            question=question,
                        ),
                    }
                )

            # Max iterations reached — ask LLM for one last answer
            fallback_messages = messages + [
                {
                    "role": "assistant",
                    "content": "Please provide a final answer to the user's question "
                    "based on the information provided.",
                }
            ]
            response = llm.complete(messages=fallback_messages)
            token_usage.prompt_tokens += response.prompt_tokens
            token_usage.completion_tokens += response.completion_tokens
            answer = response.content

            step = trace.add_step(
                type=StepType.FINAL_ANSWER,
                content=f"[max-iter fallback] {answer}",
                iteration=self.max_iterations - 1,
            )
            _write_step(step)

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
