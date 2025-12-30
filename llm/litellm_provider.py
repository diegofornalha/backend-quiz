"""LiteLLM Provider implementation for Gemini."""

from collections.abc import AsyncIterator
from typing import Any

import litellm
from litellm import acompletion

from .provider import LLMProvider, LLMResponse, Message, StreamChunk, Tool


class LiteLLMProvider(LLMProvider):
    """LLM Provider using LiteLLM for Gemini and other models.

    Example:
        >>> provider = LiteLLMProvider(model="gemini/gemini-2.0-flash")
        >>> response = await provider.completion([
        ...     {"role": "user", "content": "Hello!"}
        ... ])
        >>> print(response.content)
    """

    def __init__(
        self,
        model: str = "gemini/gemini-2.0-flash",
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        """Initialize LiteLLM provider.

        Args:
            model: Model identifier (e.g., "gemini/gemini-2.0-flash", "gpt-4")
            api_key: API key (uses env var if not provided)
            timeout: Request timeout in seconds
            max_retries: Number of retries on failure
        """
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries

        # Configure LiteLLM
        litellm.set_verbose = False

    @property
    def model_name(self) -> str:
        """Get the model name being used."""
        return self._model

    def _normalize_messages(self, messages: list[Message | dict]) -> list[dict]:
        """Convert messages to dict format."""
        result = []
        for msg in messages:
            if isinstance(msg, Message):
                m = {"role": msg.role, "content": msg.content}
                if msg.name:
                    m["name"] = msg.name
                if msg.tool_call_id:
                    m["tool_call_id"] = msg.tool_call_id
                result.append(m)
            else:
                result.append(msg)
        return result

    def _normalize_tools(self, tools: list[Tool | dict]) -> list[dict]:
        """Convert tools to dict format."""
        result = []
        for tool in tools:
            if isinstance(tool, Tool):
                result.append(tool.to_dict())
            else:
                result.append(tool)
        return result

    async def completion(
        self,
        messages: list[Message | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given messages."""
        normalized_messages = self._normalize_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": normalized_messages,
            "temperature": temperature,
            "timeout": self._timeout,
            "num_retries": self._max_retries,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if stop:
            kwargs["stop"] = stop
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = await acompletion(**kwargs)

        # Extract content
        content = ""
        tool_calls = None

        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            if choice.message.content:
                content = choice.message.content
            if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]

        # Extract usage
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            model=self._model,
            finish_reason=response.choices[0].finish_reason if response.choices else None,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )

    async def completion_stream(
        self,
        messages: list[Message | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Generate a streaming completion."""
        normalized_messages = self._normalize_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": normalized_messages,
            "temperature": temperature,
            "timeout": self._timeout,
            "num_retries": self._max_retries,
            "stream": True,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if stop:
            kwargs["stop"] = stop
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = await acompletion(**kwargs)

        async for chunk in response:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            text = None
            if hasattr(delta, "content") and delta.content:
                text = delta.content

            tool_calls = None
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id if hasattr(tc, "id") else None,
                        "type": tc.type if hasattr(tc, "type") else "function",
                        "function": {
                            "name": tc.function.name if hasattr(tc.function, "name") else None,
                            "arguments": (
                                tc.function.arguments if hasattr(tc.function, "arguments") else ""
                            ),
                        },
                    }
                    for tc in delta.tool_calls
                ]

            # Extract usage from final chunk if available
            usage = None
            if hasattr(chunk, "usage") and chunk.usage:
                usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "total_tokens": chunk.usage.total_tokens,
                }

            yield StreamChunk(
                text=text,
                finish_reason=choice.finish_reason,
                tool_calls=tool_calls,
                usage=usage,
            )

    async def completion_with_tools(
        self,
        messages: list[Message | dict],
        tools: list[Tool | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """Generate completion with tool/function calling."""
        normalized_messages = self._normalize_messages(messages)
        normalized_tools = self._normalize_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": normalized_messages,
            "tools": normalized_tools,
            "tool_choice": tool_choice,
            "temperature": temperature,
            "timeout": self._timeout,
            "num_retries": self._max_retries,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if self._api_key:
            kwargs["api_key"] = self._api_key

        response = await acompletion(**kwargs)

        # Extract content and tool calls
        content = ""
        tool_calls = None

        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            if choice.message.content:
                content = choice.message.content
            if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]

        # Extract usage
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            model=self._model,
            finish_reason=response.choices[0].finish_reason if response.choices else None,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
        )


# Singleton instance for convenience
_default_provider: LiteLLMProvider | None = None


def get_provider(model: str | None = None) -> LiteLLMProvider:
    """Get or create LiteLLM provider instance.

    Args:
        model: Optional model override

    Returns:
        LiteLLMProvider instance
    """
    global _default_provider

    if model:
        return LiteLLMProvider(model=model)

    if _default_provider is None:
        from .config import get_llm_config

        config = get_llm_config()
        _default_provider = LiteLLMProvider(model=config.model)

    return _default_provider
