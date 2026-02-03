"""Tests for sandbox executor."""

from unittest.mock import MagicMock, patch

from shesha.sandbox.executor import ContainerExecutor, ExecutionResult
from shesha.security.containers import ContainerSecurityConfig


def make_docker_frame(data: bytes, stream_type: int = 1) -> bytes:
    """Create a Docker multiplexed stream frame.

    Docker attach socket uses 8-byte header:
    - 1 byte: stream type (1=stdout, 2=stderr)
    - 3 bytes: padding (zeros)
    - 4 bytes: payload length (big-endian)
    """
    header = bytes([stream_type, 0, 0, 0]) + len(data).to_bytes(4, "big")
    return header + data


class TestDockerFrameParsing:
    """Tests for Docker multiplexed stream parsing in _read_line."""

    def test_read_line_handles_multi_frame_json_without_intermediate_newlines(self):
        """_read_line correctly handles JSON split across multiple Docker frames.

        This reproduces the bug where:
        1. Frame 1 payload (no newline) is prepended to buffer
        2. Next iteration sees payload start (e.g. '{') not Docker header
        3. Code falls to "not a Docker header" branch
        4. Binary Docker header bytes get decoded as UTF-8, causing decode error
        """
        # Simulate a JSON response split across two Docker frames
        # First frame: partial JSON without newline
        part1 = b'{"status": "ok", "data": "'
        # Second frame: rest of JSON with newline
        part2 = b'some value"}\n'

        # Build the raw Docker stream data
        stream_data = make_docker_frame(part1) + make_docker_frame(part2)

        # Create mock socket that returns this data
        mock_socket = MagicMock()
        chunks = [stream_data]  # Return all at once
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        # Create executor and set up socket directly
        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # This should NOT raise a UTF-8 decode error
        result = executor._read_line(timeout=5)

        # Should get the complete JSON line
        assert result == '{"status": "ok", "data": "some value"}'

    def test_read_line_handles_large_payload_with_binary_length_bytes(self):
        """_read_line handles payloads where length field contains 0x80+ bytes.

        When payload length > 127, the length field contains bytes >= 0x80
        which are invalid UTF-8 start bytes if incorrectly decoded.
        """
        # Create a payload that results in length bytes containing 0x80
        # Length 32768 (0x8000) has 0x80 in high byte
        large_payload = b"x" * 32749 + b'{"result": "done"}\n'  # Total 32768 bytes

        stream_data = make_docker_frame(large_payload)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # Should not raise decode error
        result = executor._read_line(timeout=5)
        assert '"result": "done"' in result

    def test_read_line_multi_frame_triggers_utf8_error_with_large_second_frame(self):
        """_read_line should not raise UTF-8 decode error when second frame is large.

        This directly reproduces the original bug:
        - First frame: partial JSON (no newline)
        - Second frame: large payload (length > 32768 = 0x8000)
        - The 0x80 byte in the length field triggers UTF-8 decode error
        """
        # First frame: partial JSON without newline
        part1 = b'{"status": "ok", "content": "'

        # Second frame: large payload with 0x80 in length field
        # 32774 bytes triggers length = 0x00008006, containing 0x80
        part2 = b"A" * 32767 + b'done"}\n'  # Total 32774 bytes

        stream_data = make_docker_frame(part1) + make_docker_frame(part2)

        mock_socket = MagicMock()
        chunks = [stream_data]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # This should NOT raise: UnicodeDecodeError: 'utf-8' codec can't decode
        # byte 0x80 in position X: invalid start byte
        result = executor._read_line(timeout=5)

        # Verify we got the complete, uncorrupted JSON
        assert result.startswith('{"status": "ok"')
        assert result.endswith('done"}')
        # The content should be exactly the two payloads concatenated
        expected = '{"status": "ok", "content": "' + "A" * 32767 + 'done"}'
        assert result == expected


class TestConnectionClose:
    """Tests for connection close handling in _read_line."""

    def test_read_line_preserves_raw_buffer_on_connection_close(self):
        """_read_line includes _raw_buffer contents when connection closes.

        When recv() returns b"" while waiting for 8 bytes (Docker header),
        any bytes already in _raw_buffer should be included in the result,
        not silently dropped.

        This tests the specific bug: if we have <8 bytes in raw_buffer when
        connection closes, those bytes were being silently dropped.
        """
        mock_socket = MagicMock()

        # Simulate: first recv gets 5 bytes (< 8), second recv gets connection close
        # This hits the bug path at lines 174-180
        chunks = [b"hello", b""]  # 5 bytes, then close
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result = executor._read_line(timeout=5)

        # Should include the 5-byte data, not return empty
        assert result == "hello"

    def test_read_line_returns_content_buffer_on_close_with_partial_header(self):
        """_read_line returns only content_buffer when connection closes mid-header.

        If we have valid content in _content_buffer and partial header bytes
        in _raw_buffer when connection closes, we should return ONLY the content,
        not the binary header bytes (which would cause decode errors or garbage).
        """
        mock_socket = MagicMock()

        # Simulate: get a complete frame, then partial header, then close
        frame1 = make_docker_frame(b'{"status": "ok"}')
        partial_header = b"\x01\x00\x00"  # 3 bytes of a Docker header

        chunks = [frame1 + partial_header, b""]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        result = executor._read_line(timeout=5)

        # Should return ONLY the valid content from frame1, NOT the partial header
        assert result == '{"status": "ok"}'

    def test_read_line_handles_binary_header_bytes_on_connection_close(self):
        """_read_line must not raise UnicodeDecodeError when partial header contains 0x80.

        When connection closes with partial Docker header in _raw_buffer containing
        bytes >= 0x80 (invalid UTF-8 start bytes), the code must not crash.
        """
        mock_socket = MagicMock()

        # Simulate: get a complete frame, then partial header with 0x80 byte, then close
        frame1 = make_docker_frame(b'{"result": "data"}')
        # Partial header: stream type 1, padding, then 0x80 (invalid UTF-8)
        partial_header_with_0x80 = b"\x01\x00\x00\x00\x80"

        chunks = [frame1 + partial_header_with_0x80, b""]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # This should NOT raise UnicodeDecodeError
        result = executor._read_line(timeout=5)

        # Should return only the valid content, discarding the partial header
        assert result == '{"result": "data"}'


class TestContainerExecutor:
    """Tests for ContainerExecutor."""

    def test_execution_result_dataclass(self):
        """ExecutionResult stores execution output."""
        result = ExecutionResult(
            status="ok",
            stdout="Hello",
            stderr="",
            return_value=None,
            error=None,
            final_answer=None,
        )
        assert result.status == "ok"
        assert result.stdout == "Hello"

    @patch("shesha.sandbox.executor.docker")
    def test_executor_creates_container(self, mock_docker: MagicMock):
        """Executor creates a Docker container."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()

        mock_client.containers.run.assert_called_once()
        assert executor._container is not None

    @patch("shesha.sandbox.executor.docker")
    def test_executor_stops_container(self, mock_docker: MagicMock):
        """Executor stops and removes container on stop()."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()
        executor.stop()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()

    @patch("shesha.sandbox.executor.docker")
    def test_executor_closes_docker_client_on_stop(self, mock_docker: MagicMock):
        """Executor closes the DockerClient on stop() to prevent resource leaks.

        The DockerClient maintains HTTP connections to the Docker daemon.
        If not closed, the urllib3 HTTP response finalizer will fail on exit.
        """
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor(image="shesha-sandbox")
        executor.start()
        executor.stop()

        # DockerClient.close() must be called to prevent urllib3 errors on exit
        mock_client.close.assert_called_once()

    @patch("shesha.sandbox.executor.docker")
    def test_start_raises_clear_error_when_docker_not_running(self, mock_docker: MagicMock):
        """Executor provides clear error message when Docker daemon is not running.

        When docker.from_env() fails with ConnectionRefusedError (wrapped in
        docker.errors.DockerException), the error message should clearly explain
        that Docker Desktop needs to be started.
        """
        from docker.errors import DockerException

        # Simulate Docker daemon not running
        mock_docker.from_env.side_effect = DockerException(
            "Error while fetching server API version: "
            "('Connection aborted.', ConnectionRefusedError(61, 'Connection refused'))"
        )

        executor = ContainerExecutor()

        import pytest

        with pytest.raises(RuntimeError) as exc_info:
            executor.start()

        error_msg = str(exc_info.value)
        assert "Docker" in error_msg
        assert "not running" in error_msg or "start" in error_msg.lower()


class TestContainerSecurityIntegration:
    """Tests for container security integration."""

    @patch("shesha.sandbox.executor.docker")
    def test_executor_uses_default_security(self, mock_docker: MagicMock) -> None:
        """Executor applies default security config."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        executor = ContainerExecutor()
        executor.start()

        # Verify security kwargs were passed
        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["cap_drop"] == ["ALL"]
        assert call_kwargs["privileged"] is False
        assert call_kwargs["read_only"] is True
        assert "no-new-privileges:true" in call_kwargs["security_opt"]

        executor.stop()

    @patch("shesha.sandbox.executor.docker")
    def test_executor_accepts_custom_security(self, mock_docker: MagicMock) -> None:
        """Executor accepts custom security config."""
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container

        custom_security = ContainerSecurityConfig(cap_drop=["NET_ADMIN"])
        executor = ContainerExecutor(security=custom_security)
        executor.start()

        call_kwargs = mock_client.containers.run.call_args[1]
        assert call_kwargs["cap_drop"] == ["NET_ADMIN"]

        executor.stop()
