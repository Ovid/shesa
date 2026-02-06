"""Tests for sandbox executor."""

import time
from unittest.mock import MagicMock, patch

import pytest

from shesha.sandbox.executor import ContainerExecutor, ExecutionResult
from shesha.security.containers import ContainerSecurityConfig


class TestProtocolError:
    """Tests for ProtocolError exception."""

    def test_protocol_error_exists(self):
        """ProtocolError is importable from executor module."""
        from shesha.sandbox.executor import ProtocolError

        err = ProtocolError("test message")
        assert str(err) == "test message"


class TestProtocolLimits:
    """Tests for protocol limit constants."""

    def test_max_buffer_size_exists(self):
        """MAX_BUFFER_SIZE constant is defined."""
        from shesha.sandbox.executor import MAX_BUFFER_SIZE

        assert MAX_BUFFER_SIZE == 10 * 1024 * 1024  # 10 MB

    def test_max_line_length_exists(self):
        """MAX_LINE_LENGTH constant is defined."""
        from shesha.sandbox.executor import MAX_LINE_LENGTH

        assert MAX_LINE_LENGTH == 1 * 1024 * 1024  # 1 MB

    def test_max_read_duration_exists(self):
        """MAX_READ_DURATION constant is defined."""
        from shesha.sandbox.executor import MAX_READ_DURATION

        assert MAX_READ_DURATION == 300  # 5 minutes


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


class TestBufferLimits:
    """Tests for buffer size limits in _read_line."""

    def test_read_line_raises_on_oversized_data_without_newline(self):
        """_read_line raises ProtocolError when data exceeds limits without newline."""
        from shesha.sandbox.executor import MAX_BUFFER_SIZE, ProtocolError

        mock_socket = MagicMock()
        # Send chunks that would exceed MAX_BUFFER_SIZE without a newline
        # Note: This will now hit MAX_LINE_LENGTH (1MB) before MAX_BUFFER_SIZE (10MB)
        # since we check line length for streaming data without newlines
        chunk_size = 1024 * 1024  # 1 MB chunks
        chunks_needed = (MAX_BUFFER_SIZE // chunk_size) + 2

        chunk_data = [b"x" * chunk_size for _ in range(chunks_needed)]
        chunk_iter = iter(chunk_data)

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

        with pytest.raises(ProtocolError) as exc_info:
            executor._read_line(timeout=5)

        # Either buffer overflow or line length limit - both protect against DoS
        error_msg = str(exc_info.value).lower()
        assert "buffer" in error_msg or "line" in error_msg


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


class TestLineLengthLimit:
    """Tests for line length limit in _read_line."""

    def test_read_line_raises_on_oversized_line(self):
        """_read_line raises ProtocolError when line exceeds MAX_LINE_LENGTH."""
        from shesha.sandbox.executor import (
            MAX_LINE_LENGTH,
            ContainerExecutor,
            ProtocolError,
        )

        mock_socket = MagicMock()

        # Create a line that exceeds MAX_LINE_LENGTH
        oversized_line = b"x" * (MAX_LINE_LENGTH + 100) + b"\n"
        frame = make_docker_frame(oversized_line)

        chunks = [frame]
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

        with pytest.raises(ProtocolError) as exc_info:
            executor._read_line(timeout=5)

        assert "line" in str(exc_info.value).lower()

    def test_read_line_raises_on_streaming_oversized_line_without_newline(self):
        """_read_line raises when data streams past MAX_LINE_LENGTH without newline."""
        from shesha.sandbox.executor import (
            MAX_LINE_LENGTH,
            ContainerExecutor,
            ProtocolError,
        )

        mock_socket = MagicMock()

        # Stream chunks without newline that total > MAX_LINE_LENGTH
        chunk_size = 100_000  # 100KB chunks
        chunks_needed = (MAX_LINE_LENGTH // chunk_size) + 2  # Exceed limit
        chunk_data = b"x" * chunk_size
        chunks_sent = 0

        def mock_recv(size):
            nonlocal chunks_sent
            if chunks_sent < chunks_needed:
                chunks_sent += 1
                # Return Docker-framed data without newline
                return make_docker_frame(chunk_data)
            # Keep connection open (don't return b"")
            time.sleep(0.1)
            return make_docker_frame(chunk_data)

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with pytest.raises(ProtocolError) as exc_info:
            executor._read_line(timeout=5)

        assert "line" in str(exc_info.value).lower()


class TestReadDeadline:
    """Tests for overall deadline in _read_line."""

    def test_read_line_raises_on_deadline_exceeded(self):
        """_read_line raises ProtocolError when total time exceeds MAX_READ_DURATION."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        mock_socket = MagicMock()

        # Simulate slow drip that would exceed deadline
        call_count = 0

        def mock_recv(size):
            nonlocal call_count
            call_count += 1
            # Return small chunks without newline
            if call_count < 100:
                return b"x"
            return b""

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # Patch time.monotonic (not time.time) to simulate elapsed time exceeding deadline
        # Using monotonic avoids issues with wall-clock jumps (NTP, manual changes)
        start_time = time.monotonic()
        call_sequence = [start_time, start_time + 301]  # 301 seconds elapsed
        time_iter = iter(call_sequence)

        def mock_monotonic():
            try:
                return next(time_iter)
            except StopIteration:
                return start_time + 400

        with patch("shesha.sandbox.executor.time.monotonic", mock_monotonic):
            with pytest.raises(ProtocolError) as exc_info:
                executor._read_line(timeout=5)

        assert (
            "duration" in str(exc_info.value).lower() or "deadline" in str(exc_info.value).lower()
        )

    def test_read_line_enforces_deadline_in_inner_frame_loop(self):
        """_read_line enforces deadline inside Docker frame reading loop.

        This tests that the deadline is checked inside the inner loop that reads
        Docker frame payloads, not just at the outer loop start. A malicious
        container could drip data slowly to keep the inner loop spinning.
        """
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        mock_socket = MagicMock()

        # Simulate a large Docker frame that drips in slowly
        # Header says 10000 bytes, but we drip small chunks
        header = bytes([1, 0, 0, 0, 0, 0, 0x27, 0x10])  # stream=1, length=10000
        recv_count = 0

        def mock_recv(size):
            nonlocal recv_count
            recv_count += 1
            if recv_count == 1:
                return header  # Send header first
            # Then drip payload in small chunks (simulating slow attack)
            # This keeps us in the inner frame-reading loop
            return b"x" * 10  # Small chunk, need many to reach 10000

        mock_socket._sock.recv = mock_recv
        mock_socket._sock.settimeout = MagicMock()

        executor = ContainerExecutor()
        executor._socket = mock_socket
        executor._raw_buffer = b""
        executor._content_buffer = b""

        # Time: first check passes, subsequent checks inside inner loop should fail
        start_time = 1000.0
        monotonic_calls = 0

        def mock_monotonic():
            nonlocal monotonic_calls
            monotonic_calls += 1
            if monotonic_calls <= 2:
                # First two calls: outer loop check and inner loop entry
                return start_time
            # After that: simulate time has exceeded deadline
            # This should be caught inside the inner loop
            return start_time + 301

        with patch("shesha.sandbox.executor.time.monotonic", mock_monotonic):
            with pytest.raises(ProtocolError) as exc_info:
                executor._read_line(timeout=5)

        assert "duration" in str(exc_info.value).lower()


class TestExecuteProtocolHandling:
    """Tests for ProtocolError handling in execute()."""

    def test_execute_returns_error_result_on_protocol_error(self):
        """execute() returns error ExecutionResult when ProtocolError occurs."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Mock _read_line to raise ProtocolError
        with patch.object(executor, "_read_line", side_effect=ProtocolError("buffer overflow")):
            with patch.object(executor, "_send_raw"):
                result = executor.execute("print('hello')")

        assert result.status == "error"
        assert "protocol" in result.error.lower() or "buffer" in result.error.lower()

    def test_execute_stops_container_on_protocol_error(self):
        """execute() stops the container when ProtocolError occurs."""
        from shesha.sandbox.executor import ContainerExecutor, ProtocolError

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Mock _read_line to raise ProtocolError and track stop() call
        with patch.object(executor, "_read_line", side_effect=ProtocolError("malicious data")):
            with patch.object(executor, "_send_raw"):
                with patch.object(executor, "stop") as mock_stop:
                    executor.execute("print('hello')")

        # Container should be stopped after protocol violation
        mock_stop.assert_called_once()

    def test_execute_handles_invalid_json_as_protocol_error(self):
        """execute() treats invalid JSON from container as protocol violation."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Container returns invalid JSON (e.g., sandbox wrote to sys.__stdout__)
        with patch.object(executor, "_read_line", return_value="not valid json {{{"):
            with patch.object(executor, "_send_raw"):
                with patch.object(executor, "stop") as mock_stop:
                    result = executor.execute("print('hello')")

        # Should return error result, not raise JSONDecodeError
        assert result.status == "error"
        assert "json" in result.error.lower() or "protocol" in result.error.lower()
        # Container should be stopped (invalid output = compromised state)
        mock_stop.assert_called_once()

    def test_execute_handles_malformed_llm_query_as_protocol_error(self):
        """execute() treats llm_query missing required fields as protocol violation."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        executor._socket = MagicMock()
        # Set a handler so we actually try to access the fields
        executor.llm_query_handler = MagicMock()

        # Malformed llm_query - missing 'instruction' and 'content' fields
        malformed_response = '{"action": "llm_query"}'

        with patch.object(executor, "_read_line", return_value=malformed_response):
            with patch.object(executor, "_send_raw"):
                with patch.object(executor, "stop") as mock_stop:
                    result = executor.execute("print('hello')")

        # Should return error result, not raise KeyError
        assert result.status == "error"
        assert "protocol" in result.error.lower() or "missing" in result.error.lower()
        # Container should be stopped
        mock_stop.assert_called_once()

    def test_execute_handles_non_utf8_as_protocol_error(self):
        """execute() treats non-UTF8 bytes from container as protocol violation."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        executor._socket = MagicMock()

        # Container sends invalid UTF-8 bytes (e.g., via sys.stdout.buffer)
        # \xff\xfe is invalid UTF-8
        invalid_utf8 = b'\xff\xfe{"status": "ok"}\n'
        frame = make_docker_frame(invalid_utf8)

        chunks = [frame]
        chunk_iter = iter(chunks)

        def mock_recv(size):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        executor._socket._sock.recv = mock_recv
        executor._socket._sock.settimeout = MagicMock()
        executor._raw_buffer = b""
        executor._content_buffer = b""

        with patch.object(executor, "_send_raw"):
            with patch.object(executor, "stop") as mock_stop:
                result = executor.execute("print('hello')")

        # Should return error result, not raise UnicodeDecodeError
        assert result.status == "error"
        assert "protocol" in result.error.lower() or "decode" in result.error.lower()
        # Container should be stopped
        mock_stop.assert_called_once()

    def test_execute_returns_error_when_socket_is_none(self):
        """execute() returns error result when called after stop() (no socket)."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()
        # Simulate stopped state - socket is None
        executor._socket = None

        result = executor.execute("print('hello')")

        # Should return error result, not raise RuntimeError
        assert result.status == "error"
        assert "stopped" in result.error.lower() or "socket" in result.error.lower()


class TestResetNamespace:
    """Tests for namespace reset in executor."""

    def test_reset_namespace_sends_reset_action(self):
        """reset_namespace() sends {"action": "reset"} to container."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()

        with patch.object(executor, "_send_command", return_value={"status": "ok"}) as mock_cmd:
            executor.reset_namespace()

        mock_cmd.assert_called_once_with({"action": "reset"})

    def test_reset_namespace_returns_response(self):
        """reset_namespace() returns the response from the container."""
        from shesha.sandbox.executor import ContainerExecutor

        executor = ContainerExecutor()

        with patch.object(executor, "_send_command", return_value={"status": "ok"}):
            result = executor.reset_namespace()

        assert result == {"status": "ok"}
