"""Docker container executor for sandboxed code execution."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import DockerException
from docker.models.containers import Container

from shesha.security.containers import DEFAULT_SECURITY, ContainerSecurityConfig


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
    ) -> None:
        """Initialize executor with container settings."""
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_count = cpu_count
        self.llm_query_handler = llm_query_handler
        self.security = security
        self._client: docker.DockerClient | None = None
        self._container: Container | None = None
        self._socket: Any = None
        self._raw_buffer: bytes = b""  # Buffer for raw Docker stream (with headers)
        self._content_buffer: bytes = b""  # Buffer for demuxed content only

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
        if self._socket:
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

    def execute(self, code: str, timeout: int = 30) -> ExecutionResult:
        """Execute code in the container, handling llm_query callbacks."""
        self._send_raw(json.dumps({"action": "execute", "code": code}) + "\n")

        # Handle responses, which may include llm_query requests
        while True:
            response_line = self._read_line(timeout=timeout)
            result = json.loads(response_line)

            # Check if this is an llm_query request
            if result.get("action") == "llm_query":
                if self.llm_query_handler is None:
                    # No handler - send error back
                    self._send_raw(
                        json.dumps(
                            {
                                "action": "llm_response",
                                "result": "ERROR: No LLM query handler configured",
                            }
                        )
                        + "\n"
                    )
                else:
                    # Call handler and send response back
                    llm_response = self.llm_query_handler(
                        result["instruction"],
                        result["content"],
                    )
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
            )

    def _send_raw(self, data: str) -> None:
        """Send raw data to container stdin."""
        if self._socket:
            self._socket._sock.sendall(data.encode())

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
        if not self._socket:
            raise RuntimeError("No socket connection")

        self._socket._sock.settimeout(timeout)

        while True:
            # Check if we have a complete line in the content buffer
            if b"\n" in self._content_buffer:
                line, self._content_buffer = self._content_buffer.split(b"\n", 1)
                return line.decode().strip()

            # Need more content - demux from raw buffer or read more data
            # Ensure we have at least 8 bytes for a Docker header
            while len(self._raw_buffer) < 8:
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
                        self._raw_buffer = b""
                    result = self._content_buffer.decode().strip()
                    self._content_buffer = b""
                    return result
                self._raw_buffer += chunk

            # Check if this looks like a Docker header
            if self._raw_buffer[0] in (1, 2) and self._raw_buffer[1:4] == b"\x00\x00\x00":
                # Extract payload length from bytes 4-7 (big-endian)
                payload_len = int.from_bytes(self._raw_buffer[4:8], "big")

                # Read until we have the full frame (header + payload)
                while len(self._raw_buffer) < 8 + payload_len:
                    chunk = self._socket._sock.recv(4096)
                    if not chunk:
                        break
                    self._raw_buffer += chunk

                # Extract payload and remove the frame from raw buffer
                payload = self._raw_buffer[8 : 8 + payload_len]
                self._raw_buffer = self._raw_buffer[8 + payload_len :]

                # Append payload to content buffer (never mix with raw buffer)
                self._content_buffer += payload
            else:
                # Not a Docker header - treat raw buffer as plain data
                # This handles non-multiplexed streams
                self._content_buffer += self._raw_buffer
                self._raw_buffer = b""

                # If still no newline, read more
                if b"\n" not in self._content_buffer:
                    chunk = self._socket._sock.recv(4096)
                    if not chunk:
                        result = self._content_buffer.decode().strip()
                        self._content_buffer = b""
                        return result
                    self._raw_buffer += chunk

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
