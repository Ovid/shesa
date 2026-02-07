#!/usr/bin/env python3
"""Sandbox runner - executes Python code in isolation."""

import json
import sys
import traceback
from io import StringIO
from typing import Any

# Global namespace for code execution (persists across executions)
NAMESPACE: dict[str, Any] = {}


def execute_code(code: str) -> dict[str, Any]:
    """Execute Python code and return results."""
    stdout_capture = StringIO()
    stderr_capture = StringIO()
    return_value = None
    error = None

    old_stdout = sys.stdout
    old_stderr = sys.stderr

    try:
        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Execute the code
        exec(code, NAMESPACE)

        # Check for special return values
        if "_return_value_" in NAMESPACE:
            return_value = NAMESPACE.pop("_return_value_")

    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    return {
        "status": "error" if error else "ok",
        "stdout": stdout_capture.getvalue(),
        "stderr": stderr_capture.getvalue(),
        "return_value": return_value,
        "error": error,
    }


def handle_llm_query(instruction: str, content: str) -> dict[str, Any]:
    """Request an LLM query from the host."""
    return {
        "action": "llm_query",
        "instruction": instruction,
        "content": content,
    }


def main() -> None:
    """Main loop: read JSON commands, execute, write JSON responses."""

    # Capture real stdout/stdin before any redirection happens during exec
    real_stdout = sys.stdout
    real_stdin = sys.stdin

    # Define FINAL and FINAL_VAR
    class FinalAnswer:
        def __init__(self, answer: str):
            self.answer = answer

    class FinalVar:
        def __init__(self, var_name: str):
            self.var_name = var_name

    def llm_query(instruction: str, content: str) -> str:
        """Request LLM query from host - blocks until response."""
        request = handle_llm_query(instruction, content)
        # Use real stdout, not the captured one during exec
        real_stdout.write(json.dumps(request) + "\n")
        real_stdout.flush()
        # Wait for response from host using real stdin
        response_line = real_stdin.readline()
        response = json.loads(response_line)
        if response.get("action") == "llm_response":
            if "error" in response:
                raise ValueError(str(response["error"]))
            return str(response["result"])
        raise RuntimeError(f"Unexpected response: {response}")

    def make_final(answer: str) -> FinalAnswer:
        """Create FinalAnswer and register it for detection."""
        fa = FinalAnswer(answer)
        NAMESPACE["_return_value_"] = fa
        return fa

    def make_final_var(var_name: str) -> FinalVar:
        """Create FinalVar and register it for detection."""
        fv = FinalVar(var_name)
        NAMESPACE["_return_value_"] = fv
        return fv

    def register_builtins() -> None:
        """Register built-in functions in the namespace."""
        NAMESPACE["llm_query"] = llm_query
        NAMESPACE["FINAL"] = make_final
        NAMESPACE["FINAL_VAR"] = make_final_var
        NAMESPACE["FinalAnswer"] = FinalAnswer
        NAMESPACE["FinalVar"] = FinalVar

    register_builtins()

    for line in sys.stdin:
        try:
            command = json.loads(line.strip())
            action = command.get("action")

            if action == "execute":
                result = execute_code(command["code"])
                # Check if return_value is a FinalAnswer or FinalVar
                rv = result.get("return_value")
                if isinstance(rv, FinalAnswer):
                    result["final_answer"] = rv.answer
                    result["return_value"] = None  # Not JSON serializable
                elif isinstance(rv, FinalVar):
                    result["final_var"] = rv.var_name
                    result["final_value"] = str(NAMESPACE.get(rv.var_name, ""))
                    result["return_value"] = None  # Not JSON serializable
                print(json.dumps(result), flush=True)

            elif action == "setup":
                # Initialize context variable
                NAMESPACE["context"] = command.get("context", [])
                print(json.dumps({"status": "ok"}), flush=True)

            elif action == "reset":
                NAMESPACE.clear()
                register_builtins()
                print(json.dumps({"status": "ok"}), flush=True)

            elif action == "ping":
                print(json.dumps({"status": "ok", "message": "pong"}), flush=True)

            else:
                err = {"status": "error", "error": f"Unknown action: {action}"}
                print(json.dumps(err), flush=True)

        except json.JSONDecodeError as e:
            print(json.dumps({"status": "error", "error": f"Invalid JSON: {e}"}), flush=True)
        except Exception as e:
            print(json.dumps({"status": "error", "error": str(e)}), flush=True)


if __name__ == "__main__":
    main()
