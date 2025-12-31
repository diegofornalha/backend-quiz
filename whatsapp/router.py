"""Router WhatsApp - Webhook para Evolution API."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

import app_state
from quiz.engine.quiz_engine import QuizEngine
from quiz.engine.scoring_engine import QuizScoringEngine

from .constants import QUIZ_ENGINE_TIMEOUT
from .evolution_client import EvolutionAPIClient, get_evolution_client
from .message_formatter import WhatsAppFormatter
from .models import EvolutionWebhookMessage, QuizFlowState, UserQuizState
from .user_state import UserStateManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

# =============================================================================
# SINGLETONS (Configuração global)
# =============================================================================

_state_manager: UserStateManager | None = None
_formatter = WhatsAppFormatter()


def get_state_manager() -> UserStateManager:
    """Dependency: Gerenciador de estado."""
    global _state_manager
    if _state_manager is None:
        _state_manager = UserStateManager()
    return _state_manager


async def get_quiz_engine() -> QuizEngine:
    """Dependency: Quiz engine."""
    agentfs = await app_state.get_agentfs()
    rag = await app_state.get_rag()
    return QuizEngine(agentfs=agentfs, rag=rag)


def get_scoring_engine() -> QuizScoringEngine:
    """Dependency: Scoring engine."""
    return QuizScoringEngine()


# =============================================================================
# WEBHOOK ENDPOINT (Principal)
# =============================================================================


@router.post("/webhook")
async def evolution_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    state_manager: UserStateManager = Depends(get_state_manager),
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Webhook para receber mensagens da Evolution API.

    Configurar no Evolution API:
    POST /webhook/set/{instance}
    {
        "url": "https://seu-dominio.com/whatsapp/webhook",
        "enabled": true,
        "events": ["MESSAGES_UPSERT"]
    }
    """
    try:
        body = await request.json()
        logger.debug(f"Webhook recebido: {body}")

        # Parsear webhook
        event = body.get("event")
        data = body.get("data", {})

        # Filtrar apenas mensagens recebidas (não enviadas por nós)
        if event != "messages.upsert":
            return {"status": "ignored", "reason": "event not messages.upsert"}

        # Extrair informações da mensagem
        message_data = data.get("message", {})
        key = data.get("key", {})

        # Ignorar mensagens enviadas por nós
        if key.get("fromMe"):
            return {"status": "ignored", "reason": "message from me"}

        # Extrair dados do remetente
        remote_jid = key.get("remoteJid", "")

        # === REDIRECIONAR MENSAGENS DE GRUPO ===
        if remote_jid.endswith("@g.us"):
            # É mensagem de grupo - verificar whitelist primeiro
            from whatsapp.group_router import process_group_message, get_group_manager, get_evolution_client as get_group_evolution

            group_id = remote_jid
            group_manager = await get_group_manager()

            # Ignorar silenciosamente grupos não autorizados
            if not await group_manager.is_group_allowed(group_id):
                logger.debug(f"Grupo não autorizado (ignorando): {group_id}")
                return {"status": "ignored", "reason": "group not whitelisted"}

            participant = key.get("participant", "")
            user_id = participant.replace("@s.whatsapp.net", "") if participant else ""
            user_name = data.get("pushName", "Participante")

            # Extrair texto
            message_type = message_data.get("messageType")
            text = ""
            if message_type == "conversation":
                text = message_data.get("conversation", "")
            elif message_type == "extendedTextMessage":
                text = message_data.get("extendedTextMessage", {}).get("text", "")

            if text:
                group_evolution = get_group_evolution()
                background_tasks.add_task(
                    process_group_message,
                    group_id=group_id,
                    user_id=user_id,
                    user_name=user_name,
                    text=text.strip(),
                    group_manager=group_manager,
                    evolution=group_evolution,
                )
                return {"status": "ok", "message": "redirected to group processor"}
            return {"status": "ignored", "reason": "group message without text"}
        # === FIM REDIRECIONAMENTO ===

        user_number = remote_jid.replace("@s.whatsapp.net", "")

        # Extrair texto da mensagem
        message_type = message_data.get("messageType")
        text = ""

        if message_type == "conversation":
            text = message_data.get("conversation", "")
        elif message_type == "extendedTextMessage":
            text = message_data.get("extendedTextMessage", {}).get("text", "")
        elif message_type in ["buttonsResponseMessage", "listResponseMessage"]:
            # Resposta de botão ou lista
            if message_type == "buttonsResponseMessage":
                text = message_data.get("buttonsResponseMessage", {}).get("selectedButtonId", "")
            else:
                text = message_data.get("listResponseMessage", {}).get("singleSelectReply", {}).get("selectedRowId", "")

        if not text:
            return {"status": "ignored", "reason": "no text in message"}

        # Processar mensagem em background
        background_tasks.add_task(
            process_message,
            user_number=user_number,
            text=text.strip(),
            state_manager=state_manager,
            evolution=evolution,
        )

        return {"status": "ok", "message": "processing"}

    except Exception as e:
        logger.error(f"Erro no webhook: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# =============================================================================
# MESSAGE PROCESSOR (Lógica principal)
# =============================================================================


async def process_message(
    user_number: str,
    text: str,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Processa mensagem do usuário e gerencia fluxo do quiz.

    Args:
        user_number: Número do usuário
        text: Texto da mensagem
        state_manager: Gerenciador de estado
        evolution: Cliente Evolution API
    """
    try:
        # Normalizar texto
        text_upper = text.upper().strip()

        # Buscar estado do usuário
        state = state_manager.get_state(user_number)

        logger.info(
            f"Processando mensagem de {user_number}: '{text}' (state: {state.flow_state})"
        )

        # Comandos globais (funcionam em qualquer estado)
        if text_upper in ["AJUDA", "HELP", "?"]:
            await evolution.send_text(user_number, _formatter.format_help())
            return

        if text_upper in ["PARAR", "STOP", "CANCELAR"]:
            if state.flow_state in [QuizFlowState.IN_QUIZ, QuizFlowState.IN_CHAT]:
                state_manager.reset_user(user_number)
                await evolution.send_text(user_number, _formatter.format_quiz_cancelled())
            else:
                await evolution.send_text(user_number, "Nenhum quiz ativo para cancelar.")
            return

        # Fluxo baseado no estado
        if state.flow_state == QuizFlowState.IDLE:
            await handle_idle_state(user_number, text_upper, state, state_manager, evolution)

        elif state.flow_state == QuizFlowState.IN_QUIZ:
            await handle_in_quiz_state(user_number, text, text_upper, state, state_manager, evolution)

        elif state.flow_state == QuizFlowState.IN_CHAT:
            await handle_in_chat_state(user_number, text, state, state_manager, evolution)

        elif state.flow_state == QuizFlowState.FINISHED:
            await handle_finished_state(user_number, text_upper, state, state_manager, evolution)

    except Exception as e:
        logger.error(f"Erro ao processar mensagem de {user_number}: {e}", exc_info=True)
        await evolution.send_text(user_number, _formatter.format_error())


# =============================================================================
# STATE HANDLERS
# =============================================================================


async def handle_idle_state(
    user_number: str,
    text_upper: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Usuário sem quiz ativo."""
    if text_upper in ["INICIAR", "START", "COMEÇAR"]:
        # Iniciar novo quiz
        try:
            agentfs = await app_state.get_agentfs()
            rag = await app_state.get_rag()
            engine = QuizEngine(agentfs=agentfs, rag=rag)

            # Validar RAG
            search_results = await rag.search("programa Renda Extra Ton", top_k=3)
            if not search_results:
                await evolution.send_text(
                    user_number,
                    _formatter.format_error(
                        "Base de conhecimento vazia. Por favor, aguarde a configuração do sistema."
                    ),
                )
                return

            # Iniciar quiz
            quiz_id, first_question = await engine.start_quiz()

            # Atualizar estado
            state.quiz_id = quiz_id
            state.current_question = 1
            state.flow_state = QuizFlowState.IN_QUIZ
            state.answers = []
            state.score = 0
            state_manager.save_state(state)

            # Enviar primeira pergunta
            await evolution.send_text(user_number, "🎯 *Quiz Iniciado!*\n\nPrepare-se...")
            await asyncio.sleep(1)
            msg = _formatter.format_question(first_question, 1)
            await evolution.send_text(user_number, msg)

        except Exception as e:
            logger.error(f"Erro ao iniciar quiz: {e}", exc_info=True)
            await evolution.send_text(user_number, _formatter.format_error("Erro ao iniciar quiz. Tente novamente."))
    else:
        # Primeira interação ou comando desconhecido
        await evolution.send_text(user_number, _formatter.format_welcome())


async def handle_in_quiz_state(
    user_number: str,
    text: str,
    text_upper: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Usuário no meio do quiz."""
    # Verificar se é resposta (A, B, C, D)
    if text_upper in ["A", "B", "C", "D"]:
        await handle_answer(user_number, text_upper, state, state_manager, evolution)
    elif text_upper in ["PROXIMA", "PRÓXIMA", "CONTINUAR", "NEXT"]:
        await send_next_question(user_number, state, state_manager, evolution)
    else:
        await evolution.send_text(
            user_number,
            "Por favor, responda com *A*, *B*, *C* ou *D*"
        )


async def handle_answer(
    user_number: str,
    answer: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Processa resposta do usuário."""
    try:
        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)
        scoring = QuizScoringEngine()

        # Buscar pergunta atual
        question = await engine.get_question(state.quiz_id, state.current_question, timeout=QUIZ_ENGINE_TIMEOUT)
        if not question:
            await evolution.send_text(user_number, _formatter.format_error("Erro ao carregar pergunta."))
            return

        # Converter resposta para índice (A=0, B=1, C=2, D=3)
        answer_index = {"A": 0, "B": 1, "C": 2, "D": 3}[answer]

        # Avaliar resposta
        result = scoring.evaluate_answer(question, answer_index)

        # Salvar resposta
        state.answers.append(answer_index)
        if result["is_correct"]:
            state.score += result["points_earned"]
        state_manager.save_state(state)

        # Enviar feedback
        correct_opt = None
        if not result["is_correct"]:
            correct_opt = question.options[question.correct_index]
            correct_opt_text = f"{correct_opt.label}) {correct_opt.text}"
        else:
            correct_opt_text = None

        feedback_msg = _formatter.format_feedback(
            is_correct=result["is_correct"],
            explanation=result["explanation"],
            correct_answer=correct_opt_text,
        )
        await evolution.send_text(user_number, feedback_msg)

        # Se foi a última pergunta, mostrar resultado
        if state.current_question >= 10:
            await send_final_results(user_number, state, state_manager, evolution)

    except Exception as e:
        logger.error(f"Erro ao processar resposta: {e}", exc_info=True)
        await evolution.send_text(user_number, _formatter.format_error())


async def send_next_question(
    user_number: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Envia próxima pergunta."""
    try:
        # Verificar se já respondeu a pergunta atual
        if len(state.answers) < state.current_question:
            await evolution.send_text(user_number, "Você ainda não respondeu a pergunta atual!")
            return

        # Verificar se acabou
        if state.current_question >= 10:
            await send_final_results(user_number, state, state_manager, evolution)
            return

        # Avançar para próxima pergunta
        state.current_question += 1
        state_manager.save_state(state)

        # Buscar próxima pergunta
        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)

        question = await engine.get_question(state.quiz_id, state.current_question, timeout=QUIZ_ENGINE_TIMEOUT)
        if not question:
            await evolution.send_text(user_number, _formatter.format_error("Erro ao carregar próxima pergunta."))
            return

        # Enviar pergunta
        msg = _formatter.format_question(question, state.current_question)
        await evolution.send_text(user_number, msg)

    except Exception as e:
        logger.error(f"Erro ao enviar próxima pergunta: {e}", exc_info=True)
        await evolution.send_text(user_number, _formatter.format_error())


async def send_final_results(
    user_number: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Calcula e envia resultado final."""
    try:
        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)
        scoring = QuizScoringEngine()

        # Buscar todas as perguntas
        questions = []
        for i in range(1, 11):
            q = await engine.store.get_question(state.quiz_id, i)
            if q:
                questions.append(q)

        if len(questions) != 10:
            await evolution.send_text(user_number, _formatter.format_error("Erro ao calcular resultado."))
            return

        # Calcular resultado
        result = scoring.calculate_score(questions, state.answers)

        # Atualizar estado
        state.flow_state = QuizFlowState.FINISHED
        state_manager.save_state(state)

        # Enviar resultado
        result_msg = _formatter.format_results(
            score=result["score"],
            max_score=result["max_score"],
            correct=result["correct_answers"],
            total=result["total_questions"],
            percentage=result["percentage"],
            rank=result["rank"],
            rank_title=result["rank_title"],
            rank_message=result["rank_message"],
        )
        await evolution.send_text(user_number, result_msg)

    except Exception as e:
        logger.error(f"Erro ao enviar resultado: {e}", exc_info=True)
        await evolution.send_text(user_number, _formatter.format_error())


async def handle_chat_question(
    user_number: str,
    question: str,
    state: UserQuizState,
    evolution: EvolutionAPIClient,
):
    """Processa dúvida do usuário via chat."""
    try:
        # Buscar contexto da pergunta atual
        agentfs = await app_state.get_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)

        current_q = await engine.get_question(state.quiz_id, state.current_question, timeout=QUIZ_ENGINE_TIMEOUT)
        if not current_q:
            await evolution.send_text(user_number, _formatter.format_error("Erro ao buscar pergunta."))
            return

        # Montar contexto para o chat
        context_prompt = f"""[CONTEXTO DO QUIZ]
Pergunta atual: "{current_q.question}"
Opções: {" | ".join(f"{o.label}) {o.text}" for o in current_q.options)}

[DÚVIDA DO USUÁRIO]
{question}

[INSTRUÇÕES]
1. Ajude o usuário a ENTENDER o conceito por trás da pergunta
2. NÃO revele qual é a resposta correta
3. NÃO diga que "não existe" algo se você não tiver certeza absoluta
4. Se não souber a resposta exata, diga "consulte o regulamento oficial"
5. NUNCA contradiga as opções apresentadas na pergunta
6. Seja breve (2-3 frases) e educativo
7. Ajude o usuário a raciocinar, não dê a resposta pronta"""

        # Usar cliente de chat do backend
        client = await app_state.get_client()
        response = await client.send_message_async(
            message=context_prompt,
            session_id=state.chat_session_id or f"whatsapp_{user_number}",
        )

        # Atualizar session_id se necessário
        if not state.chat_session_id:
            state.chat_session_id = f"whatsapp_{user_number}"

        # Enviar resposta
        chat_response = _formatter.format_chat_response(response)
        await evolution.send_text(user_number, chat_response)

    except Exception as e:
        logger.error(f"Erro ao processar dúvida: {e}", exc_info=True)
        await evolution.send_text(
            user_number,
            _formatter.format_error("Erro ao processar sua dúvida. Tente novamente.")
        )


async def handle_in_chat_state(
    user_number: str,
    text: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Usuário em modo chat de dúvidas."""
    text_upper = text.upper().strip()

    # Verificar se quer voltar ao quiz
    if text_upper in ["A", "B", "C", "D", "VOLTAR", "CONTINUAR"]:
        # Voltar ao quiz
        state.flow_state = QuizFlowState.IN_QUIZ
        state_manager.save_state(state)

        if text_upper in ["A", "B", "C", "D"]:
            # Processar resposta
            await handle_answer(user_number, text_upper, state, state_manager, evolution)
        else:
            await evolution.send_text(user_number, "Voltando ao quiz. Digite sua resposta (A/B/C/D).")
    else:
        # Continuar chat
        await handle_chat_question(user_number, text, state, evolution)


async def handle_finished_state(
    user_number: str,
    text_upper: str,
    state: UserQuizState,
    state_manager: UserStateManager,
    evolution: EvolutionAPIClient,
):
    """Quiz finalizado."""
    if text_upper in ["INICIAR", "START", "NOVAMENTE"]:
        # Resetar e iniciar novo quiz
        state_manager.reset_user(user_number)
        await handle_idle_state(user_number, "INICIAR", state_manager.get_state(user_number), state_manager, evolution)
    else:
        await evolution.send_text(user_number, "Quiz finalizado! Digite *INICIAR* para fazer novamente.")


# =============================================================================
# MANAGEMENT ENDPOINTS
# =============================================================================


@router.get("/status")
async def get_whatsapp_status(evolution: EvolutionAPIClient = Depends(get_evolution_client)):
    """Verifica status da instância WhatsApp."""
    try:
        status = await evolution.get_instance_status()
        return {"status": "ok", "evolution": status}
    except Exception as e:
        logger.error(f"Erro ao verificar status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configure-webhook")
async def configure_webhook(
    webhook_url: str,
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Configura webhook na Evolution API.

    Args:
        webhook_url: URL pública do webhook (ex: https://seu-dominio.com/whatsapp/webhook)
    """
    try:
        result = await evolution.set_webhook(webhook_url)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-users")
async def get_active_users(state_manager: UserStateManager = Depends(get_state_manager)):
    """Lista usuários com quiz ativo."""
    active = state_manager.get_active_users()
    return {
        "total": len(active),
        "users": [
            {
                "user_id": u.user_id,
                "quiz_id": u.quiz_id,
                "current_question": u.current_question,
                "score": u.score,
                "flow_state": u.flow_state,
            }
            for u in active
        ],
    }


@router.post("/reset-user/{user_number}")
async def reset_user_state(
    user_number: str,
    state_manager: UserStateManager = Depends(get_state_manager),
):
    """Reseta estado de um usuário (admin)."""
    state_manager.reset_user(user_number)
    return {"status": "ok", "message": f"Estado de {user_number} resetado"}
