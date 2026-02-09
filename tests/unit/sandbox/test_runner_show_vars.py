"""Tests for SHOW_VARS sandbox function."""

from shesha.sandbox.runner import NAMESPACE, execute_code


class TestShowVars:
    """Tests for show_vars function."""

    def setup_method(self) -> None:
        """Clear namespace before each test."""
        NAMESPACE.clear()

    def test_show_vars_returns_user_variables(self) -> None:
        """SHOW_VARS returns user-created variables, not builtins."""
        from shesha.sandbox.runner import show_vars

        # Simulate builtins
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        # Create user variable via execute_code
        execute_code("my_var = 42")

        result = show_vars()
        assert "my_var" in result
        assert "llm_query" not in result
        assert "FINAL" not in result
        assert "SHOW_VARS" not in result
        assert "context" not in result

    def test_show_vars_empty_namespace(self) -> None:
        """SHOW_VARS returns helpful message when no user vars exist."""
        from shesha.sandbox.runner import show_vars

        # Only builtins
        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        result = show_vars()
        assert "No variables created yet" in result

    def test_show_vars_shows_types(self) -> None:
        """SHOW_VARS includes variable types."""
        from shesha.sandbox.runner import show_vars

        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        execute_code("x = 42\ny = 'hello'")

        result = show_vars()
        assert "int" in result
        assert "str" in result

    def test_show_vars_excludes_private_vars(self) -> None:
        """SHOW_VARS excludes variables starting with underscore."""
        from shesha.sandbox.runner import show_vars

        NAMESPACE["llm_query"] = lambda x: x
        NAMESPACE["FINAL"] = lambda x: x
        NAMESPACE["FINAL_VAR"] = lambda x: x
        NAMESPACE["SHOW_VARS"] = show_vars
        NAMESPACE["FinalAnswer"] = type("FinalAnswer", (), {})
        NAMESPACE["FinalVar"] = type("FinalVar", (), {})
        NAMESPACE["context"] = ["doc"]

        execute_code("_private = 'hidden'\npublic = 'visible'")

        result = show_vars()
        assert "_private" not in result
        assert "public" in result
