"""Tests for analysis shortcut — skip RLM when analysis can answer."""

from unittest.mock import MagicMock, patch

from shesha.analysis.shortcut import try_answer_from_analysis


class TestTryAnswerFromAnalysis:
    """Tests for try_answer_from_analysis()."""

    def test_returns_answer_when_llm_can_answer(self):
        """When LLM returns a real answer, function returns answer with token counts."""
        mock_response = MagicMock()
        mock_response.content = "This codebase implements a web framework."
        mock_response.prompt_tokens = 100
        mock_response.completion_tokens = 20

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="What does this codebase do?",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
            )

        assert result == ("This codebase implements a web framework.", 100, 20)

    def test_returns_none_when_need_deeper(self):
        """When LLM returns NEED_DEEPER, function returns None."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="Find race conditions in the executor",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
            )

        assert result is None

    def test_returns_none_when_need_deeper_with_whitespace(self):
        """NEED_DEEPER with trailing whitespace still returns None."""
        mock_response = MagicMock()
        mock_response.content = "NEED_DEEPER\n"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.return_value = mock_response
            result = try_answer_from_analysis(
                question="Any question",
                analysis_context="Some analysis",
                model="test-model",
                api_key="test-key",
            )

        assert result is None

    def test_returns_none_when_analysis_context_is_none(self):
        """No analysis context -> None immediately, no LLM call."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context=None,
                model="test-model",
                api_key="test-key",
            )

        mock_cls.assert_not_called()
        assert result is None

    def test_returns_none_when_analysis_context_is_empty(self):
        """Empty string analysis context -> None immediately, no LLM call."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context="",
                model="test-model",
                api_key="test-key",
            )

        mock_cls.assert_not_called()
        assert result is None

    def test_wraps_analysis_in_untrusted_tags(self):
        """Prompt sent to LLM wraps analysis in <untrusted_document_content> tags."""
        mock_response = MagicMock()
        mock_response.content = "Some answer"

        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.complete.return_value = mock_response
            try_answer_from_analysis(
                question="What does this do?",
                analysis_context="Overview: A web framework...",
                model="test-model",
                api_key="test-key",
            )

        # Check the user message sent to complete()
        call_args = mock_client.complete.call_args
        messages = call_args[0][0]
        user_content = messages[0]["content"]
        assert "<untrusted_document_content>" in user_content
        assert "</untrusted_document_content>" in user_content
        assert "Overview: A web framework..." in user_content

    def test_returns_none_on_llm_error(self):
        """LLM exception -> None (graceful fallback)."""
        with patch("shesha.analysis.shortcut.LLMClient") as mock_cls:
            mock_cls.return_value.complete.side_effect = Exception("API error")
            result = try_answer_from_analysis(
                question="What does this do?",
                analysis_context="Some analysis",
                model="test-model",
                api_key="test-key",
            )

        assert result is None
