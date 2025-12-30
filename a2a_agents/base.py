"""Base Agent Executor for A2A-compatible agents."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from llm import LiteLLMProvider


@dataclass
class AgentMessage:
    """Message in agent conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentEvent:
    """Event emitted by agent during execution."""

    type: str  # "text", "tool_call", "status", "error", "done"
    data: Any = None
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def text(content: str) -> "AgentEvent":
        """Create text event."""
        return AgentEvent(type="text", data=content)

    @staticmethod
    def status(state: str, message: str | None = None) -> "AgentEvent":
        """Create status event."""
        return AgentEvent(type="status", data={"state": state, "message": message})

    @staticmethod
    def tool_call(name: str, args: dict, result: Any = None) -> "AgentEvent":
        """Create tool call event."""
        return AgentEvent(type="tool_call", data={"name": name, "args": args, "result": result})

    @staticmethod
    def error(message: str) -> "AgentEvent":
        """Create error event."""
        return AgentEvent(type="error", data=message)

    @staticmethod
    def done() -> "AgentEvent":
        """Create done event."""
        return AgentEvent(type="done")


@dataclass
class AgentContext:
    """Context for agent execution."""

    session_id: str
    message: AgentMessage
    history: list[AgentMessage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def user_input(self) -> str:
        """Get user input from message."""
        return self.message.content


class BaseAgentExecutor(ABC):
    """Base class for A2A-compatible agent executors.

    Provides common functionality for agents that use LiteLLM and AgentFS.

    Example:
        >>> class MyAgent(BaseAgentExecutor):
        ...     async def execute(self, context):
        ...         async for chunk in self.llm.completion_stream([...]):
        ...             yield AgentEvent.text(chunk.text)
        ...         yield AgentEvent.done()
    """

    def __init__(
        self,
        llm: LiteLLMProvider | None = None,
        agentfs: "AgentFS | None" = None,
        system_prompt: str | None = None,
    ):
        """Initialize agent executor.

        Args:
            llm: LiteLLM provider instance
            agentfs: AgentFS instance for persistence
            system_prompt: Optional system prompt for the agent
        """
        self._llm = llm
        self._agentfs = agentfs
        self._system_prompt = system_prompt

    @property
    def llm(self) -> LiteLLMProvider:
        """Get LLM provider, creating default if needed."""
        if self._llm is None:
            from llm.litellm_provider import get_provider

            self._llm = get_provider()
        return self._llm

    @property
    def agentfs(self) -> "AgentFS | None":
        """Get AgentFS instance."""
        return self._agentfs

    @agentfs.setter
    def agentfs(self, value: "AgentFS") -> None:
        """Set AgentFS instance."""
        self._agentfs = value

    @property
    def system_prompt(self) -> str | None:
        """Get system prompt."""
        return self._system_prompt

    @abstractmethod
    async def execute(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        """Execute agent with given context.

        Args:
            context: Agent execution context with message and history

        Yields:
            AgentEvent with text, tool calls, or status updates
        """
        ...

    async def cancel(self, context: AgentContext) -> None:
        """Cancel ongoing execution.

        Override to implement cancellation logic.
        """
        pass

    def build_messages(
        self,
        context: AgentContext,
        rag_context: str | None = None,
    ) -> list[dict]:
        """Build messages list for LLM.

        Args:
            context: Agent context with user message and history
            rag_context: Optional RAG context to include

        Returns:
            List of message dicts for LLM
        """
        messages = []

        # Add system prompt if present
        if self._system_prompt:
            system_content = self._system_prompt
            if rag_context:
                system_content += f"\n\n<context>\n{rag_context}\n</context>"
            messages.append({"role": "system", "content": system_content})
        elif rag_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Use the following context to answer:\n\n{rag_context}",
                }
            )

        # Add history
        for msg in context.history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current message
        messages.append({"role": context.message.role, "content": context.message.content})

        return messages

    async def save_to_history(
        self,
        context: AgentContext,
        response: str,
    ) -> None:
        """Save conversation turn to AgentFS.

        Args:
            context: Agent context
            response: Assistant response
        """
        if not self._agentfs:
            return

        try:
            history = await self._agentfs.kv.get("conversation:history") or []
            history.append({"role": "user", "content": context.user_input})
            history.append({"role": "assistant", "content": response})
            # Keep last 100 messages
            await self._agentfs.kv.set("conversation:history", history[-100:])
        except Exception:
            pass  # Ignore persistence errors

    async def audit_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        """Record tool call in AgentFS for audit.

        Args:
            tool_name: Name of the tool called
            tool_input: Input arguments
            result: Tool result (if successful)
            error: Error message (if failed)
        """
        if not self._agentfs:
            return

        try:
            call_id = await self._agentfs.tools.start(tool_name, {"input": str(tool_input)[:500]})
            if error:
                await self._agentfs.tools.error(call_id, error)
            else:
                await self._agentfs.tools.success(call_id, {"result": str(result)[:500]})
        except Exception:
            pass  # Ignore audit errors
