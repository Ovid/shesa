"""Tests for LLM client."""

from unittest.mock import MagicMock, patch

import pytest

from shesha.llm.client import LLMClient, LLMResponse
from shesha.llm.exceptions import PermanentError
from shesha.llm.retry import RetryConfig


class TestLLMClient:
    """Tests for LLMClient."""

    @patch("shesha.llm.client.litellm")
    def test_complete_returns_response(self, mock_litellm: MagicMock):
        """LLMClient.complete returns structured response."""
        mock_litellm.completion.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Hello!"))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

        client = LLMClient(model="gpt-4")
        response = client.complete(messages=[{"role": "user", "content": "Hi"}])

        assert isinstance(response, LLMResponse)
        assert response.content == "Hello!"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 5

    @patch("shesha.llm.client.litellm")
    def test_complete_with_system_prompt(self, mock_litellm: MagicMock):
        """LLMClient prepends system prompt to messages."""
        mock_litellm.completion.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Response"))],
            usage=MagicMock(prompt_tokens=20, completion_tokens=5, total_tokens=25),
        )

        client = LLMClient(model="gpt-4", system_prompt="You are helpful.")
        client.complete(messages=[{"role": "user", "content": "Hi"}])

        call_args = mock_litellm.completion.call_args
        messages = call_args.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."

    def test_client_stores_model(self):
        """LLMClient stores the model name."""
        client = LLMClient(model="claude-sonnet-4-20250514")
        assert client.model == "claude-sonnet-4-20250514"


class TestLLMClientRetry:
    """Tests for LLM client retry integration."""

    @patch("shesha.llm.client.litellm")
    def test_retries_on_rate_limit(self, mock_litellm: MagicMock) -> None:
        """Client retries on rate limit."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        # Import after patching
        from litellm.exceptions import RateLimitError as LiteLLMRateLimit

        mock_litellm.completion.side_effect = [
            LiteLLMRateLimit("rate limited", "model", None),
            mock_response,
        ]

        client = LLMClient(
            model="test-model",
            retry_config=RetryConfig(max_retries=2, base_delay=0.001),
        )
        result = client.complete(messages=[{"role": "user", "content": "test"}])

        assert result.content == "response"
        assert mock_litellm.completion.call_count == 2

    @patch("shesha.llm.client.litellm")
    def test_no_retry_on_auth_error(self, mock_litellm: MagicMock) -> None:
        """Client doesn't retry on auth error (4xx)."""
        from litellm.exceptions import AuthenticationError

        mock_litellm.completion.side_effect = AuthenticationError("invalid key", "model", None)

        client = LLMClient(
            model="test-model",
            retry_config=RetryConfig(max_retries=2),
        )

        with pytest.raises(PermanentError):
            client.complete(messages=[{"role": "user", "content": "test"}])

        assert mock_litellm.completion.call_count == 1
