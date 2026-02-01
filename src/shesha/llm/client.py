"""LLM client wrapper using LiteLLM."""

from dataclasses import dataclass
from typing import Any

import litellm


@dataclass
class LLMResponse:
    """Response from an LLM completion."""

    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    raw_response: Any = None


class LLMClient:
    """Wrapper around LiteLLM for unified LLM access."""

    def __init__(
        self,
        model: str,
        system_prompt: str | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the LLM client."""
        self.model = model
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.extra_kwargs = kwargs

    def complete(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to the LLM."""
        full_messages = list(messages)
        if self.system_prompt:
            full_messages.insert(0, {"role": "system", "content": self.system_prompt})

        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": full_messages,
            **self.extra_kwargs,
            **kwargs,
        }
        if self.api_key:
            call_kwargs["api_key"] = self.api_key

        response = litellm.completion(**call_kwargs)

        return LLMResponse(
            content=response.choices[0].message.content,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            raw_response=response,
        )
