"""Chat endpoints - Migrado para LiteLLM."""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app_state import SESSIONS_DIR, get_agentfs, get_llm
from llm import LiteLLMProvider
from utils.validators import validate_session_id

# Logging padrão
logger = logging.getLogger("chat")

router = APIRouter(tags=["Chat"])


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
        r"(?:define|defina|coloca|coloque)\s+(?:o\s+)?(?:nome|título)\s+(?:como\s+)?['\"]?(.+?)['\"]?\s*$",
    ],
}


def detect_session_command(message: str) -> tuple[str | None, str | None]:
    """Detecta comandos de gerenciamento de sessão na mensagem."""
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
    afs, session_id: str, command: str, extra_data: str | None
) -> str:
    """Executa um comando de gerenciamento de sessão."""
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
        logger.error(f"Erro ao executar comando de sessao: {e}")
        return f"Erro ao executar comando: {str(e)}"


# =============================================================================
# JSONL Persistence
# =============================================================================


def append_to_jsonl(
    session_id: str, user_message: str, assistant_response: str, parent_uuid: str | None = None
):
    """Append user and assistant messages to a session's JSONL file."""
    jsonl_file = SESSIONS_DIR / f"{session_id}.jsonl"

    if not jsonl_file.exists():
        logger.info(f"Criando arquivo JSONL para nova sessao: {session_id}")
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
            f.write(json.dumps(user_entry, ensure_ascii=False) + "\n")
            f.write(json.dumps(assistant_entry, ensure_ascii=False) + "\n")
        logger.debug(f"Mensagens salvas no JSONL: {session_id}")
    except Exception as e:
        logger.error(f"Falha ao salvar JSONL: {session_id}, error: {e}")


# =============================================================================
# RAG Search
# =============================================================================


async def search_rag_context(query: str, top_k: int = 5) -> str:
    """Busca contexto relevante na base RAG."""
    try:
        from a2a_rag_sdk.core.config import get_config
        from a2a_rag_sdk.search import SearchEngine

        config = get_config()
        rag_db_path = config.rag_db_path

        if not rag_db_path.exists():
            return ""

        engine = SearchEngine(
            db_path=str(rag_db_path),
            embedding_model=config.embedding_model_string,
            enable_reranking=True,
        )
        results = await engine.search(query, top_k=top_k)

        if not results:
            return ""

        context_parts = []
        for r in results:
            context_parts.append(f"[Fonte: {r.source}]\n{r.content[:4000]}")

        return "\n\n---\n\n".join(context_parts)

    except Exception as e:
        logger.error(f"Busca RAG falhou: {e}")
        return "[AVISO: Busca na base de conhecimento falhou - respondendo sem contexto RAG]"


# =============================================================================
# Request/Response Models
# =============================================================================


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = "gemini/gemini-2.0-flash"
    resume: bool | None = False
    fork_session: bool | None = False


class ChatStreamRequest(BaseModel):
    """Request model for streaming chat endpoint."""

    message: str
    session_id: str | None = None
    model: str | None = "gemini/gemini-2.0-flash"
    resume: bool | None = True
    fork_session: str | None = None
    use_rag: bool = True
    top_k: int = 5
    project: str = "default"


class ChatResponse(BaseModel):
    response: str


# =============================================================================
# Simple API Key Verification (placeholder)
# =============================================================================


async def verify_api_key(request: Request) -> str:
    """Verify API key from header or query param."""
    import os

    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    expected_key = os.getenv("RAG_API_KEY", "dev-key")

    # Em desenvolvimento, aceitar qualquer chave
    if os.getenv("ENVIRONMENT", "development") == "development":
        return api_key or "dev-key"

    if not api_key or api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


# =============================================================================
# Chat Endpoints
# =============================================================================


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """Chat with RAG-powered AI using LiteLLM."""
    from agentfs_sdk import AgentFS, AgentFSOptions

    import app_state

    project = request.headers.get("X-Client-Project", "default")

    try:
        # Get LLM provider
        llm = get_llm(chat_request.model)

        session_specific_afs = None

        # Ensure we have a session
        if not chat_request.session_id and not app_state.current_session_id:
            from app_state import reset_session
            await reset_session()

        target_session_id = chat_request.session_id or app_state.current_session_id

        if target_session_id:
            validate_session_id(target_session_id)

        if chat_request.session_id and chat_request.session_id != app_state.current_session_id:
            session_specific_afs = await AgentFS.open(AgentFSOptions(id=chat_request.session_id))
            afs = session_specific_afs
            print(f"[INFO] Usando sessao especifica: {chat_request.session_id}")
        else:
            afs = await get_agentfs()

        # Buscar contexto RAG
        rag_context = await search_rag_context(chat_request.message)

        artifacts_path = str(Path.cwd() / "artifacts" / target_session_id)

        # Build messages
        messages = []

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
        messages.append({"role": "system", "content": f"Ao criar arquivos, use: {artifacts_path}/"})
        messages.append({"role": "user", "content": chat_request.message})

        # Get response from LLM
        response = await llm.completion(messages)
        response_text = response.content

        # Save to history
        history = await afs.kv.get("conversation:history") or []
        history.append({"role": "user", "content": chat_request.message})
        history.append({"role": "assistant", "content": response_text})
        await afs.kv.set("conversation:history", history[-100:])

        # Save to JSONL
        if chat_request.session_id:
            append_to_jsonl(
                session_id=chat_request.session_id,
                user_message=chat_request.message,
                assistant_response=response_text,
            )

        return ChatResponse(response=response_text)

    except Exception as e:
        print(f"[ERROR] Chat error: {e}")
        raise HTTPException(status_code=500, detail="Chat processing failed") from e
    finally:
        if session_specific_afs:
            await session_specific_afs.close()


@router.post("/chat/stream")
async def chat_stream(
    request: Request, chat_request: ChatRequest, api_key: str = Depends(verify_api_key)
):
    """Chat with streaming response using LiteLLM."""
    from agentfs_sdk import AgentFS, AgentFSOptions

    if chat_request.session_id:
        validate_session_id(chat_request.session_id)

    afs = None
    try:
        import app_state

        project = request.headers.get("X-Client-Project", "default")

        if chat_request.session_id:
            validate_session_id(chat_request.session_id)
            target_session_id = chat_request.session_id
        else:
            from app_state import reset_session

            await reset_session(project=project)
            target_session_id = app_state.current_session_id
            print(f"[STREAM] Nova sessao criada: {target_session_id} (projeto: {project})")

        afs = await AgentFS.open(AgentFSOptions(id=target_session_id))

        # Save project
        try:
            current_project = await afs.kv.get("session:project")
            if not current_project or current_project != project:
                await afs.kv.set("session:project", project)
        except Exception:
            pass

        # Detect session commands
        command, extra_data = detect_session_command(chat_request.message)
        if command:
            async def generate_command_response():
                nonlocal afs
                try:
                    response_text = await execute_session_command(
                        afs, target_session_id, command, extra_data
                    )

                    yield f"data: {json.dumps({'session_id': target_session_id})}\n\n"
                    yield f"data: {json.dumps({'text': response_text})}\n\n"
                    yield f"data: {json.dumps({'refresh_sessions': True, 'command': command})}\n\n"

                    # Save to history
                    try:
                        history = await afs.kv.get("conversation:history") or []
                        history.append({"role": "user", "content": chat_request.message})
                        history.append({"role": "assistant", "content": response_text})
                        await afs.kv.set("conversation:history", history[-100:])
                    except Exception:
                        pass

                    append_to_jsonl(target_session_id, chat_request.message, response_text)
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                finally:
                    if afs:
                        await afs.close()

            return StreamingResponse(generate_command_response(), media_type="text/event-stream")

        async def generate():
            nonlocal afs
            full_response = ""
            call_id = None

            try:
                # Get LLM
                llm = get_llm(chat_request.model)

                # Record tool call for auditing
                call_id = await afs.tools.start("chat", {"message": chat_request.message[:100]})

                # Search RAG context
                rag_context = await search_rag_context(chat_request.message)

                # Build messages
                messages = []
                artifacts_path = str(Path.cwd() / "artifacts" / target_session_id)

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
                messages.append({"role": "system", "content": f"Ao criar arquivos, use: {artifacts_path}/"})
                messages.append({"role": "user", "content": chat_request.message})

                # Send session_id first
                yield f"data: {json.dumps({'session_id': target_session_id})}\n\n"

                # Stream response
                async for chunk in llm.completion_stream(messages):
                    if chunk.text:
                        full_response += chunk.text
                        # Stream in smaller chunks for smoother UX
                        chunk_size = 50
                        text = chunk.text
                        for i in range(0, len(text), chunk_size):
                            yield f"data: {json.dumps({'text': text[i:i + chunk_size]})}\n\n"
                            await asyncio.sleep(0.001)

                # Save to history
                try:
                    history = await afs.kv.get("conversation:history") or []
                    history.append({"role": "user", "content": chat_request.message})
                    history.append({"role": "assistant", "content": full_response})
                    await afs.kv.set("conversation:history", history[-100:])

                    # Auto-rename in background
                    existing_title = await afs.kv.get("session:title")
                    if not existing_title:
                        async def generate_title_background(
                            session_id: str, user_msg: str, assistant_resp: str
                        ):
                            try:
                                from agentfs_sdk import AgentFS, AgentFSOptions

                                from agents.title_generator import get_smart_title

                                auto_title = await get_smart_title(
                                    user_message=user_msg,
                                    assistant_response=assistant_resp,
                                )
                                bg_afs = await AgentFS.open(AgentFSOptions(id=session_id))
                                await bg_afs.kv.set("session:title", auto_title)
                                await bg_afs.close()
                                print(f"[BG] Auto-titulo: {auto_title}")
                            except Exception as e:
                                print(f"[BG] Erro auto-titulo: {e}")

                        asyncio.create_task(
                            generate_title_background(
                                target_session_id, chat_request.message, full_response
                            )
                        )
                except Exception as save_err:
                    print(f"[WARN] Erro ao salvar historico: {save_err}")

                # Save to JSONL
                append_to_jsonl(target_session_id, chat_request.message, full_response)

                # Mark tool call as success
                if call_id:
                    await afs.tools.success(call_id, {"response_length": len(full_response)})

                yield "data: [DONE]\n\n"

            except Exception as e:
                if call_id:
                    try:
                        await afs.tools.error(call_id, str(e))
                    except Exception:
                        pass
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                if afs:
                    await afs.close()

        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        print(f"[ERROR] Stream error: {e}")
        if afs:
            await afs.close()
        raise HTTPException(status_code=500, detail=str(e)) from e


# =============================================================================
# V2 Endpoints - Using ChatAgent Abstraction
# =============================================================================


@router.post("/v2/chat/stream")
async def chat_stream_v2(
    chat_request: ChatStreamRequest,
    request: Request,
    _: None = Depends(verify_api_key),
):
    """Chat streaming endpoint V2 - Usa ChatAgent abstraction.

    Esta versao usa a abstracao ChatAgent que encapsula:
    - Gerenciamento de sessoes
    - Comandos de sessao (favoritar, renomear)
    - Integracao com RAG
    - Streaming SSE
    - Auditoria
    - Persistencia JSONL

    Exemplo de uso:
        POST /v2/chat/stream
        {
            "message": "ola",
            "session_id": "uuid-opcional",
            "model": "gemini/gemini-2.0-flash"
        }
    """
    from agents.chat_agent import ChatRequest as AgentChatRequest
    from agents.chat_agent import create_chat_agent

    # Obter projeto do header ou request
    project = request.headers.get("X-Client-Project", chat_request.project)

    # Criar request para o agent
    agent_request = AgentChatRequest(
        message=chat_request.message,
        session_id=chat_request.session_id,
        model=chat_request.model or "gemini/gemini-2.0-flash",
        resume=chat_request.resume if chat_request.resume is not None else True,
        fork_session=chat_request.fork_session,
        project=project,
    )

    # Criar agent com funcao de busca RAG
    agent = create_chat_agent(rag_search_fn=search_rag_context)

    async def generate():
        async for chunk in agent.stream(agent_request):
            yield chunk.to_sse()

    return StreamingResponse(generate(), media_type="text/event-stream")
