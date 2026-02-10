"""Tests for sandbox runner."""

import io
import json
import struct

from shesha.sandbox.runner import NAMESPACE, execute_code


def frame_message(data: dict) -> bytes:
    """Create a length-prefixed message frame for testing."""
    payload = json.dumps(data).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class TestExecuteCode:
    """Tests for execute_code function."""

    def setup_method(self) -> None:
        """Clear namespace before each test."""
        NAMESPACE.clear()

    def test_execute_code_runs_python(self) -> None:
        """execute_code runs Python code and captures stdout."""
        result = execute_code("print('hello')")
        assert result["status"] == "ok"
        assert result["stdout"] == "hello\n"

    def test_execute_code_persists_namespace(self) -> None:
        """Variables set in one execute_code call persist to the next."""
        execute_code("x = 42")
        result = execute_code("print(x)")
        assert result["stdout"] == "42\n"


class TestResetAction:
    """Tests for the reset action in the runner main loop."""

    def test_reset_action_returns_ok(self) -> None:
        """Sending reset action returns {"status": "ok"}."""
        # We test by invoking the runner protocol directly via stdin/stdout
        # Simulate: setup builtins, set a var, send reset, check response
        import io
        import sys

        from shesha.sandbox.runner import main

        commands = [
            json.dumps({"action": "reset"}) + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        response = json.loads(output_lines[0])
        assert response["status"] == "ok"

    def test_reset_clears_user_vars_but_keeps_builtins(self) -> None:
        """Reset clears user-defined vars but preserves FINAL/llm_query."""
        import io
        import sys

        from shesha.sandbox.runner import main

        commands = [
            json.dumps({"action": "execute", "code": "user_var = 'secret'"}) + "\n",
            json.dumps({"action": "reset"}) + "\n",
            json.dumps({"action": "execute", "code": "print('user_var' in dir())"}) + "\n",
            json.dumps({"action": "execute", "code": "print(callable(FINAL))"}) + "\n",
            json.dumps({"action": "execute", "code": "print(callable(llm_query))"}) + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        # Line 0: execute result (setting user_var)
        # Line 1: reset result
        # Line 2: execute result (checking user_var gone)
        # Line 3: execute result (checking FINAL exists)
        # Line 4: execute result (checking llm_query exists)

        execute_after_reset = json.loads(output_lines[2])
        assert execute_after_reset["stdout"] == "False\n", "user_var should be cleared"

        final_check = json.loads(output_lines[3])
        assert final_check["stdout"] == "True\n", "FINAL should still exist"

        llm_query_check = json.loads(output_lines[4])
        assert llm_query_check["stdout"] == "True\n", "llm_query should still exist"


class TestRunnerInvalidJson:
    """Tests for runner handling of invalid JSON input."""

    def test_runner_exits_on_invalid_json(self) -> None:
        """Runner breaks out of main loop on JSONDecodeError (fail-closed)."""
        import io
        import sys

        from shesha.sandbox.runner import main

        commands = [
            json.dumps({"action": "ping"}) + "\n",
            "this is not valid json\n",
            json.dumps({"action": "ping"}) + "\n",  # Should NOT be processed
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        # First ping should succeed
        first = json.loads(output_lines[0])
        assert first["status"] == "ok"
        # Runner should have stopped after invalid JSON — no third ping response
        assert len(output_lines) == 1, (
            f"Expected only 1 response (runner should exit on invalid JSON), "
            f"got {len(output_lines)}: {output_lines}"
        )


class TestLlmQueryErrorHandling:
    """Tests for llm_query() error response handling."""

    def test_llm_query_raises_on_error_response(self) -> None:
        """llm_query() raises ValueError when host sends error field."""
        import io
        import sys

        from shesha.sandbox.runner import main

        error_msg = "Content size (735,490 chars) exceeds the sub-LLM limit"

        # The runner reads lines from stdin in sequence:
        # 1. {"action": "execute", "code": "result = llm_query('x', 'y')"}
        # 2. (llm_query writes request to stdout, then reads next line from stdin)
        # 3. {"action": "llm_response", "error": "Content size..."}
        # 4. (code raises ValueError, execute_code returns error result)

        error_response = json.dumps({"action": "llm_response", "error": error_msg})
        commands = [
            json.dumps({"action": "execute", "code": "result = llm_query('summarize', 'big')"})
            + "\n",
            error_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        # First line: the llm_query request from the sandbox
        llm_request = json.loads(output_lines[0])
        assert llm_request["action"] == "llm_query"
        # Second line: the execute result (should be error from ValueError)
        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "error"
        assert "ValueError" in exec_result["error"]
        assert error_msg in exec_result["error"]

    def test_llm_query_succeeds_on_normal_response(self) -> None:
        """llm_query() returns result string when response has no error field."""
        import io
        import sys

        from shesha.sandbox.runner import main

        normal_response = json.dumps({"action": "llm_response", "result": "Analysis complete"})
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": "result = llm_query('summarize', 'content')\nprint(result)",
                }
            )
            + "\n",
            normal_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        # First line: the llm_query request
        llm_request = json.loads(output_lines[0])
        assert llm_request["action"] == "llm_query"
        # Second line: the execute result (should be ok)
        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "ok"
        assert "Analysis complete" in exec_result["stdout"]


class TestLlmQueryOptionalContent:
    """Tests for llm_query() with optional content argument."""

    def test_llm_query_single_arg_sends_empty_content(self) -> None:
        """llm_query('prompt') sends empty string as content field."""
        import io
        import sys

        from shesha.sandbox.runner import main

        normal_response = json.dumps({"action": "llm_response", "result": "42"})
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": "result = llm_query('What is the answer?')\nprint(result)",
                }
            )
            + "\n",
            normal_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        llm_request = json.loads(output_lines[0])
        assert llm_request["action"] == "llm_query"
        assert llm_request["instruction"] == "What is the answer?"
        assert llm_request["content"] == ""

        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "ok"
        assert "42" in exec_result["stdout"]

    def test_llm_query_two_args_still_works(self) -> None:
        """llm_query('instruction', 'content') still sends both fields."""
        import io
        import sys

        from shesha.sandbox.runner import main

        normal_response = json.dumps({"action": "llm_response", "result": "done"})
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": "result = llm_query('classify', 'some data')\nprint(result)",
                }
            )
            + "\n",
            normal_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        llm_request = json.loads(output_lines[0])
        assert llm_request["action"] == "llm_query"
        assert llm_request["instruction"] == "classify"
        assert llm_request["content"] == "some data"


class TestLlmQueryBatched:
    """Tests for llm_query_batched() function."""

    def test_llm_query_batched_sends_batch_request(self) -> None:
        """llm_query_batched sends a batch action with all prompts."""
        import io
        import sys

        from shesha.sandbox.runner import main

        batch_response = json.dumps(
            {"action": "llm_batch_response", "results": ["cat", "dog", "bird"]}
        )
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": (
                        "results = llm_query_batched("
                        "['classify: cat', 'classify: dog', 'classify: bird'])\n"
                        "print(results)"
                    ),
                }
            )
            + "\n",
            batch_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        batch_request = json.loads(output_lines[0])
        assert batch_request["action"] == "llm_query_batch"
        assert batch_request["prompts"] == ["classify: cat", "classify: dog", "classify: bird"]

        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "ok"
        assert "cat" in exec_result["stdout"]
        assert "dog" in exec_result["stdout"]
        assert "bird" in exec_result["stdout"]

    def test_llm_query_batched_raises_on_error(self) -> None:
        """llm_query_batched raises ValueError when host sends error."""
        import io
        import sys

        from shesha.sandbox.runner import main

        error_response = json.dumps({"action": "llm_batch_response", "error": "Batch failed"})
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": "results = llm_query_batched(['prompt1'])",
                }
            )
            + "\n",
            error_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "error"
        assert "ValueError" in exec_result["error"]

    def test_llm_query_batched_preserves_order(self) -> None:
        """llm_query_batched returns results in same order as prompts."""
        import io
        import sys

        from shesha.sandbox.runner import main

        batch_response = json.dumps(
            {"action": "llm_batch_response", "results": ["first", "second", "third"]}
        )
        commands = [
            json.dumps(
                {
                    "action": "execute",
                    "code": (
                        "results = llm_query_batched(['a', 'b', 'c'])\n"
                        "for i, r in enumerate(results):\n"
                        "    print(f'{i}:{r}')"
                    ),
                }
            )
            + "\n",
            batch_response + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "ok"
        assert "0:first" in exec_result["stdout"]
        assert "1:second" in exec_result["stdout"]
        assert "2:third" in exec_result["stdout"]

    def test_llm_query_batched_available_after_reset(self) -> None:
        """llm_query_batched persists after namespace reset."""
        import io
        import sys

        from shesha.sandbox.runner import main

        commands = [
            json.dumps({"action": "reset"}) + "\n",
            json.dumps({"action": "execute", "code": "print(callable(llm_query_batched))"}) + "\n",
        ]
        stdin = io.StringIO("".join(commands))
        stdout = io.StringIO()

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        try:
            sys.stdin = stdin
            sys.stdout = stdout
            main()
        finally:
            sys.stdin = old_stdin
            sys.stdout = old_stdout

        output_lines = stdout.getvalue().strip().split("\n")
        exec_result = json.loads(output_lines[1])
        assert exec_result["status"] == "ok"
        assert exec_result["stdout"] == "True\n"


class TestLengthPrefixHelpers:
    """Tests for length-prefix protocol helpers."""

    def test_read_message_reads_length_prefixed_json(self) -> None:
        """_read_message reads 4-byte BE length prefix then exact payload."""
        from shesha.sandbox.runner import _read_message

        data = {"action": "execute", "code": "print('hello')"}
        stream = io.BytesIO(frame_message(data))
        result = _read_message(stream)
        assert result == data

    def test_read_message_handles_large_payload(self) -> None:
        """_read_message handles payloads larger than typical buffers."""
        from shesha.sandbox.runner import _read_message

        data = {"action": "llm_response", "result": "x" * 100_000}
        stream = io.BytesIO(frame_message(data))
        result = _read_message(stream)
        assert result == data

    def test_write_message_writes_length_prefixed_json(self) -> None:
        """_write_message writes 4-byte BE length prefix + JSON payload."""
        from shesha.sandbox.runner import _write_message

        data = {"status": "ok", "stdout": "hello\n"}
        stream = io.BytesIO()
        _write_message(stream, data)
        written = stream.getvalue()

        # Verify length prefix
        length = struct.unpack(">I", written[:4])[0]
        payload = written[4:]
        assert len(payload) == length
        assert json.loads(payload.decode("utf-8")) == data

    def test_write_message_flushes_stream(self) -> None:
        """_write_message calls flush() on the stream."""
        from unittest.mock import MagicMock

        from shesha.sandbox.runner import _write_message

        mock_stream = MagicMock()
        _write_message(mock_stream, {"status": "ok"})
        mock_stream.flush.assert_called_once()

    def test_read_exactly_raises_on_eof(self) -> None:
        """_read_exactly raises ConnectionError on EOF mid-read."""
        from shesha.sandbox.runner import _read_exactly

        stream = io.BytesIO(b"abc")  # Only 3 bytes
        with __import__("pytest").raises(ConnectionError, match="Connection closed"):
            _read_exactly(stream, 10)  # Ask for 10

    def test_read_exactly_reads_exact_bytes(self) -> None:
        """_read_exactly reads exactly n bytes from stream."""
        from shesha.sandbox.runner import _read_exactly

        stream = io.BytesIO(b"hello world")
        result = _read_exactly(stream, 5)
        assert result == b"hello"

    def test_read_message_multiple_messages(self) -> None:
        """_read_message reads only one message, leaving rest in stream."""
        from shesha.sandbox.runner import _read_message

        msg1 = {"action": "ping"}
        msg2 = {"action": "reset"}
        stream = io.BytesIO(frame_message(msg1) + frame_message(msg2))

        result1 = _read_message(stream)
        assert result1 == msg1

        result2 = _read_message(stream)
        assert result2 == msg2
