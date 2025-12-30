"""Router para Quiz em Grupo - WhatsApp."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

import app_state
from quiz.engine.quiz_engine import QuizEngine
from quiz.engine.scoring_engine import QuizScoringEngine

from .evolution_client import EvolutionAPIClient
from .group_formatter import GroupMessageFormatter
from .group_manager import GroupStateManager
from .group_models import GroupCommand, GroupQuizState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/group", tags=["WhatsApp Group"])

# =============================================================================
# SINGLETONS
# =============================================================================

_group_manager: GroupStateManager | None = None
_evolution_client: EvolutionAPIClient | None = None
_formatter = GroupMessageFormatter()


def get_group_manager() -> GroupStateManager:
    """Dependency: Gerenciador de grupos."""
    global _group_manager
    if _group_manager is None:
        _group_manager = GroupStateManager()
    return _group_manager


def get_evolution_client() -> EvolutionAPIClient:
    """Dependency: Cliente Evolution API."""
    global _evolution_client
    if _evolution_client is None:
        base_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        api_key = os.getenv("EVOLUTION_API_KEY", "")
        instance = os.getenv("EVOLUTION_INSTANCE", "quiz-instance")

        if not api_key:
            raise RuntimeError("EVOLUTION_API_KEY não configurado")

        _evolution_client = EvolutionAPIClient(
            base_url=base_url,
            api_key=api_key,
            instance_name=instance,
        )

    return _evolution_client


async def get_quiz_engine() -> QuizEngine:
    """Dependency: Quiz engine."""
    agentfs = await app_state.get_agentfs()
    rag = await app_state.get_rag()
    return QuizEngine(agentfs=agentfs, rag=rag)


def get_scoring_engine() -> QuizScoringEngine:
    """Dependency: Scoring engine."""
    return QuizScoringEngine()


# =============================================================================
# WEBHOOK ENDPOINT
# =============================================================================


@router.post("/webhook")
async def group_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    group_manager: GroupStateManager = Depends(get_group_manager),
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Webhook para receber mensagens de grupos WhatsApp.

    IMPORTANTE: Este endpoint APENAS processa mensagens de grupos.
    Mensagens individuais são ignoradas ou recebem mensagem de bloqueio.
    """
    try:
        body = await request.json()
        logger.debug(f"Webhook recebido: {body}")

        event = body.get("event")
        data = body.get("data", {})

        if event != "messages.upsert":
            return {"status": "ignored", "reason": "event not messages.upsert"}

        message_data = data.get("message", {})
        key = data.get("key", {})

        # Ignorar mensagens enviadas por nós
        if key.get("fromMe"):
            return {"status": "ignored", "reason": "message from me"}

        # Extrair dados
        remote_jid = key.get("remoteJid", "")
        sender_jid = data.get("pushName", "Participante")  # Nome do remetente

        # Verificar se é mensagem de grupo
        is_group = remote_jid.endswith("@g.us")

        if not is_group:
            # Mensagem individual - ignorar silenciosamente (não responder)
            logger.info(f"📱 Mensagem individual ignorada de: {remote_jid}")
            return {"status": "ignored", "reason": "private message ignored"}

        # É mensagem de grupo - verificar whitelist
        group_id = remote_jid
        if not group_manager.is_group_allowed(group_id):
            # Grupo não autorizado - ignorar silenciosamente
            logger.debug(f"Grupo não autorizado (ignorando): {group_id}")
            return {"status": "ignored", "reason": "group not whitelisted"}

        # Extrair texto da mensagem
        message_type = message_data.get("messageType")
        text = ""

        if message_type == "conversation":
            text = message_data.get("conversation", "")
        elif message_type == "extendedTextMessage":
            text = message_data.get("extendedTextMessage", {}).get("text", "")

        if not text:
            return {"status": "ignored", "reason": "no text in message"}

        # Extrair ID do usuário que enviou
        participant = key.get("participant", "")  # Quem enviou no grupo
        if not participant:
            # Fallback para remoteJid (pode ser admin)
            participant = remote_jid

        user_number = participant.replace("@s.whatsapp.net", "")

        # Processar mensagem em background
        background_tasks.add_task(
            process_group_message,
            group_id=group_id,
            user_id=user_number,
            user_name=sender_jid,
            text=text.strip(),
            group_manager=group_manager,
            evolution=evolution,
        )

        return {"status": "ok", "message": "processing"}

    except Exception as e:
        logger.error(f"Erro no webhook de grupo: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# =============================================================================
# MESSAGE PROCESSOR
# =============================================================================


async def process_group_message(
    group_id: str,
    user_id: str,
    user_name: str,
    text: str,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Processa mensagem do grupo.

    Args:
        group_id: ID do grupo
        user_id: ID do usuário que enviou
        user_name: Nome do usuário
        text: Texto da mensagem
        group_manager: Gerenciador de grupos
        evolution: Cliente Evolution
    """
    try:
        text_upper = text.upper().strip()

        # Buscar sessão do grupo
        session = group_manager.get_session(group_id)

        logger.info(
            f"Mensagem em {group_id} de {user_name}: '{text}' (state: {session.state})"
        )

        # Comandos globais
        if text_upper == GroupCommand.AJUDA.value:
            await evolution.send_text(group_id, _formatter.format_help())
            return

        if text_upper == GroupCommand.REGULAMENTO.value:
            await evolution.send_text(
                group_id,
                "📋 *Regulamento Oficial*\n\n"
                "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view"
            )
            return

        if text_upper == GroupCommand.STATUS.value:
            await evolution.send_text(group_id, _formatter.format_status(session))
            return

        if text_upper == GroupCommand.RANKING.value:
            await evolution.send_text(group_id, _formatter.format_ranking(session, show_full=True))
            return

        # Comandos baseados em estado
        if session.state == GroupQuizState.IDLE:
            await handle_idle_state(group_id, user_id, user_name, text_upper, session, group_manager, evolution)

        elif session.state == GroupQuizState.ACTIVE:
            await handle_active_state(group_id, user_id, user_name, text_upper, session, group_manager, evolution)

        elif session.state == GroupQuizState.WAITING_NEXT:
            await handle_waiting_next_state(group_id, text_upper, session, group_manager, evolution)

        elif session.state == GroupQuizState.FINISHED:
            await handle_finished_state(group_id, user_id, user_name, text_upper, session, group_manager, evolution)

    except Exception as e:
        logger.error(f"Erro ao processar mensagem em {group_id}: {e}", exc_info=True)
        await evolution.send_text(group_id, "⚠️ Ocorreu um erro. Tente novamente.")


# =============================================================================
# STATE HANDLERS
# =============================================================================


async def handle_idle_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_upper: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Nenhum quiz ativo."""
    if text_upper == GroupCommand.INICIAR.value:
        # Iniciar novo quiz
        try:
            agentfs = await app_state.get_agentfs()
            rag = await app_state.get_rag()
            engine = QuizEngine(agentfs=agentfs, rag=rag)

            # Validar RAG
            search_results = await rag.search("programa Renda Extra Ton", top_k=3)
            if not search_results:
                await evolution.send_text(
                    group_id,
                    "⚠️ Base de conhecimento vazia. Aguarde configuração do sistema."
                )
                return

            # Iniciar quiz
            quiz_id, first_question = await engine.start_quiz()

            # Atualizar sessão
            session.quiz_id = quiz_id
            session.state = GroupQuizState.ACTIVE
            session.started_by = user_id
            session.started_at = None  # Será setado automaticamente
            session.start_new_question(1)
            group_manager.save_session(session)

            # Avisar que quiz iniciou
            await evolution.send_text(group_id, _formatter.format_quiz_started(user_name))
            await asyncio.sleep(1)

            # Enviar primeira pergunta
            msg = _formatter.format_question(first_question, 1)
            await evolution.send_text(group_id, msg)

        except Exception as e:
            logger.error(f"Erro ao iniciar quiz no grupo: {e}", exc_info=True)
            await evolution.send_text(group_id, "⚠️ Erro ao iniciar quiz. Tente novamente.")
    else:
        # Primeira mensagem ou comando desconhecido
        await evolution.send_text(group_id, _formatter.format_welcome())


async def handle_active_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_upper: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Quiz ativo - recebendo respostas."""
    # Verificar se é comando PARAR
    if text_upper == GroupCommand.PARAR.value:
        group_manager.reset_group(group_id)
        await evolution.send_text(group_id, _formatter.format_quiz_cancelled(user_name))
        return

    # Verificar se é resposta (A/B/C/D)
    if text_upper in [GroupCommand.A.value, GroupCommand.B.value, GroupCommand.C.value, GroupCommand.D.value]:
        await handle_group_answer(group_id, user_id, user_name, text_upper, session, group_manager, evolution)
        return

    # Ignorar outras mensagens durante quiz ativo
    # (para não poluir o grupo com mensagens de erro)


async def handle_group_answer(
    group_id: str,
    user_id: str,
    user_name: str,
    answer: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Processa resposta de participante."""
    try:
        # Verificar se já respondeu
        if session.has_answered(user_id):
            # Avisar apenas o usuário (não o grupo todo)
            # Não fazemos nada para não poluir o grupo
            return

        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)
        scoring = QuizScoringEngine()

        # Buscar pergunta atual
        question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
        if not question:
            await evolution.send_text(group_id, "⚠️ Erro ao carregar pergunta.")
            return

        # Converter resposta para índice
        answer_index = {"A": 0, "B": 1, "C": 2, "D": 3}[answer]

        # Avaliar resposta
        result = scoring.evaluate_answer(question, answer_index)

        # Salvar resposta na sessão
        session.add_answer(
            user_id=user_id,
            user_name=user_name,
            answer_index=answer_index,
            is_correct=result["is_correct"],
            points=result["points_earned"],
        )
        group_manager.save_session(session)

        # Feedback individual (pode ser enviado ao grupo ou só para o usuário)
        current_state = session.get_current_question_state()
        answered_count = len(current_state.answers) if current_state else 0
        total_participants = len(session.participants)

        feedback = _formatter.format_answer_feedback(
            user_name=user_name,
            is_correct=result["is_correct"],
            points_earned=result["points_earned"],
            answered_count=answered_count,
            total_participants=total_participants,
        )
        await evolution.send_text(group_id, feedback)

        # TODO: Implementar lógica de timeout ou avançar automático
        # Por enquanto, avança manualmente com comando PROXIMA

    except Exception as e:
        logger.error(f"Erro ao processar resposta no grupo: {e}", exc_info=True)
        await evolution.send_text(group_id, "⚠️ Erro ao processar resposta.")


async def handle_waiting_next_state(
    group_id: str,
    text_upper: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Aguardando comando para próxima pergunta."""
    if text_upper == GroupCommand.PROXIMA.value:
        await send_next_group_question(group_id, session, group_manager, evolution)


async def send_next_group_question(
    group_id: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Envia próxima pergunta para o grupo."""
    try:
        # Mostrar resultado da pergunta anterior
        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)

        prev_question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
        if prev_question:
            current_state = session.get_current_question_state()
            if current_state:
                correct_opt = prev_question.options[prev_question.correct_index]
                result_msg = _formatter.format_question_results(
                    question_state=current_state,
                    correct_answer=f"{correct_opt.label}) {correct_opt.text}",
                    explanation=prev_question.explanation,
                )
                await evolution.send_text(group_id, result_msg)
                await asyncio.sleep(2)

        # Verificar se acabou
        if session.current_question >= 10:
            session.state = GroupQuizState.FINISHED
            group_manager.save_session(session)
            await evolution.send_text(group_id, _formatter.format_final_results(session))
            return

        # Avançar para próxima pergunta
        session.current_question += 1
        session.start_new_question(session.current_question)
        session.state = GroupQuizState.ACTIVE
        group_manager.save_session(session)

        # Buscar e enviar próxima pergunta
        next_question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
        if not next_question:
            await evolution.send_text(group_id, "⚠️ Erro ao carregar próxima pergunta.")
            return

        msg = _formatter.format_question(next_question, session.current_question)
        await evolution.send_text(group_id, msg)

    except Exception as e:
        logger.error(f"Erro ao enviar próxima pergunta: {e}", exc_info=True)
        await evolution.send_text(group_id, "⚠️ Erro ao avançar para próxima pergunta.")


async def handle_finished_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_upper: str,
    session: Any,
    group_manager: GroupStateManager,
    evolution: EvolutionAPIClient,
):
    """Quiz finalizado."""
    if text_upper == GroupCommand.INICIAR.value:
        # Resetar e iniciar novo quiz
        group_manager.reset_group(group_id)
        new_session = group_manager.get_session(group_id)
        await handle_idle_state(group_id, user_id, user_name, text_upper, new_session, group_manager, evolution)


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================


@router.post("/whitelist/add/{group_id}")
async def add_group_to_whitelist(
    group_id: str,
    group_manager: GroupStateManager = Depends(get_group_manager),
):
    """Adiciona grupo à whitelist (ADMIN).

    Args:
        group_id: ID do grupo WhatsApp (ex: 123456789@g.us)
    """
    success = group_manager.add_allowed_group(group_id)
    if success:
        return {"status": "ok", "message": f"Grupo {group_id} adicionado à whitelist"}
    return {"status": "ok", "message": f"Grupo {group_id} já estava na whitelist"}


@router.delete("/whitelist/remove/{group_id}")
async def remove_group_from_whitelist(
    group_id: str,
    group_manager: GroupStateManager = Depends(get_group_manager),
):
    """Remove grupo da whitelist (ADMIN).

    Args:
        group_id: ID do grupo WhatsApp
    """
    success = group_manager.remove_allowed_group(group_id)
    if success:
        return {"status": "ok", "message": f"Grupo {group_id} removido da whitelist"}
    return {"status": "error", "message": f"Grupo {group_id} não estava na whitelist"}


@router.get("/whitelist")
async def list_whitelisted_groups(
    group_manager: GroupStateManager = Depends(get_group_manager),
):
    """Lista grupos autorizados (ADMIN)."""
    groups = group_manager.list_allowed_groups()
    return {"total": len(groups), "groups": groups}


@router.get("/active")
async def get_active_group_sessions(
    group_manager: GroupStateManager = Depends(get_group_manager),
):
    """Lista grupos com quiz ativo (ADMIN)."""
    active = group_manager.get_active_groups()
    return {
        "total": len(active),
        "groups": [
            {
                "group_id": s.group_id,
                "group_name": s.group_name,
                "quiz_id": s.quiz_id,
                "current_question": s.current_question,
                "participants": len(s.participants),
                "state": s.state,
            }
            for s in active
        ],
    }


@router.post("/reset/{group_id}")
async def reset_group_session(
    group_id: str,
    group_manager: GroupStateManager = Depends(get_group_manager),
):
    """Reseta sessão de um grupo (ADMIN)."""
    group_manager.reset_group(group_id)
    return {"status": "ok", "message": f"Sessão de {group_id} resetada"}
