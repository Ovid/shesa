"""Tests for sandbox runner."""

import json

from shesha.sandbox.runner import NAMESPACE, execute_code


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
