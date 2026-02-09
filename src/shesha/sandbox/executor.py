"""Docker container executor for sandboxed code execution."""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import DockerException
from docker.models.containers import Container

from shesha.security.containers import DEFAULT_SECURITY, ContainerSecurityConfig


class ProtocolError(Exception):
    """Container protocol violation (oversized data, timeout)."""

    pass


class SubcallContentError(Exception):
    """Sub-LLM call rejected (e.g., content exceeds size limit)."""

    pass


# Protocol limits to prevent DoS attacks from malicious containers
MAX_BUFFER_SIZE = 10 * 1024 * 1024  # 10 MB max buffer
MAX_LINE_LENGTH = 1 * 1024 * 1024  # 1 MB max single line
MAX_READ_DURATION = 300  # 5 min total deadline
MAX_PAYLOAD_SIZE = 50 * 1024 * 1024  # 50 MB max outgoing payload
DEFAULT_SEND_TIMEOUT = 30  # 30 seconds for send operations


@dataclass
class ExecutionResult:
    """Result of code execution in sandbox."""

    status: str
    stdout: str
    stderr: str
    return_value: Any
    error: str | None
    final_answer: str | None = None
    final_var: str | None = None
    final_value: str | None = None
    vars: dict[str, str] | None = None


LLMQueryHandler = Callable[[str, str], str]  # (instruction, content) -> response


class ContainerExecutor:
    """Execute code in a Docker container."""

    def __init__(
        self,
        image: str = "shesha-sandbox",
        memory_limit: str = "512m",
        cpu_count: int = 1,
        llm_query_handler: LLMQueryHandler | None = None,
        security: ContainerSecurityConfig = DEFAULT_SECURITY,
        execution_mode: str = "fast",
    ) -> None:
        """Initialize executor with container settings."""
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_count = cpu_count
        self.llm_query_handler = llm_query_handler
        self.security = security
        self.execution_mode = execution_mode
        self._client: docker.DockerClient | None = None
        self._container: Container | None = None
        self._socket: Any = None
        self._raw_buffer: bytes = b""  # Buffer for raw Docker stream (with headers)
        self._content_buffer: bytes = b""  # Buffer for demuxed content only

    @property
    def is_alive(self) -> bool:
        """Whether the executor has an active socket connection."""
        return self._socket is not None

    def start(self) -> None:
        """Start a container for execution."""
        self._raw_buffer = b""  # Clear raw stream buffer
        self._content_buffer = b""  # Clear content buffer
        try:
            self._client = docker.from_env()
        except DockerException as e:
            if "Connection refused" in str(e):
                raise RuntimeError(
                    "Docker is not running. Please start Docker Desktop and try again."
                ) from e
            raise
        self._container = self._client.containers.run(
            self.image,
            detach=True,
            stdin_open=True,
            tty=False,
            mem_limit=self.memory_limit,
            cpu_count=self.cpu_count,
            **self.security.to_docker_kwargs(),
        )
        # Attach to container for bidirectional communication
        self._socket = self._container.attach_socket(params={"stdin": 1, "stdout": 1, "stream": 1})

    def stop(self) -> None:
        """Stop and remove the container."""
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._container:
            try:
                self._container.stop(timeout=5)
            except Exception:
                pass  # Container may already be stopped or removed
            try:
                self._container.remove(force=True)
            except Exception:
                pass  # Container may already be removed
            self._container = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass  # Client may already be closed or daemon unavailable
            self._client = None

    def setup_context(self, context: list[str]) -> None:
        """Initialize the context variable in the container."""
        self._send_command({"action": "setup", "context": context})

    def reset_namespace(self) -> dict[str, Any]:
        """Reset the sandbox namespace, clearing user variables but keeping builtins."""
        return self._send_command({"action": "reset"})

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Execute code in the container, handling llm_query callbacks."""
        # Check if executor is in stopped state (e.g., after protocol error)
        if self._socket is None:
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error="Executor stopped: no socket connection",
            )

        self._send_raw(json.dumps({"action": "execute", "code": code}) + "\n")

        try:
            # Handle responses, which may include llm_query requests
            while True:
                response_line = self._read_line(timeout=timeout)
                result = json.loads(response_line)

                # Check if this is an llm_query request
                if result.get("action") == "llm_query":
                    if self.llm_query_handler is None:
                        # No handler — signal error so sandbox raises ValueError
                        self._send_raw(
                            json.dumps(
                                {
                                    "action": "llm_response",
                                    "error": "No LLM query handler configured",
                                }
                            )
                            + "\n"
                        )
                    else:
                        # Call handler and send response back
                        try:
                            llm_response = self.llm_query_handler(
                                result["instruction"],
                                result["content"],
                            )
                        except SubcallContentError as e:
                            # Content rejected — send error so sandbox raises
                            self._send_raw(
                                json.dumps(
                                    {
                                        "action": "llm_response",
                                        "error": str(e),
                                    }
                                )
                                + "\n"
                            )
                        else:
                            self._send_raw(
                                json.dumps(
                                    {
                                        "action": "llm_response",
                                        "result": llm_response,
                                    }
                                )
                                + "\n"
                            )
                    continue

                # Check if this is a batched llm_query request
                if result.get("action") == "llm_query_batch":
                    if self.llm_query_handler is None:
                        self._send_raw(
                            json.dumps(
                                {
                                    "action": "llm_batch_response",
                                    "error": "No LLM query handler configured",
                                }
                            )
                            + "\n"
                        )
                    else:
                        prompts = result["prompts"]
                        results_list = self._execute_batch(prompts)
                        self._send_raw(
                            json.dumps(
                                {
                                    "action": "llm_batch_response",
                                    "results": results_list,
                                }
                            )
                            + "\n"
                        )
                    continue

                # This is the final execution result
                return ExecutionResult(
                    status=result.get("status", "error"),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    return_value=result.get("return_value"),
                    error=result.get("error"),
                    final_answer=result.get("final_answer"),
                    final_var=result.get("final_var"),
                    final_value=result.get("final_value"),
                    vars=result.get("vars"),
                )
        except ProtocolError as e:
            # Protocol violation implies potentially malicious/broken container state.
            # Terminate it to prevent reuse of compromised container.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: {e}",
            )
        except json.JSONDecodeError as e:
            # Invalid JSON from container (e.g., sandbox wrote to sys.__stdout__).
            # Treat as protocol violation - container is in unknown state.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: invalid JSON from container: {e}",
            )
        except KeyError as e:
            # Malformed message missing required fields (e.g., llm_query without
            # instruction/content). Treat as protocol violation.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: missing required field {e}",
            )
        except UnicodeDecodeError as e:
            # Non-UTF8 bytes from container (e.g., writing to sys.stdout.buffer).
            # Treat as protocol violation - container is sending invalid data.
            self.stop()
            return ExecutionResult(
                status="error",
                stdout="",
                stderr="",
                return_value=None,
                error=f"Protocol error: invalid UTF-8 from container: {e}",
            )

    _MAX_BATCH_WORKERS = 32

    def _execute_batch(self, prompts: list[str]) -> list[str]:
        """Execute batch of LLM prompts, concurrently (fast) or sequentially (deep)."""
        if not prompts:
            return []

        handler = self.llm_query_handler
        assert handler is not None

        def _call_one(prompt: str) -> str:
            try:
                return handler(prompt, "")
            except SubcallContentError as e:
                return f"[error: {e}]"

        if self.execution_mode == "deep":
            return [_call_one(p) for p in prompts]

        workers = min(len(prompts), self._MAX_BATCH_WORKERS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_call_one, prompts))

    def _send_raw(self, data: str, timeout: int = DEFAULT_SEND_TIMEOUT) -> None:
        """Send raw data to container stdin."""
        encoded = data.encode()
        if len(encoded) > MAX_PAYLOAD_SIZE:
            raise ProtocolError(f"Payload size {len(encoded)} exceeds maximum {MAX_PAYLOAD_SIZE}")
        if self._socket is not None:
            sock = self._socket._sock
            previous_timeout = sock.gettimeout()
            sock.settimeout(timeout)
            try:
                sock.sendall(encoded)
            except OSError as e:
                raise ProtocolError(f"Send failed: {e}") from e
            finally:
                sock.settimeout(previous_timeout)

    def _read_line(self, timeout: int = 30) -> str:
        """Read a line from container stdout, stripping Docker multiplexed headers.

        Uses two separate buffers:
        - _raw_buffer: raw Docker stream data (may contain headers)
        - _content_buffer: demuxed payload content only (safe to decode)

        Docker attach socket uses multiplexed format with 8-byte header:
        - 1 byte: stream type (1=stdout, 2=stderr)
        - 3 bytes: padding (zeros)
        - 4 bytes: payload length (big-endian)
        """
        if self._socket is None:
            raise RuntimeError("No socket connection")

        self._socket._sock.settimeout(timeout)

        # Effective deadline: the shorter of MAX_READ_DURATION and timeout + 10s buffer.
        # This prevents a container from exploiting the gap between a short execution
        # timeout and the hardcoded 5-minute MAX_READ_DURATION.
        effective_deadline = min(MAX_READ_DURATION, timeout + 10)

        start_time = time.monotonic()

        while True:
            if time.monotonic() - start_time > effective_deadline:
                raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
            # Check if we have a complete line in the content buffer
            if b"\n" in self._content_buffer:
                line, self._content_buffer = self._content_buffer.split(b"\n", 1)
                if len(line) > MAX_LINE_LENGTH:
                    raise ProtocolError(
                        f"Line length {len(line)} exceeds maximum {MAX_LINE_LENGTH}"
                    )
                return line.decode().strip()

            # Need more content - demux from raw buffer or read more data
            # Ensure we have at least 8 bytes for a Docker header
            while len(self._raw_buffer) < 8:
                # Check deadline inside inner loop to prevent slow-drip DoS
                if time.monotonic() - start_time > effective_deadline:
                    raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
                chunk = self._socket._sock.recv(4096)
                if not chunk:
                    # Connection closed while waiting for Docker header
                    # Check if _raw_buffer looks like a partial Docker header
                    # (starts with stream type 1 or 2) - if so, discard it
                    # as it contains binary length bytes that would cause
                    # UnicodeDecodeError. Otherwise, it might be plain text
                    # from a non-multiplexed stream, so try to decode it.
                    if self._raw_buffer and self._raw_buffer[0] in (1, 2):
                        # Partial Docker header - discard binary bytes
                        self._raw_buffer = b""
                    else:
                        # Possibly plain text - add to content buffer
                        self._content_buffer += self._raw_buffer
                        if len(self._content_buffer) > MAX_BUFFER_SIZE:
                            raise ProtocolError(f"Content buffer exceeded {MAX_BUFFER_SIZE} bytes")
                        self._raw_buffer = b""
                    buf_len = len(self._content_buffer)
                    if buf_len > MAX_LINE_LENGTH:
                        raise ProtocolError(f"Line length {buf_len} exceeds max {MAX_LINE_LENGTH}")
                    result = self._content_buffer.decode().strip()
                    self._content_buffer = b""
                    return result
                self._raw_buffer += chunk
                if len(self._raw_buffer) > MAX_BUFFER_SIZE:
                    raise ProtocolError(f"Raw buffer exceeded {MAX_BUFFER_SIZE} bytes")

            # Check if this looks like a Docker header
            if self._raw_buffer[0] in (1, 2) and self._raw_buffer[1:4] == b"\x00\x00\x00":
                # Extract payload length from bytes 4-7 (big-endian)
                payload_len = int.from_bytes(self._raw_buffer[4:8], "big")

                # Read until we have the full frame (header + payload)
                while len(self._raw_buffer) < 8 + payload_len:
                    # Check deadline inside inner loop to prevent slow-drip DoS
                    if time.monotonic() - start_time > effective_deadline:
                        raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
                    chunk = self._socket._sock.recv(4096)
                    if not chunk:
                        break
                    self._raw_buffer += chunk
                    if len(self._raw_buffer) > MAX_BUFFER_SIZE:
                        raise ProtocolError(f"Raw buffer exceeded {MAX_BUFFER_SIZE} bytes")

                # Extract payload and remove the frame from raw buffer
                payload = self._raw_buffer[8 : 8 + payload_len]
                self._raw_buffer = self._raw_buffer[8 + payload_len :]

                # Append payload to content buffer (never mix with raw buffer)
                self._content_buffer += payload
                if len(self._content_buffer) > MAX_BUFFER_SIZE:
                    raise ProtocolError(f"Content buffer exceeded {MAX_BUFFER_SIZE} bytes")
                # Check line length limit even without newline (prevents streaming attack)
                if (
                    b"\n" not in self._content_buffer
                    and len(self._content_buffer) > MAX_LINE_LENGTH
                ):
                    raise ProtocolError(
                        f"Line length {len(self._content_buffer)} exceeds max {MAX_LINE_LENGTH}"
                    )
            else:
                # Not a Docker header - treat raw buffer as plain data
                # This handles non-multiplexed streams
                self._content_buffer += self._raw_buffer
                if len(self._content_buffer) > MAX_BUFFER_SIZE:
                    raise ProtocolError(f"Content buffer exceeded {MAX_BUFFER_SIZE} bytes")
                # Check line length limit even without newline (prevents streaming attack)
                if (
                    b"\n" not in self._content_buffer
                    and len(self._content_buffer) > MAX_LINE_LENGTH
                ):
                    raise ProtocolError(
                        f"Line length {len(self._content_buffer)} exceeds max {MAX_LINE_LENGTH}"
                    )
                self._raw_buffer = b""

                # If still no newline, read more
                if b"\n" not in self._content_buffer:
                    # Check deadline before recv to prevent slow-drip DoS
                    if time.monotonic() - start_time > effective_deadline:
                        raise ProtocolError(f"Read duration exceeded {effective_deadline} seconds")
                    chunk = self._socket._sock.recv(4096)
                    if not chunk:
                        buf_len = len(self._content_buffer)
                        if buf_len > MAX_LINE_LENGTH:
                            raise ProtocolError(
                                f"Line length {buf_len} exceeds max {MAX_LINE_LENGTH}"
                            )
                        result = self._content_buffer.decode().strip()
                        self._content_buffer = b""
                        return result
                    self._raw_buffer += chunk
                    if len(self._raw_buffer) > MAX_BUFFER_SIZE:
                        raise ProtocolError(f"Raw buffer exceeded {MAX_BUFFER_SIZE} bytes")

    def _send_command(self, command: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
        """Send a JSON command to the container and get response."""
        self._send_raw(json.dumps(command) + "\n")
        response = self._read_line(timeout=timeout)
        result: dict[str, Any] = json.loads(response)
        return result

    def __enter__(self) -> "ContainerExecutor":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.stop()
