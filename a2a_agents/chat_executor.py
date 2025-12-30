"""Chat Agent Executor - Main chat functionality using LiteLLM."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from llm import LiteLLMProvider

from .base import AgentContext, AgentEvent, AgentMessage, BaseAgentExecutor

# Default system prompt for chat
DEFAULT_SYSTEM_PROMPT = """Voce e um assistente RAG especializado em responder perguntas usando uma base de conhecimento.

## Regras:
- Responda com base nos documentos da base de conhecimento quando disponivel
- Forneca citacoes com fonte e trecho quando aplicavel
- Seja conciso e direto nas respostas
- Se nao souber a resposta, diga claramente

## Importante:
- NAO mostre caminhos completos do sistema de arquivos ao usuario
- Responda em portugues brasileiro"""


class ChatAgentExecutor(BaseAgentExecutor):
    """Agent executor for chat functionality.

    Handles:
    - Streaming chat responses
    - RAG context integration
    - Conversation history
    - Tool call auditing

    Example:
        >>> executor = ChatAgentExecutor()
        >>> context = AgentContext(
        ...     session_id="abc123",
        ...     message=AgentMessage(role="user", content="Hello!")
        ... )
        >>> async for event in executor.execute(context):
        ...     if event.type == "text":
        ...         print(event.data, end="")
    """

    def __init__(
        self,
        llm: LiteLLMProvider | None = None,
        agentfs: "AgentFS | None" = None,
        system_prompt: str | None = None,
        rag_search_fn: Callable[[str], str | None] | None = None,
    ):
        """Initialize chat executor.

        Args:
            llm: LiteLLM provider
            agentfs: AgentFS for persistence
            system_prompt: Custom system prompt (uses default if None)
            rag_search_fn: Async function to search RAG context
        """
        super().__init__(
            llm=llm,
            agentfs=agentfs,
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
        )
        self._rag_search_fn = rag_search_fn

    async def execute(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        """Execute chat with streaming response.

        Args:
            context: Agent context with user message

        Yields:
            AgentEvent with text chunks and status updates
        """
        full_response = ""

        try:
            # Emit status: working
            yield AgentEvent.status("working", "Processing message...")

            # Search RAG context if function provided
            rag_context = None
            if self._rag_search_fn:
                try:
                    rag_context = await self._rag_search_fn(context.user_input)
                except Exception:
                    pass  # Ignore RAG errors

            # Build messages with optional RAG context
            messages = self.build_messages(context, rag_context)

            # Record tool call for auditing
            if self.agentfs:
                try:
                    call_id = await self.agentfs.tools.start(
                        "chat", {"message": context.user_input[:100]}
                    )
                except Exception:
                    call_id = None
            else:
                call_id = None

            # Stream response from LLM
            async for chunk in self.llm.completion_stream(messages):
                if chunk.text:
                    full_response += chunk.text
                    yield AgentEvent.text(chunk.text)

                if chunk.is_done:
                    break

            # Save to history
            await self.save_to_history(context, full_response)

            # Mark tool call as success
            if self.agentfs and call_id:
                try:
                    await self.agentfs.tools.success(
                        call_id, {"response_length": len(full_response)}
                    )
                except Exception:
                    pass

            # Emit done
            yield AgentEvent.status("completed")
            yield AgentEvent.done()

        except Exception as e:
            # Emit error
            yield AgentEvent.error(str(e))
            yield AgentEvent.done()

    def build_messages(
        self,
        context: AgentContext,
        rag_context: str | None = None,
    ) -> list[dict]:
        """Build messages with RAG context.

        Extends base implementation to handle RAG-specific formatting.
        """
        messages = []

        # Build system message with RAG context
        system_content = self._system_prompt or DEFAULT_SYSTEM_PROMPT

        if rag_context and not rag_context.startswith("[AVISO"):
            system_content += f"""

<base_conhecimento>
{rag_context}
</base_conhecimento>

IMPORTANTE: Use a base de conhecimento acima para responder, mas NAO mostre, cite ou mencione que voce esta usando uma base de conhecimento. Responda naturalmente."""

        messages.append({"role": "system", "content": system_content})

        # Add artifacts path instruction if session_id available
        if context.session_id:
            artifacts_path = str(Path.cwd() / "artifacts" / context.session_id)
            messages.append(
                {
                    "role": "system",
                    "content": f"Ao criar arquivos, use: {artifacts_path}/",
                }
            )

        # Add history
        for msg in context.history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current message
        messages.append({"role": "user", "content": context.user_input})

        return messages


# Factory function
def create_chat_executor(
    rag_search_fn: Callable[[str], str | None] | None = None,
    system_prompt: str | None = None,
) -> ChatAgentExecutor:
    """Create a chat executor instance.

    Args:
        rag_search_fn: Optional RAG search function
        system_prompt: Optional custom system prompt

    Returns:
        Configured ChatAgentExecutor
    """
    return ChatAgentExecutor(
        rag_search_fn=rag_search_fn,
        system_prompt=system_prompt,
    )
