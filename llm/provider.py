"""Abstract LLM Provider interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamChunk:
    """Represents a streaming chunk from LLM."""

    text: str | None = None
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict | None = None

    @property
    def is_done(self) -> bool:
        """Check if this is the final chunk."""
        return self.finish_reason is not None


@dataclass
class LLMResponse:
    """Complete response from LLM."""

    content: str
    model: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict | None = None
    raw_response: Any = None


@dataclass
class Message:
    """Chat message."""

    role: str  # "system", "user", "assistant", "tool"
    content: str | list[dict]
    name: str | None = None
    tool_call_id: str | None = None


@dataclass
class Tool:
    """Tool definition for function calling."""

    name: str
    description: str
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to OpenAI-compatible tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Implementations should handle:
    - Basic completion
    - Streaming completion
    - Tool/function calling
    - Error handling and retries
    """

    @abstractmethod
    async def completion(
        self,
        messages: list[Message | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion for the given messages.

        Args:
            messages: List of chat messages
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            stop: Stop sequences

        Returns:
            LLMResponse with generated content
        """
        ...

    @abstractmethod
    async def completion_stream(
        self,
        messages: list[Message | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Generate a streaming completion.

        Args:
            messages: List of chat messages
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            stop: Stop sequences

        Yields:
            StreamChunk with incremental content
        """
        ...

    @abstractmethod
    async def completion_with_tools(
        self,
        messages: list[Message | dict],
        tools: list[Tool | dict],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """Generate completion with tool/function calling.

        Args:
            messages: List of chat messages
            tools: List of available tools
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tool_choice: "auto", "required", or specific tool name

        Returns:
            LLMResponse with content and/or tool_calls
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name being used."""
        ...
