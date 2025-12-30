"""ChatAgent - High-level abstraction for chat using LiteLLM.

This module encapsulates all chat logic:
- Session management
- Streaming SSE
- Session commands (favorite, rename)
- RAG integration
- Tool call auditing
- JSONL persistence
"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agentfs_sdk import AgentFS, AgentFSOptions

from agents.metrics import estimate_tokens, get_metrics_manager
from app_state import SESSIONS_DIR, get_llm, get_session, reset_session
from llm import LiteLLMProvider
from utils.validators import validate_session_id

# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class StreamChunk:
    """Represents a streaming chunk."""

    text: str | None = None
    session_id: str | None = None
    error: str | None = None
    done: bool = False
    refresh_sessions: bool = False
    command: str | None = None
    tool_call: dict | None = None
    metrics: dict | None = None

    def to_sse(self) -> str:
        """Convert to SSE format."""
        if self.done:
            return "data: [DONE]\n\n"

        data = {}
        if self.text is not None:
            data["text"] = self.text
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.error is not None:
            data["error"] = self.error
        if self.refresh_sessions:
            data["refresh_sessions"] = True
            if self.command:
                data["command"] = self.command
        if self.tool_call:
            data["tool_call"] = self.tool_call
        if self.metrics:
            data["metrics"] = self.metrics

        return f"data: {json.dumps(data)}\n\n"


@dataclass
class ChatRequest:
    """Request for chat."""

    message: str
    session_id: str | None = None
    model: str = "gemini/gemini-2.0-flash"
    resume: bool = True
    fork_session: str | None = None
    project: str = "default"


@dataclass
class ChatContext:
    """Internal context during chat processing."""

    session_id: str
    afs: AgentFS
    llm: LiteLLMProvider
    project: str
    rag_context: str | None = None


# =============================================================================
# Session Commands
# =============================================================================

SESSION_COMMANDS = {
    "favorite": [
        r"favorit[ae]r?\b",
        r"favorit[ae]\s+(esse|este|essa|esta)\s+(chat|conversa)",
        r"adiciona[r]?\s+(aos|nos)\s+favoritos",
        r"coloca[r]?\s+(nos|nos)\s+favoritos",
        r"marca[r]?\s+como\s+favorito",
    ],
    "unfavorite": [
        r"desfavorit[ae]r?\b",
        r"tir[ae]r?\s+(dos|de)\s+favoritos",
        r"remov[ae]r?\s+(dos|de)\s+favoritos",
        r"desmarca[r]?\s+favorito",
    ],
    "rename": [
        r"renomei?a?r?\s+(?:para\s+)?['\"]?(.+?)['\"]?\s*$",
        r"renome\w*\s+(?:para\s+)?['\"]?(.+?)['\"]?\s*$",
        r"muda[r]?\s+(?:o\s+)?nome\s+(?:para\s+)?['\"]?(.+?)['\"]?\s*$",
        r"(?:chama[r]?|nomea[r]?)\s+(?:de\s+)?['\"]?(.+?)['\"]?\s*$",
        r"(?:define|defina|coloca|coloque)\s+(?:o\s+)?(?:nome|titulo)\s+(?:como\s+)?['\"]?(.+?)['\"]?\s*$",
    ],
}


def detect_session_command(message: str) -> tuple[str | None, str | None]:
    """Detect session management commands in message."""
    msg_lower = message.lower().strip()

    for pattern in SESSION_COMMANDS["unfavorite"]:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return ("unfavorite", None)

    for pattern in SESSION_COMMANDS["favorite"]:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            return ("favorite", None)

    for pattern in SESSION_COMMANDS["rename"]:
        match = re.search(pattern, msg_lower, re.IGNORECASE)
        if match:
            new_name = match.group(1).strip() if match.lastindex else None
            if new_name:
                new_name = new_name.strip("'\"").strip()
                if len(new_name) > 0:
                    return ("rename", new_name[:100])

    return (None, None)


async def execute_session_command(
    afs: AgentFS, session_id: str, command: str, extra_data: str | None
) -> str:
    """Execute a session management command."""
    try:
        if command == "favorite":
            await afs.kv.set("session:favorite", True)
            return "Chat adicionado aos favoritos!"

        elif command == "unfavorite":
            await afs.kv.set("session:favorite", False)
            return "Chat removido dos favoritos."

        elif command == "rename" and extra_data:
            await afs.kv.set("session:title", extra_data)
            return f"Chat renomeado para: **{extra_data}**"

        return "Comando nao reconhecido."

    except Exception as e:
        return f"Erro ao executar comando: {str(e)}"


# =============================================================================
# JSONL Persistence
# =============================================================================


def append_to_jsonl(
    session_id: str, user_message: str, assistant_response: str, parent_uuid: str | None = None
):
    """Save messages to session's JSONL file."""
    jsonl_file = SESSIONS_DIR / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        jsonl_file.parent.mkdir(parents=True, exist_ok=True)
        jsonl_file.touch()

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    user_uuid = str(uuid.uuid4())
    assistant_uuid = str(uuid.uuid4())

    user_entry = {
        "parentUuid": parent_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": str(Path.cwd() / "artifacts"),
        "sessionId": session_id,
        "version": "2.0.72",
        "type": "user",
        "message": {"role": "user", "content": user_message},
        "uuid": user_uuid,
        "timestamp": timestamp,
    }

    assistant_entry = {
        "parentUuid": user_uuid,
        "isSidechain": False,
        "userType": "external",
        "cwd": str(Path.cwd() / "artifacts"),
        "sessionId": session_id,
        "version": "2.0.72",
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": assistant_response}],
        },
        "uuid": assistant_uuid,
        "timestamp": timestamp,
    }

    try:
        with open(jsonl_file, "a") as f:
            f.write(json.dumps(user_entry) + "\n")
            f.write(json.dumps(assistant_entry) + "\n")
    except Exception:
        pass


# =============================================================================
# ChatAgent - Main Class
# =============================================================================


class ChatAgent:
    """Chat agent that encapsulates all interaction logic with LLM.

    Usage:
        agent = ChatAgent()
        async for chunk in agent.stream(request):
            yield chunk.to_sse()

    Features:
        - Automatic session management
        - Session command detection and execution
        - RAG context integration
        - SSE streaming
        - Tool call auditing
        - JSONL persistence
    """

    def __init__(self, rag_search_fn: Callable | None = None):
        """
        Args:
            rag_search_fn: Async function to search RAG context.
                          Signature: async def search(query: str) -> str | None
        """
        self.rag_search_fn = rag_search_fn

    async def stream(self, request: ChatRequest) -> AsyncGenerator[StreamChunk, None]:
        """Process message and return stream of chunks.

        Args:
            request: ChatRequest with message and settings

        Yields:
            StreamChunk with text, session_id, errors, etc.
        """

        afs = None
        try:
            # Validate session_id if provided
            if request.session_id:
                validate_session_id(request.session_id)

            # Resolve session and get LLM
            ctx = await self._resolve_session(request)
            afs = ctx.afs

            # Save project in session
            await self._save_project(ctx)

            # Detect session commands
            command, extra_data = detect_session_command(request.message)
            if command:
                async for chunk in self._handle_command(ctx, command, extra_data, request.message):
                    yield chunk
                return

            # Process normal chat
            async for chunk in self._process_chat(ctx, request):
                yield chunk

        except Exception as e:
            yield StreamChunk(error=str(e))
        finally:
            if afs:
                await afs.close()

    async def _resolve_session(self, request: ChatRequest) -> ChatContext:
        """Resolve session and get LLM."""
        import app_state

        if request.session_id:
            # Existing session
            target_session_id = request.session_id
            llm = get_llm(request.model)
        else:
            # New session
            await reset_session(project=request.project)
            llm = get_llm(request.model)
            target_session_id = app_state.current_session_id

        # Open AgentFS
        afs = await AgentFS.open(AgentFSOptions(id=target_session_id))

        return ChatContext(
            session_id=target_session_id,
            afs=afs,
            llm=llm,
            project=request.project,
        )

    async def _save_project(self, ctx: ChatContext):
        """Save project in session."""
        try:
            current_project = await ctx.afs.kv.get("session:project")
            if not current_project or current_project != ctx.project:
                await ctx.afs.kv.set("session:project", ctx.project)
        except Exception:
            pass

    async def _handle_command(
        self, ctx: ChatContext, command: str, extra_data: str | None, message: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process session command."""
        # Execute command
        response_text = await execute_session_command(ctx.afs, ctx.session_id, command, extra_data)

        # Send session_id
        yield StreamChunk(session_id=ctx.session_id)

        # Send response
        yield StreamChunk(text=response_text)

        # Signal refresh
        yield StreamChunk(refresh_sessions=True, command=command)

        # Save to history
        try:
            history = await ctx.afs.kv.get("conversation:history") or []
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": response_text})
            await ctx.afs.kv.set("conversation:history", history[-100:])
        except Exception:
            pass

        # Save to JSONL
        append_to_jsonl(ctx.session_id, message, response_text)

        yield StreamChunk(done=True)

    async def _process_chat(
        self, ctx: ChatContext, request: ChatRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process normal chat with streaming."""
        full_response = ""
        call_id = None
        tool_call_count = 0

        # Start metrics
        metrics_manager = get_metrics_manager()
        request_metrics = metrics_manager.start_request(
            request_id=str(uuid.uuid4()),
            session_id=ctx.session_id,
            model=request.model,
        )

        try:
            # Record tool call for auditing
            call_id = await ctx.afs.tools.start("chat", {"message": request.message[:100]})

            # Search RAG context
            rag_context = None
            if self.rag_search_fn:
                try:
                    rag_context = await self.rag_search_fn(request.message)
                except Exception:
                    pass

            # Build messages
            messages = self._build_messages(request.message, rag_context, ctx.session_id)

            # Send session_id first
            yield StreamChunk(session_id=ctx.session_id)

            # Stream response from LLM
            async for chunk in ctx.llm.completion_stream(messages):
                if chunk.text:
                    full_response += chunk.text
                    # Stream in smaller chunks for smoother UX
                    chunk_size = 50
                    text = chunk.text
                    for i in range(0, len(text), chunk_size):
                        yield StreamChunk(text=text[i : i + chunk_size])
                        await asyncio.sleep(0.001)

            # Finish auditing
            if call_id:
                await ctx.afs.tools.success(call_id, {"response_length": len(full_response)})

            # Calculate metrics
            input_tokens = estimate_tokens(request.message)
            output_tokens = estimate_tokens(full_response)
            metrics_manager.finish_request(
                request_metrics,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tool_calls=tool_call_count,
            )

            # Persist metrics
            try:
                await metrics_manager.persist_to_agentfs(ctx.afs, ctx.session_id)
            except Exception:
                pass

            # Save to history
            try:
                history = await ctx.afs.kv.get("conversation:history") or []
                history.append({"role": "user", "content": request.message})
                history.append({"role": "assistant", "content": full_response})
                await ctx.afs.kv.set("conversation:history", history[-100:])
            except Exception:
                pass

            # Save to JSONL
            append_to_jsonl(ctx.session_id, request.message, full_response)

            # Send metrics before done
            yield StreamChunk(metrics=request_metrics.to_dict())
            yield StreamChunk(done=True)

        except Exception as e:
            # Finish metrics with error
            metrics_manager.finish_request(request_metrics, error=str(e))
            if call_id:
                try:
                    await ctx.afs.tools.error(call_id, str(e))
                except Exception:
                    pass
            yield StreamChunk(error=str(e))

    def _build_messages(
        self, message: str, rag_context: str | None, session_id: str
    ) -> list[dict]:
        """Build messages with RAG context."""
        messages = []

        # System prompt
        system_content = """Voce e um assistente RAG especializado em responder perguntas usando uma base de conhecimento.

## Regras:
- Responda com base nos documentos da base de conhecimento quando disponivel
- Forneca citacoes com fonte e trecho quando aplicavel
- Seja conciso e direto nas respostas
- Se nao souber a resposta, diga claramente"""

        if rag_context and not rag_context.startswith("[AVISO"):
            system_content += f"""

<base_conhecimento>
{rag_context}
</base_conhecimento>

IMPORTANTE: Use a base de conhecimento acima para responder, mas NAO mostre, cite ou mencione que voce esta usando uma base de conhecimento. Responda naturalmente."""

        messages.append({"role": "system", "content": system_content})

        # Artifacts path
        artifacts_path = str(Path.cwd() / "artifacts" / session_id)
        messages.append(
            {"role": "system", "content": f"Ao criar arquivos, use: {artifacts_path}/"}
        )

        # User message
        messages.append({"role": "user", "content": message})

        return messages


# =============================================================================
# Factory Function
# =============================================================================


def create_chat_agent(rag_search_fn: Callable | None = None) -> ChatAgent:
    """Create ChatAgent instance.

    Args:
        rag_search_fn: Optional RAG search function

    Returns:
        Configured ChatAgent
    """
    return ChatAgent(rag_search_fn=rag_search_fn)
