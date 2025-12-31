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
from .group_formatter import GroupMessageFormatter, _format_participant_name
from .group_manager_kv import GroupStateManagerKV
from .group_models import GroupCommand, GroupQuizState
from .quiz_logger import get_quiz_logger, QuizLogger, LogCategory
from .user_manager_kv import UserManagerKV
from .user_models import UserProfile, WelcomeConfig

# Import do welcome_router para delegação
from .welcome_router import process_group_join as welcome_process_group_join
from .welcome_router import get_user_manager as welcome_get_user_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/group", tags=["WhatsApp Group"])

# =============================================================================
# SINGLETONS
# =============================================================================

_group_manager: GroupStateManagerKV | None = None
_evolution_client: EvolutionAPIClient | None = None
_user_manager: UserManagerKV | None = None
_formatter = GroupMessageFormatter()


async def get_group_manager() -> GroupStateManagerKV:
    """Dependency: Gerenciador de grupos usando AgentFS KVStore.

    Usa uma sessão AgentFS dedicada (ID fixo) para persistência de grupos.
    """
    global _group_manager
    if _group_manager is None:
        agentfs = await app_state.get_group_agentfs()
        _group_manager = GroupStateManagerKV(agentfs)
    return _group_manager


async def get_user_manager() -> UserManagerKV:
    """Dependency: Gerenciador de usuários usando AgentFS KVStore.

    Usa mesma sessão AgentFS dos grupos para persistência de usuários.
    """
    global _user_manager
    if _user_manager is None:
        agentfs = await app_state.get_group_agentfs()
        _user_manager = UserManagerKV(agentfs)
    return _user_manager


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
    agentfs = await app_state.get_quiz_agentfs()
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
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Webhook para receber mensagens e eventos de grupos WhatsApp.

    Processa:
    - messages.upsert: Mensagens de grupo
    - groups.participants.update: Entrada/saída de participantes (DM automático)

    Mensagens individuais são ignoradas.
    """
    try:
        body = await request.json()
        print(f"[WEBHOOK] Recebido: {body}")  # Debug temporário

        event = body.get("event", "")
        data = body.get("data", {})

        # Log para debug
        print(f"[WEBHOOK] event={event}, keys={list(body.keys())}")

        # =====================================================================
        # EVENTO: Participante entrou/saiu do grupo
        # Delegado ao welcome_router (separação de responsabilidades)
        # =====================================================================
        if event.lower() in ["groups.participants.update", "group-participants.update", "group_participants_update"]:
            # Delegar ao welcome_router para processar DMs de boas-vindas
            user_manager = await welcome_get_user_manager()
            background_tasks.add_task(
                welcome_process_group_join,
                payload=body,
                user_manager=user_manager,
                evolution=evolution,
            )

            # Também processar auto-join no quiz (se houver lobby ativo)
            background_tasks.add_task(
                _process_auto_join_quiz,
                data=data,
                group_manager=group_manager,
                evolution=evolution,
            )

            logger.info(f"[WEBHOOK] Delegando evento de participante ao welcome_router + quiz auto-join")
            return {"status": "ok", "message": "delegated to welcome_router"}

        # =====================================================================
        # EVENTO: Mensagem recebida
        # =====================================================================
        # Evolution API pode enviar como "messages.upsert" ou "MESSAGES_UPSERT"
        if event.lower() != "messages.upsert" and event != "MESSAGES_UPSERT":
            return {"status": "ignored", "reason": f"event {event} not supported"}

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
        if not await group_manager.is_group_allowed(group_id):
            # Grupo não autorizado - ignorar silenciosamente
            logger.debug(f"Grupo não autorizado (ignorando): {group_id}")
            return {"status": "ignored", "reason": "group not whitelisted"}

        # Extrair texto da mensagem
        # messageType pode estar em data ou em data.message
        message_type = data.get("messageType") or message_data.get("messageType")
        text = ""

        if message_type == "conversation":
            # Texto pode estar em data.message.conversation ou direto
            text = message_data.get("conversation", "") or data.get("message", {}).get("conversation", "")
        elif message_type == "extendedTextMessage":
            text = message_data.get("extendedTextMessage", {}).get("text", "")

        print(f"[WEBHOOK] group={remote_jid}, type={message_type}, text={text[:50] if text else 'EMPTY'}")

        if not text:
            return {"status": "ignored", "reason": "no text in message"}

        # Extrair ID do usuário que enviou
        participant = key.get("participant", "")  # Quem enviou no grupo
        if not participant:
            # Fallback para remoteJid (pode ser admin)
            participant = remote_jid

        user_number = participant.replace("@s.whatsapp.net", "").replace("@lid", "")

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
# PARTICIPANT UPDATE PROCESSOR (Entrada/Saída de grupo)
# =============================================================================


async def process_participant_update(
    data: dict,
    group_manager: GroupStateManagerKV,
    user_manager: UserManagerKV,
    evolution: EvolutionAPIClient,
):
    """Processa evento de entrada/saída de participante no grupo.

    Quando alguém ENTRA no grupo:
    1. Registra usuário no sistema (AgentFS/Turso)
    2. Verifica se já recebeu DM de boas-vindas para este grupo
    3. Se não, envia DM individual com mensagem personalizada
    4. Marca como welcomed

    Args:
        data: Dados do evento da Evolution API
        group_manager: Gerenciador de grupos
        user_manager: Gerenciador de usuários
        evolution: Cliente Evolution API
    """
    try:
        # Extrair dados do evento
        # Formato Evolution API: {"groupJid": "xxx@g.us", "participants": ["xxx@s.whatsapp.net"], "action": "add"}
        group_id = data.get("groupJid") or data.get("id") or data.get("groupId", "")
        participants = data.get("participants", [])
        action = data.get("action", "").lower()

        # Também pode vir como: {"participant": "xxx", "action": "add", ...}
        if not participants and data.get("participant"):
            participants = [data.get("participant")]

        logger.info(f"👥 Evento de grupo: {action} em {group_id} - {len(participants)} participantes")

        # Só processar entradas (add/join)
        if action not in ["add", "join", "invite"]:
            logger.debug(f"Ação '{action}' ignorada (não é entrada)")
            return

        # Verificar se grupo está na whitelist
        if not await group_manager.is_group_allowed(group_id):
            logger.debug(f"Grupo {group_id} não está na whitelist, ignorando")
            return

        # Buscar config de welcome do grupo
        welcome_config = await user_manager.get_welcome_config(group_id)
        if not welcome_config.enabled:
            logger.debug(f"Welcome desabilitado para grupo {group_id}")
            return

        # Buscar nome do grupo (se disponível)
        group_name = data.get("groupName") or data.get("subject") or welcome_config.group_name or "Grupo"
        if group_name != welcome_config.group_name:
            welcome_config.group_name = group_name
            await user_manager.save_welcome_config(welcome_config)

        # Processar cada participante que entrou
        for participant_jid in participants:
            try:
                await _send_welcome_dm(
                    participant_jid=participant_jid,
                    group_id=group_id,
                    group_name=group_name,
                    user_manager=user_manager,
                    evolution=evolution,
                    welcome_config=welcome_config,
                )

                # === AUTO-ADICIONAR AO QUIZ SE HOUVER LOBBY ATIVO ===
                await _auto_add_to_quiz_lobby(
                    participant_jid=participant_jid,
                    group_id=group_id,
                    group_manager=group_manager,
                    evolution=evolution,
                )
            except Exception as e:
                logger.error(f"Erro ao enviar welcome para {participant_jid}: {e}")

    except Exception as e:
        logger.error(f"Erro ao processar participant update: {e}", exc_info=True)


async def _process_auto_join_quiz(
    data: dict,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Processa evento de entrada para auto-join no quiz.

    Args:
        data: Dados do evento da Evolution API
        group_manager: Gerenciador de grupos
        evolution: Cliente Evolution API
    """
    try:
        # Extrair dados do evento
        group_id = data.get("groupJid") or data.get("id") or data.get("groupId", "")
        participants_raw = data.get("participants", [])
        action = data.get("action", "").lower()

        # Extrair JIDs dos participantes (podem vir como objetos ou strings)
        participants = []
        for p in participants_raw:
            if isinstance(p, dict):
                # Formato: {"id": "xxx@lid", "phoneNumber": "xxx@s.whatsapp.net"}
                jid = p.get("id") or p.get("phoneNumber", "")
                if jid:
                    participants.append(jid)
            elif isinstance(p, str):
                participants.append(p)

        # Processar cada participante baseado na ação
        for participant_jid in participants:
            if action in ["add", "join", "invite"]:
                # Auto-adicionar ao quiz se houver lobby ativo
                await _auto_add_to_quiz_lobby(
                    participant_jid=participant_jid,
                    group_id=group_id,
                    group_manager=group_manager,
                    evolution=evolution,
                )
            elif action in ["remove", "leave"]:
                # Remover do quiz se estiver participando
                await _auto_remove_from_quiz(
                    participant_jid=participant_jid,
                    group_id=group_id,
                    group_manager=group_manager,
                    evolution=evolution,
                )

    except Exception as e:
        logger.error(f"Erro ao processar auto-join quiz: {e}")


async def _auto_add_to_quiz_lobby(
    participant_jid: str,
    group_id: str,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Auto-adiciona participante ao quiz se houver lobby ativo.

    Args:
        participant_jid: JID do participante
        group_id: ID do grupo
        group_manager: Gerenciador de grupos
        evolution: Cliente Evolution API
    """
    try:
        # Verificar se há sessão de quiz em WAITING_START
        session = await group_manager.get_session(group_id)
        if not session or session.state != GroupQuizState.WAITING_START:
            return  # Não há lobby ativo

        # Extrair ID e criar nome temporário
        user_id = participant_jid.replace("@s.whatsapp.net", "").replace("@lid", "")
        user_name = f"Novo ({user_id[-4:]})"  # Nome temporário até interagir

        # Verificar se já é participante
        if user_id in session.participants:
            return

        # Adicionar ao quiz
        session.get_or_create_participant(user_id, user_name)
        await group_manager.save_session(session)

        logger.info(f"[AUTO-JOIN] {user_name} adicionado automaticamente ao quiz no grupo {group_id}")

        # Notificar no grupo
        await evolution.send_text(
            group_id,
            f"👋 *{user_name}* entrou no grupo e foi adicionado ao quiz!\n\n"
            f"👥 Total: {len(session.participants)} participantes"
        )

    except Exception as e:
        logger.error(f"Erro ao auto-adicionar ao quiz: {e}")


async def _auto_remove_from_quiz(
    participant_jid: str,
    group_id: str,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Remove participante do quiz quando sai do grupo.

    Args:
        participant_jid: JID do participante
        group_id: ID do grupo
        group_manager: Gerenciador de grupos
        evolution: Cliente Evolution API
    """
    try:
        # Verificar se há sessão de quiz ativa
        session = await group_manager.get_session(group_id)
        if not session or session.state == GroupQuizState.IDLE:
            return  # Não há quiz ativo

        # Extrair ID do usuário
        user_id = participant_jid.replace("@s.whatsapp.net", "").replace("@lid", "")

        # Verificar se é participante
        if user_id not in session.participants:
            return

        # Obter nome antes de remover
        participant = session.participants.get(user_id)
        user_name = participant.user_name if participant else f"Usuário ({user_id[-4:]})"

        # Remover do quiz
        del session.participants[user_id]
        await group_manager.save_session(session)

        logger.info(f"[AUTO-REMOVE] {user_name} removido do quiz ao sair do grupo {group_id}")

        # Notificar apenas se ainda houver participantes
        if session.participants:
            await evolution.send_text(
                group_id,
                f"👋 *{user_name}* saiu do grupo e foi removido do quiz.\n\n"
                f"👥 Restam: {len(session.participants)} participantes"
            )

    except Exception as e:
        logger.error(f"Erro ao remover do quiz: {e}")


async def _send_welcome_dm(
    participant_jid: str,
    group_id: str,
    group_name: str,
    user_manager: UserManagerKV,
    evolution: EvolutionAPIClient,
    welcome_config: WelcomeConfig,
):
    """Envia DM de boas-vindas para novo participante.

    Args:
        participant_jid: JID do participante (xxx@s.whatsapp.net)
        group_id: ID do grupo
        group_name: Nome do grupo
        user_manager: Gerenciador de usuários
        evolution: Cliente Evolution API
        welcome_config: Configuração de welcome
    """
    # Limpar JID para obter número
    phone = participant_jid.replace("@s.whatsapp.net", "").replace("@lid", "")

    # Registrar que usuário entrou no grupo
    user, is_new_to_group = await user_manager.user_joined_group(
        user_id=participant_jid,
        user_name=phone,  # Nome será atualizado quando interagir
        group_id=group_id,
        group_name=group_name,
    )

    # Verificar se já recebeu welcome para este grupo
    if user.was_welcomed_for_group(group_id):
        logger.debug(f"Usuário {phone} já foi welcomed para {group_name}")
        return

    # Delay para não parecer bot (configurável)
    if welcome_config.delay_seconds > 0:
        logger.debug(f"Aguardando {welcome_config.delay_seconds}s antes de enviar DM...")
        await asyncio.sleep(welcome_config.delay_seconds)

    # Formatar mensagem de boas-vindas
    welcome_message = welcome_config.format_welcome(
        name=user.display_name or phone,
        phone=phone,
    )

    # Enviar DM individual
    logger.info(f"📤 Enviando DM de boas-vindas para {phone} (grupo: {group_name})")

    try:
        await evolution.send_text(
            number=phone,
            text=welcome_message,
        )

        # Marcar como welcomed
        await user_manager.mark_user_welcomed(participant_jid, group_id)

        # Registrar mensagem no histórico
        await user_manager.add_conversation_message(
            user_id=participant_jid,
            role="assistant",
            content=welcome_message,
        )

        logger.info(f"✅ DM enviado com sucesso para {phone}")

    except Exception as e:
        logger.error(f"❌ Falha ao enviar DM para {phone}: {e}")
        raise


# =============================================================================
# MESSAGE PROCESSOR
# =============================================================================


async def process_group_message(
    group_id: str,
    user_id: str,
    user_name: str,
    text: str,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Processa mensagem do grupo.

    Args:
        group_id: ID do grupo
        user_id: ID do usuário que enviou
        user_name: Nome do usuário
        text: Texto da mensagem
        group_manager: Gerenciador de grupos (KVStore)
        evolution: Cliente Evolution
    """
    try:
        text_upper = text.upper().strip()

        # Normalizar acentos para comandos
        # COMEÇAR -> COMECAR, PRÓXIMA -> PROXIMA, etc.
        text_normalized = (
            text_upper
            .replace("Ç", "C")
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
            .replace("Ã", "A")
            .replace("Õ", "O")
        )

        # Buscar sessão do grupo
        session = await group_manager.get_session(group_id)

        print(f"[PROCESS] Mensagem de {user_name} ({user_id}): '{text}' -> '{text_normalized}' (state: {session.state})")

        # Número do bot (Evolution) - NUNCA deve ser participante
        BOT_NUMBER = "5521936182339"
        is_bot = user_id == BOT_NUMBER or user_id.startswith(BOT_NUMBER)

        if is_bot:
            # Ignorar mensagens do próprio bot
            print(f"[BOT] Ignorando mensagem do próprio bot")
            return

        # === CHECK-IN AUTOMÁTICO (apenas durante quiz ACTIVE) ===
        # No lobby (WAITING_START), participantes devem digitar ENTRAR explicitamente
        is_admin = session.started_by == user_id
        if session.state == GroupQuizState.ACTIVE:
            is_new_participant = user_id not in session.participants
            if is_new_participant and user_id and not user_id.endswith("@g.us") and not is_admin:
                # Registrar participante que entrou durante o quiz
                session.get_or_create_participant(user_id, user_name)

                # Adicionar à ordem de turnos
                session.add_participant_to_turn_order(user_id)

                # Adicionar perguntas bônus para dar chance ao novo participante
                added_questions = session.add_bonus_questions(1)
                await group_manager.save_session(session)

                # Mensagem de boas-vindas com info sobre perguntas extras e turno atual
                current_turn_name = session.get_current_turn_display()
                turn_info = f"\n🎯 *Turno atual:* {current_turn_name}" if current_turn_name else ""
                display_name = _format_participant_name(user_id, user_name)

                if added_questions > 0:
                    welcome_msg = (
                        f"🎉 *{display_name}* entrou no quiz!\n\n"
                        f"🎁 *+{added_questions} perguntas extras* adicionadas!\n"
                        f"📊 Total agora: *{session.total_questions} perguntas*"
                        f"{turn_info}\n\n"
                        f"_Aguarde sua vez! 🧠✨_"
                    )
                else:
                    welcome_msg = (
                        f"🎉 *{display_name}* entrou no quiz!\n"
                        f"📊 Já estamos no máximo de {session.total_questions} perguntas."
                        f"{turn_info}\n\n"
                        f"_Aguarde sua vez! 🧠✨_"
                    )
                await evolution.send_text(group_id, welcome_msg)
                print(f"[CHECK-IN] Novo participante: {user_name} ({user_id}) | +{added_questions} perguntas")

        # Comandos globais (usando text_normalized para aceitar acentos)
        if text_normalized == GroupCommand.AJUDA.value:
            await evolution.send_text(group_id, _formatter.format_help())
            return

        if text_normalized == GroupCommand.REGULAMENTO.value:
            await evolution.send_text(
                group_id,
                "📋 *Regulamento Oficial*\n\n"
                "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view"
            )
            return

        if text_normalized == GroupCommand.STATUS.value:
            await evolution.send_text(group_id, _formatter.format_status(session))
            return

        if text_normalized == GroupCommand.RANKING.value:
            await evolution.send_text(group_id, _formatter.format_ranking(session, show_full=True))
            return

        # Comando SAIR - participante sai do quiz
        if text_normalized == GroupCommand.SAIR.value:
            display_name = _format_participant_name(user_id, user_name)
            if user_id in session.participants:
                del session.participants[user_id]
                await group_manager.save_session(session)
                await evolution.send_text(
                    group_id,
                    f"👋 *{display_name}* saiu do quiz.\n"
                    f"👥 Participantes restantes: {len(session.participants)}"
                )
            else:
                await evolution.send_text(group_id, f"ℹ️ *{display_name}*, você não está participando do quiz.")
            return

        # Comando DUVIDA - consulta o regulamento com pergunta livre
        if text_normalized.startswith(GroupCommand.DUVIDA.value):
            # Extrair a pergunta após "DUVIDA "
            question_text = text[len(GroupCommand.DUVIDA.value):].strip()
            if not question_text:
                await evolution.send_text(
                    group_id,
                    "❓ *Como usar o comando DUVIDA:*\n\n"
                    "Digite *DUVIDA* seguido da sua pergunta.\n\n"
                    "Exemplo:\n"
                    "_DUVIDA como funciona o cashback?_\n"
                    "_DUVIDA qual o prazo de pagamento?_"
                )
            else:
                await handle_doubt_request(group_id, user_id, user_name, question_text, session, evolution)
            return

        # Comandos baseados em estado (usar text_normalized para comandos)
        if session.state == GroupQuizState.IDLE:
            await handle_idle_state(group_id, user_id, user_name, text_normalized, session, group_manager, evolution)

        elif session.state == GroupQuizState.WAITING_START:
            await handle_waiting_start_state(group_id, user_id, user_name, text_normalized, session, group_manager, evolution)

        elif session.state == GroupQuizState.ACTIVE:
            await handle_active_state(group_id, user_id, user_name, text_normalized, text_upper, session, group_manager, evolution)

        elif session.state == GroupQuizState.WAITING_NEXT:
            await handle_waiting_next_state(group_id, text_normalized, session, group_manager, evolution)

        elif session.state == GroupQuizState.FINISHED:
            await handle_finished_state(group_id, user_id, user_name, text_normalized, session, group_manager, evolution)

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
    text_normalized: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Nenhum quiz ativo - criar lobby."""
    if text_normalized == GroupCommand.INICIAR.value:
        # Criar lobby para aguardar participantes
        # Admin NÃO é adicionado automaticamente como participante
        session.state = GroupQuizState.WAITING_START
        session.started_by = user_id
        await group_manager.save_session(session)

        # Enviar mensagem de lobby
        await evolution.send_text(group_id, _formatter.format_lobby_created(user_name, session))
    else:
        # Primeira mensagem ou comando desconhecido
        await evolution.send_text(group_id, _formatter.format_welcome())


async def handle_waiting_start_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_normalized: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Lobby ativo - aguardando participantes."""
    # Comando ENTRAR - registrar participante
    if text_normalized == GroupCommand.ENTRAR.value:
        display_name = _format_participant_name(user_id, user_name)
        if user_id not in session.participants:
            session.get_or_create_participant(user_id, user_name)
            await group_manager.save_session(session)
            await evolution.send_text(
                group_id,
                f"✅ *{display_name}* entrou no quiz!\n\n"
                f"👥 *Participantes:* {len(session.participants)}\n\n"
                "_Digite *COMECAR* quando todos estiverem prontos!_"
            )
        else:
            await evolution.send_text(group_id, f"ℹ️ *{display_name}*, você já está no quiz!")
        return

    # Comando COMECAR - iniciar quiz de fato
    if text_normalized == GroupCommand.COMECAR.value:

        # Validar: precisa ter pelo menos 1 participante no lobby
        if len(session.participants) == 0:
            await evolution.send_text(
                group_id,
                "⚠️ *Ninguém entrou no quiz ainda!*\n\n"
                "Pelo menos 1 pessoa precisa digitar *ENTRAR* antes de começar."
            )
            return

        # Iniciar quiz
        try:
            agentfs = await app_state.get_quiz_agentfs()
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

            # Calcular total de perguntas baseado nos participantes do lobby
            total_questions = session.calculate_initial_questions()

            # Iniciar quiz
            quiz_id, first_question = await engine.start_quiz()

            # Inicializar sistema de turnos
            session.initialize_turn_order()

            # Atualizar sessão
            session.quiz_id = quiz_id
            session.state = GroupQuizState.ACTIVE
            session.started_at = None
            session.start_new_question(1)
            await group_manager.save_session(session)

            # Avisar que quiz iniciou com total de perguntas
            await evolution.send_text(group_id, _formatter.format_quiz_started_with_participants(session))

            # Simular digitação antes da primeira pergunta
            await evolution.send_typing(group_id, duration=2500)
            await asyncio.sleep(2.5)

            # Enviar primeira pergunta (com nome + número de quem é a vez)
            current_turn_name = session.get_current_turn_display()
            msg = _formatter.format_question(
                first_question,
                1,
                total_questions=session.total_questions,
                current_turn_name=current_turn_name,
            )
            await evolution.send_text(group_id, msg)

        except Exception as e:
            logger.error(f"Erro ao iniciar quiz no grupo: {e}", exc_info=True)
            await evolution.send_text(group_id, "⚠️ Erro ao iniciar quiz. Tente novamente.")
        return

    # Comando PARAR - cancelar lobby
    if text_normalized == GroupCommand.PARAR.value:
        await group_manager.reset_group(group_id)
        await evolution.send_text(group_id, "❌ Lobby cancelado.")
        return

    # Mostrar status do lobby para qualquer outra mensagem
    await evolution.send_text(group_id, _formatter.format_lobby_status(session))


async def handle_active_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_normalized: str,
    text_upper: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Quiz ativo - recebendo respostas."""
    # Verificar se é comando PARAR
    if text_normalized == GroupCommand.PARAR.value:
        await group_manager.reset_group(group_id)
        await evolution.send_text(group_id, _formatter.format_quiz_cancelled(user_name))
        return

    # Verificar se é comando DICA
    if text_normalized == GroupCommand.DICA.value:
        await handle_hint_request(group_id, session, group_manager, evolution)
        return

    # Verificar se é comando PROXIMA/PROXIMO - avança para próxima pergunta
    if text_normalized in [GroupCommand.PROXIMA.value, "PROXIMO"]:
        await send_next_group_question(group_id, session, group_manager, evolution)
        return

    # Verificar se é resposta (A/B/C/D) - usar text_upper (sem normalização)
    if text_upper in [GroupCommand.A.value, GroupCommand.B.value, GroupCommand.C.value, GroupCommand.D.value]:
        await handle_group_answer(group_id, user_id, user_name, text_upper, session, group_manager, evolution)
        return

    # Só tratar como dúvida se:
    # 1. Começar explicitamente com "DUVIDA"
    # 2. OU terminar com "?" (indicando uma pergunta)
    # Isso evita tratar comentários/feedback como dúvidas
    is_explicit_doubt = text_normalized.startswith(GroupCommand.DUVIDA.value)
    is_question = text_upper.strip().endswith("?")

    if is_explicit_doubt or is_question:
        original_text = text_normalized.replace(GroupCommand.DUVIDA.value, "").strip() if is_explicit_doubt else text_upper.strip()
        if original_text and len(original_text) > 2:  # Ignorar mensagens muito curtas
            await handle_doubt_request(group_id, user_id, user_name, original_text, session, evolution)


async def handle_doubt_request(
    group_id: str,
    user_id: str,
    user_name: str,
    question_text: str,
    session: Any | None,
    evolution: EvolutionAPIClient,
):
    """Responde dúvida sobre o regulamento usando RAG.

    Fluxo:
    1. Busca informação relevante no RAG
    2. Gera resposta usando LLM
    3. Envia resposta ao grupo
    4. Se quiz ativo, relembra as opções da pergunta atual
    """
    try:
        # Simular digitação enquanto busca (sem mensagem de "buscando...")
        await evolution.send_typing(group_id, duration=3000)

        # Formatar nome do usuário com número
        display_name = _format_participant_name(user_id, user_name)

        # Buscar no RAG
        rag = await app_state.get_rag()
        search_results = await rag.search(question_text, top_k=3)

        if not search_results:
            await evolution.send_text(
                group_id,
                f"❓ *{display_name}*, não encontrei informações sobre isso no regulamento.\n\n"
                "📋 Consulte o regulamento completo:\n"
                "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view"
            )
            return

        # Montar contexto das buscas
        context_parts = []
        for result in search_results:
            if hasattr(result, 'content'):
                context_parts.append(result.content[:500])
            elif isinstance(result, dict) and 'content' in result:
                context_parts.append(result['content'][:500])

        context = "\n".join(context_parts)

        # Usar LLM para gerar resposta
        llm = app_state.get_llm()

        prompt = f"""Você é um assistente especializado no programa Renda Extra Ton.

Um participante do quiz fez a seguinte pergunta:
"{question_text}"

Com base no contexto do regulamento abaixo, responda de forma clara e objetiva (máximo 3 frases).

CONTEXTO DO REGULAMENTO:
{context}

IMPORTANTE:
- Responda APENAS com base no regulamento
- Se não tiver certeza, diga que o participante deve consultar o regulamento completo
- Seja direto e educativo

Responda de forma amigável, sem prefixos como "Resposta:" ou similares."""

        llm_response = await llm.completion(
            [{"role": "user", "content": prompt}],
            max_tokens=200
        )
        answer_text = llm_response.content.strip() if llm_response.content else "Consulte o regulamento para mais detalhes."

        # Montar mensagem de resposta
        response_msg = f"💡 *{display_name}*, sobre sua dúvida:\n\n{answer_text}"

        # Se quiz está ativo, relembrar as opções da pergunta atual
        if session and session.state == GroupQuizState.ACTIVE and session.quiz_id:
            agentfs = await app_state.get_quiz_agentfs()
            rag_engine = await app_state.get_rag()
            engine = QuizEngine(agentfs=agentfs, rag=rag_engine)

            question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
            if question and hasattr(question, 'options'):
                options_lines = []
                for opt in question.options:
                    options_lines.append(f"*{opt.label})* {opt.text}")
                options_text = "\n".join(options_lines)

                response_msg += (
                    f"\n\n───────────────\n"
                    f"📝 *Voltando à pergunta {session.current_question}/{session.total_questions}:*\n\n"
                    f"{options_text}\n\n"
                    f"_Responda com A, B, C ou D_"
                )

        await evolution.send_text(group_id, response_msg)

    except Exception as e:
        logger.error(f"Erro ao responder dúvida: {e}", exc_info=True)
        display_name = _format_participant_name(user_id, user_name)
        await evolution.send_text(
            group_id,
            f"⚠️ *{display_name}*, não consegui buscar a informação agora.\n\n"
            "📋 Consulte o regulamento:\n"
            "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view"
        )


async def handle_hint_request(
    group_id: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Gera uma dica para a pergunta atual usando RAG.

    Fluxo:
    1. Gera dica não repetitiva baseada no RAG
    2. Após a dica, relembra as opções de resposta
    """
    # Validar que há um quiz ativo
    if not session.quiz_id:
        await evolution.send_text(
            group_id,
            "⚠️ *Nenhum quiz ativo para dar dica.*\n\n"
            "Digite *INICIAR* para começar um novo quiz!"
        )
        return

    try:
        # Simular digitação enquanto busca (sem mensagem de "buscando...")
        await evolution.send_typing(group_id, duration=3000)

        # Buscar pergunta atual
        agentfs = await app_state.get_quiz_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)

        question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
        if not question:
            await evolution.send_text(
                group_id,
                "⚠️ *Não foi possível buscar a dica.*\n\n"
                "Possíveis causas:\n"
                "• Quiz não iniciado corretamente\n"
                "• Sessão expirada\n\n"
                "_Tente reiniciar o quiz com INICIAR._"
            )
            return

        # Extrair o tema/tópico da pergunta para buscar no RAG
        question_text = question.question if hasattr(question, 'question') else str(question)
        topic = question.topic if hasattr(question, 'topic') else ""

        # Buscar informações relevantes no RAG
        search_query = f"{topic} {question_text}" if topic else question_text
        search_results = await rag.search(search_query, top_k=3)

        # Obter dicas já dadas para não repetir
        current_state = session.get_current_question_state()
        previous_hints = current_state.hints_given if current_state else []

        if not search_results:
            hint_text = "Leia com atenção as alternativas e pense no que faz mais sentido! 🧠"
        else:
            # Montar contexto das buscas
            context_parts = []
            for result in search_results:
                if hasattr(result, 'content'):
                    context_parts.append(result.content[:500])
                elif isinstance(result, dict) and 'content' in result:
                    context_parts.append(result['content'][:500])

            context = "\n".join(context_parts)

            # Usar LLM para gerar dica baseada no contexto
            llm = app_state.get_llm()

            # Incluir dicas anteriores para evitar repetição
            previous_hints_text = ""
            if previous_hints:
                previous_hints_text = f"\n\nDICAS JÁ DADAS (NÃO REPITA ESTAS INFORMAÇÕES):\n" + "\n".join(f"- {h}" for h in previous_hints)

            hint_prompt = f"""Você é um assistente de quiz sobre o programa Renda Extra Ton.

Com base no contexto do regulamento abaixo, dê uma DICA breve (máximo 2 frases) que ajude a responder esta pergunta, SEM revelar a resposta diretamente.

PERGUNTA: {question_text}

CONTEXTO DO REGULAMENTO:
{context}{previous_hints_text}

IMPORTANTE:
- Dê uma dica DIFERENTE das anteriores
- Não revele a resposta, apenas dê uma pista útil
- Seja direto e objetivo

Responda APENAS com a dica, sem prefixos como "Dica:" ou similares."""

            llm_response = await llm.completion(
                [{"role": "user", "content": hint_prompt}],
                max_tokens=150
            )
            hint_text = llm_response.content.strip() if llm_response.content else "Leia o regulamento com atenção!"

        # Salvar dica no histórico para não repetir
        if current_state and hint_text:
            current_state.hints_given.append(hint_text)
            await group_manager.save_session(session)

        # Formatar opções para relembrar
        options_text = ""
        if hasattr(question, 'options'):
            options_lines = []
            for opt in question.options:
                options_lines.append(f"*{opt.label})* {opt.text}")
            options_text = "\n".join(options_lines)

        # Enviar dica formatada + relembrar opções
        hint_msg = (
            f"💡 *Dica:*\n\n"
            f"{hint_text}\n\n"
            f"───────────────\n"
            f"📝 *Suas opções:*\n\n"
            f"{options_text}\n\n"
            f"_Responda com A, B, C ou D_"
        )
        await evolution.send_text(group_id, hint_msg)

    except Exception as e:
        logger.error(f"Erro ao gerar dica: {e}", exc_info=True)
        await evolution.send_text(group_id, "⚠️ Erro ao buscar dica. Tente novamente.")


async def handle_group_answer(
    group_id: str,
    user_id: str,
    user_name: str,
    answer: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Processa resposta de participante.

    Fluxo:
    1. Verifica se é a vez do usuário (sistema de turnos)
    2. Valida resposta
    3. Mostra se acertou/errou com explicação do RAG
    4. Mostra posição no ranking (se houver mais de 1 participante)
    5. Avança turno e envia próxima pergunta
    """
    # Validar que há um quiz ativo
    if not session.quiz_id:
        logger.warning(f"[handle_group_answer] quiz_id é None para grupo {group_id}")
        return

    try:
        # === SISTEMA DE TURNOS ===
        # Se não for a vez do usuário, informar de quem é a vez
        if not session.is_user_turn(user_id):
            current_turn_display = session.get_current_turn_display()
            display_name = _format_participant_name(user_id, user_name)

            if current_turn_display:
                await evolution.send_text(
                    group_id,
                    f"⏳ *{display_name}*, ainda não é sua vez!\n\n"
                    f"🎯 Aguardando resposta de *{current_turn_display}*\n\n"
                    f"💡 _Enquanto isso, você pode tirar dúvidas sobre o regulamento digitando sua pergunta._"
                )
            else:
                # Turno não inicializado - reinicializar
                session.initialize_turn_order()
                if session.turn_order:
                    session.current_turn_user_id = session.turn_order[0]
                    await group_manager.save_session(session)
                    current_turn_display = session.get_current_turn_display()
                    await evolution.send_text(
                        group_id,
                        f"🔄 Sistema de turnos reiniciado!\n\n"
                        f"🎯 Vez de *{current_turn_display}* responder."
                    )
            return

        # Verificar se já respondeu (redundante com turnos, mas mantido por segurança)
        if session.has_answered(user_id):
            return

        agentfs = await app_state.get_quiz_agentfs()
        rag = await app_state.get_rag()
        engine = QuizEngine(agentfs=agentfs, rag=rag)
        scoring = QuizScoringEngine()

        # Buscar pergunta atual (silencioso - não mostra erro ao usuário)
        question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
        if not question:
            logger.error(f"[SILENT] Falha ao carregar pergunta {session.current_question} do quiz {session.quiz_id}")
            return

        # Converter resposta para índice
        answer_index = {"A": 0, "B": 1, "C": 2, "D": 3}[answer]

        # Avaliar resposta
        result = scoring.evaluate_answer(question, answer_index)
        is_correct = result["is_correct"]

        # Salvar resposta na sessão
        session.add_answer(
            user_id=user_id,
            user_name=user_name,
            answer_index=answer_index,
            is_correct=is_correct,
            points=result["points_earned"],
        )
        await group_manager.save_session(session)

        # Logar resposta
        quiz_logger = await get_quiz_logger()
        await quiz_logger.answer_received(
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=session.quiz_id,
            question_num=session.current_question,
            answer=answer,
            is_correct=is_correct,
            points=result["points_earned"],
        )

        # Gerar explicação usando RAG
        explanation = await generate_answer_explanation(
            question=question,
            user_answer=answer,
            is_correct=is_correct,
            rag=rag,
        )

        # === MONTAR FEEDBACK ===
        correct_opt = question.options[question.correct_index]
        display_name = _format_participant_name(user_id, user_name)

        if is_correct:
            feedback = f"✅ *{display_name}* acertou! +{result['points_earned']} pts\n\n"
        else:
            feedback = f"❌ *{display_name}* errou!\n\n"
            feedback += f"📍 *Resposta correta:* {correct_opt.label}) {correct_opt.text}\n\n"

        # Adicionar explicação do RAG
        if explanation:
            feedback += f"📚 *Por quê?*\n_{explanation}_\n\n"

        # Mostrar ranking APENAS se houver mais de 1 participante
        total_participants = len(session.participants)
        if total_participants > 1:
            ranking = session.get_ranking()
            user_position = next((i + 1 for i, p in enumerate(ranking) if p.user_id == user_id), None)
            user_score = session.participants.get(user_id)

            if user_position and user_score:
                feedback += f"───────────────\n"
                feedback += f"🏆 *Sua posição:* {user_position}º de {total_participants}\n"
                feedback += f"📊 *Pontuação:* {user_score.total_score} pts ({user_score.correct_answers}/{user_score.total_answers} acertos)\n"

        await evolution.send_text(group_id, feedback)

        # === AVANÇAR TURNO E PRÓXIMA PERGUNTA ===
        # Avançar para o próximo jogador
        session.advance_turn()

        # Dar tempo para pessoa ler o feedback (4 segundos)
        await asyncio.sleep(4)

        # Simular digitação enquanto "prepara" próxima pergunta (mais realista)
        await evolution.send_typing(group_id, duration=3000)
        await asyncio.sleep(3)

        # Verificar se acabou o quiz (usando total dinâmico)
        if session.current_question >= session.total_questions:
            session.state = GroupQuizState.FINISHED
            await group_manager.save_session(session)
            await evolution.send_text(group_id, _formatter.format_final_results(session))
            return

        # Avançar para próxima pergunta
        session.current_question += 1
        session.start_new_question(session.current_question)
        await group_manager.save_session(session)

        # Buscar próxima pergunta (com retry silencioso)
        next_question = None
        for attempt in range(3):
            next_question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
            if next_question:
                break
            logger.warning(f"[RETRY] Tentativa {attempt + 1}/3 falhou ao carregar pergunta {session.current_question}")
            await asyncio.sleep(2)

        if not next_question:
            logger.error(f"[ERRO] Falha ao carregar pergunta {session.current_question} após 3 tentativas")
            # Não mostrar erro no grupo, apenas logar
            return

        # Enviar próxima pergunta (com nome + número de quem é a vez)
        current_turn_name = session.get_current_turn_display()
        question_msg = _formatter.format_question(
            next_question,
            session.current_question,
            total_questions=session.total_questions,
            current_turn_name=current_turn_name,
        )
        await evolution.send_text(group_id, question_msg)

    except Exception as e:
        logger.error(f"Erro ao processar resposta no grupo: {e}", exc_info=True)
        try:
            quiz_logger = await get_quiz_logger()
            await quiz_logger.error(
                message="Erro ao processar resposta",
                error=str(e),
                group_id=group_id,
                user_id=user_id,
                quiz_id=session.quiz_id if session else None,
            )
        except:
            pass
        # Erro silencioso - não mostrar ao usuário, apenas logar


async def generate_answer_explanation(
    question: Any,
    user_answer: str,
    is_correct: bool,
    rag: Any,
) -> str | None:
    """Gera explicação para a resposta usando RAG e LLM.

    Args:
        question: Objeto da pergunta
        user_answer: Resposta do usuário (A/B/C/D)
        is_correct: Se a resposta está correta
        rag: Instância do SearchEngine

    Returns:
        Explicação gerada ou None se falhar
    """
    try:
        # Extrair texto da pergunta
        question_text = question.question if hasattr(question, 'question') else str(question)
        topic = question.topic if hasattr(question, 'topic') else ""

        # Resposta correta
        correct_opt = question.options[question.correct_index]
        correct_answer = f"{correct_opt.label}) {correct_opt.text}"

        # Buscar contexto no RAG
        search_query = f"{topic} {question_text}" if topic else question_text
        search_results = await rag.search(search_query, top_k=2)

        if not search_results:
            return None

        # Montar contexto
        context_parts = []
        for result in search_results:
            if hasattr(result, 'content'):
                context_parts.append(result.content[:500])
            elif isinstance(result, dict) and 'content' in result:
                context_parts.append(result['content'][:500])

        context = "\n".join(context_parts)

        if not context:
            return None

        # Gerar explicação com LLM
        llm = app_state.get_llm()

        if is_correct:
            prompt = f"""Você é um assistente de quiz sobre o programa Renda Extra Ton.

O participante ACERTOU a pergunta. Dê uma explicação BREVE (1-2 frases) confirmando por que a resposta está correta, baseada no regulamento.

PERGUNTA: {question_text}
RESPOSTA CORRETA: {correct_answer}

CONTEXTO DO REGULAMENTO:
{context}

Responda de forma direta e educativa, confirmando a informação do regulamento."""
        else:
            # Resposta que o usuário escolheu
            user_idx = {"A": 0, "B": 1, "C": 2, "D": 3}[user_answer]
            user_opt = question.options[user_idx]
            user_answer_text = f"{user_opt.label}) {user_opt.text}"

            prompt = f"""Você é um assistente de quiz sobre o programa Renda Extra Ton.

O participante ERROU a pergunta. Explique BREVEMENTE (1-2 frases) por que a resposta dele está errada e por que a correta é a certa, baseado no regulamento.

PERGUNTA: {question_text}
RESPOSTA DO PARTICIPANTE (ERRADA): {user_answer_text}
RESPOSTA CORRETA: {correct_answer}

CONTEXTO DO REGULAMENTO:
{context}

Responda de forma educativa, explicando o erro e a informação correta do regulamento."""

        llm_response = await llm.completion(
            [{"role": "user", "content": prompt}],
            max_tokens=150
        )
        return llm_response.content.strip() if llm_response.content else None

    except Exception as e:
        logger.error(f"Erro ao gerar explicação: {e}")
        return None


async def handle_waiting_next_state(
    group_id: str,
    text_normalized: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Aguardando comando para próxima pergunta."""
    if text_normalized == GroupCommand.PROXIMA.value:
        await send_next_group_question(group_id, session, group_manager, evolution)


async def send_next_group_question(
    group_id: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Envia próxima pergunta para o grupo."""
    # Validar que há um quiz ativo
    if not session.quiz_id:
        logger.warning(f"[send_next_group_question] quiz_id é None para grupo {group_id}")
        await evolution.send_text(
            group_id,
            "⚠️ *Nenhum quiz ativo.*\n\n"
            "Digite *INICIAR* para começar um novo quiz!"
        )
        return

    try:
        # Mostrar resultado da pergunta anterior
        agentfs = await app_state.get_quiz_agentfs()
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

                # Simular digitação antes da próxima pergunta
                await evolution.send_typing(group_id, duration=2000)
                await asyncio.sleep(2)

        # Avançar turno para o próximo jogador
        session.advance_turn()

        # Verificar se acabou (usando total dinâmico)
        if session.current_question >= session.total_questions:
            session.state = GroupQuizState.FINISHED
            await group_manager.save_session(session)
            await evolution.send_text(group_id, _formatter.format_final_results(session))
            return

        # Avançar para próxima pergunta
        session.current_question += 1
        session.start_new_question(session.current_question)
        session.state = GroupQuizState.ACTIVE
        await group_manager.save_session(session)

        # Buscar próxima pergunta (com retry silencioso)
        next_question = None
        for attempt in range(3):
            next_question = await engine.get_question(session.quiz_id, session.current_question, timeout=30.0)
            if next_question:
                break
            logger.warning(f"[RETRY] Tentativa {attempt + 1}/3 falhou ao carregar pergunta {session.current_question}")
            await asyncio.sleep(2)

        if not next_question:
            logger.error(f"[ERRO] Falha ao carregar pergunta {session.current_question} após 3 tentativas")
            return

        # Enviar com nome + número de quem é a vez
        current_turn_name = session.get_current_turn_display()
        msg = _formatter.format_question(
            next_question,
            session.current_question,
            total_questions=session.total_questions,
            current_turn_name=current_turn_name,
        )
        await evolution.send_text(group_id, msg)

    except Exception as e:
        logger.error(f"Erro ao enviar próxima pergunta: {e}", exc_info=True)
        await evolution.send_text(group_id, "⚠️ Erro ao avançar para próxima pergunta.")


async def handle_finished_state(
    group_id: str,
    user_id: str,
    user_name: str,
    text_normalized: str,
    session: Any,
    group_manager: GroupStateManagerKV,
    evolution: EvolutionAPIClient,
):
    """Quiz finalizado."""
    if text_normalized == GroupCommand.INICIAR.value:
        # Resetar e iniciar novo quiz
        await group_manager.reset_group(group_id)
        new_session = await group_manager.get_session(group_id)
        await handle_idle_state(group_id, user_id, user_name, text_normalized, new_session, group_manager, evolution)


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================


@router.post("/whitelist/add/{group_id}")
async def add_group_to_whitelist(
    group_id: str,
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
):
    """Adiciona grupo à whitelist (ADMIN).

    Args:
        group_id: ID do grupo WhatsApp (ex: 123456789@g.us)
    """
    success = await group_manager.add_allowed_group(group_id)
    if success:
        return {"status": "ok", "message": f"Grupo {group_id} adicionado à whitelist"}
    return {"status": "ok", "message": f"Grupo {group_id} já estava na whitelist"}


@router.delete("/whitelist/remove/{group_id}")
async def remove_group_from_whitelist(
    group_id: str,
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
):
    """Remove grupo da whitelist (ADMIN).

    Args:
        group_id: ID do grupo WhatsApp
    """
    success = await group_manager.remove_allowed_group(group_id)
    if success:
        return {"status": "ok", "message": f"Grupo {group_id} removido da whitelist"}
    return {"status": "error", "message": f"Grupo {group_id} não estava na whitelist"}


@router.get("/whitelist")
async def list_whitelisted_groups(
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
):
    """Lista grupos autorizados (ADMIN)."""
    groups = await group_manager.list_allowed_groups()
    return {"total": len(groups), "groups": groups}


@router.get("/active")
async def get_active_group_sessions(
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
):
    """Lista grupos com quiz ativo (ADMIN)."""
    active = await group_manager.get_active_groups()
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
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
):
    """Reseta sessão de um grupo (ADMIN)."""
    await group_manager.reset_group(group_id)
    return {"status": "ok", "message": f"Sessão de {group_id} resetada"}


@router.post("/send-hint/{group_id}")
async def send_hint_to_group(
    group_id: str,
    group_manager: GroupStateManagerKV = Depends(get_group_manager),
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Envia dica para o grupo (ADMIN)."""
    session = await group_manager.get_session(group_id)
    if session.state.value != "active":
        return {"status": "error", "message": "Nenhum quiz ativo"}

    await handle_hint_request(group_id, session, group_manager, evolution)
    return {"status": "ok", "message": f"Dica enviada para {group_id}"}


# =============================================================================
# LOGS ENDPOINTS
# =============================================================================


@router.get("/logs")
async def get_quiz_logs(
    category: str | None = None,
    date: str | None = None,
    group_id: str | None = None,
    limit: int = 50,
):
    """Lista logs do quiz (ADMIN).

    Args:
        category: Filtrar por categoria (webhook, message, command, quiz, participant, rag, llm, error, system, api)
        date: Filtrar por data (YYYY-MM-DD)
        group_id: Filtrar por grupo
        limit: Limite de resultados (default 50)
    """
    try:
        quiz_logger = await get_quiz_logger()

        # Converter categoria se fornecida
        cat = None
        if category:
            try:
                cat = LogCategory(category)
            except ValueError:
                return {"status": "error", "message": f"Categoria inválida: {category}"}

        logs = await quiz_logger.get_logs(
            category=cat,
            date=date,
            group_id=group_id,
            limit=limit,
        )

        return {
            "total": len(logs),
            "logs": [log.model_dump(mode="json") for log in logs],
        }
    except Exception as e:
        logger.error(f"Erro ao buscar logs: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/logs/errors")
async def get_recent_errors(limit: int = 20):
    """Lista erros recentes (ADMIN)."""
    try:
        quiz_logger = await get_quiz_logger()
        errors = await quiz_logger.get_recent_errors(limit=limit)
        return {
            "total": len(errors),
            "errors": [log.model_dump(mode="json") for log in errors],
        }
    except Exception as e:
        logger.error(f"Erro ao buscar erros: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/logs/group/{group_id}")
async def get_group_logs(group_id: str, limit: int = 50):
    """Lista atividade de um grupo específico (ADMIN)."""
    try:
        quiz_logger = await get_quiz_logger()
        logs = await quiz_logger.get_group_activity(group_id=group_id, limit=limit)
        return {
            "total": len(logs),
            "logs": [log.model_dump(mode="json") for log in logs],
        }
    except Exception as e:
        logger.error(f"Erro ao buscar logs do grupo: {e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# USER MANAGEMENT ENDPOINTS (Welcome DM / Relacionamento)
# =============================================================================


@router.get("/users/stats")
async def get_user_stats(
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Retorna estatísticas de usuários."""
    try:
        stats = await user_manager.get_stats()
        return {"status": "ok", "data": stats}
    except Exception as e:
        logger.error(f"Erro ao buscar stats: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/users/{user_id}")
async def get_user_profile(
    user_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Busca perfil de um usuário específico."""
    try:
        # Adicionar sufixo se não tiver
        if not user_id.endswith("@s.whatsapp.net"):
            user_id = f"{user_id}@s.whatsapp.net"

        user = await user_manager.get_user(user_id)
        return {"status": "ok", "data": user.model_dump(mode="json")}
    except Exception as e:
        logger.error(f"Erro ao buscar usuário: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/users/group/{group_id}")
async def list_users_in_group(
    group_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Lista todos os usuários de um grupo."""
    try:
        users = await user_manager.get_users_in_group(group_id)
        return {
            "status": "ok",
            "total": len(users),
            "users": [u.model_dump(mode="json") for u in users],
        }
    except Exception as e:
        logger.error(f"Erro ao listar usuários do grupo: {e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# WELCOME CONFIG ENDPOINTS
# =============================================================================


@router.get("/welcome/{group_id}")
async def get_welcome_config(
    group_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Busca configuração de boas-vindas de um grupo."""
    try:
        config = await user_manager.get_welcome_config(group_id)
        return {"status": "ok", "data": config.model_dump(mode="json")}
    except Exception as e:
        logger.error(f"Erro ao buscar welcome config: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/welcome/{group_id}")
async def update_welcome_config(
    group_id: str,
    request: Request,
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Atualiza configuração de boas-vindas de um grupo.

    Body JSON:
    {
        "enabled": true,
        "welcome_message": "Olá {name}! Bem-vindo ao {group}!",
        "group_name": "Meu Grupo",
        "delay_seconds": 5,
        "ai_enabled": true
    }
    """
    try:
        body = await request.json()
        config = await user_manager.get_welcome_config(group_id)

        # Atualizar campos fornecidos
        if "enabled" in body:
            config.enabled = body["enabled"]
        if "welcome_message" in body:
            config.welcome_message = body["welcome_message"]
        if "group_name" in body:
            config.group_name = body["group_name"]
        if "delay_seconds" in body:
            config.delay_seconds = body["delay_seconds"]
        if "ai_enabled" in body:
            config.ai_enabled = body["ai_enabled"]
        if "follow_up_enabled" in body:
            config.follow_up_enabled = body["follow_up_enabled"]

        await user_manager.save_welcome_config(config)

        return {"status": "ok", "data": config.model_dump(mode="json")}
    except Exception as e:
        logger.error(f"Erro ao atualizar welcome config: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/welcome/{group_id}/toggle")
async def toggle_welcome(
    group_id: str,
    enabled: bool = True,
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Ativa/desativa boas-vindas para um grupo."""
    try:
        config = await user_manager.toggle_welcome(group_id, enabled)
        return {
            "status": "ok",
            "message": f"Welcome {'ativado' if enabled else 'desativado'} para {group_id}",
            "data": config.model_dump(mode="json"),
        }
    except Exception as e:
        logger.error(f"Erro ao toggle welcome: {e}")
        return {"status": "error", "message": str(e)}


# =============================================================================
# WEBHOOK SETUP ENDPOINTS
# =============================================================================


@router.post("/setup/webhook")
async def setup_evolution_webhook(
    request: Request,
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
):
    """Configura webhook da Evolution API para receber eventos de grupo.

    Body JSON:
    {
        "webhook_url": "https://seu-dominio.com/whatsapp/group/webhook"
    }

    Eventos configurados:
    - MESSAGES_UPSERT: Mensagens recebidas
    - GROUPS_UPDATE: Atualizações de grupo
    - GROUP_PARTICIPANTS_UPDATE: Entrada/saída de participantes
    """
    try:
        body = await request.json()
        webhook_url = body.get("webhook_url")

        if not webhook_url:
            return {"status": "error", "message": "webhook_url é obrigatório"}

        # Eventos necessários para funcionalidade completa
        events = [
            "MESSAGES_UPSERT",
            "GROUPS_UPDATE",
            "GROUP_PARTICIPANTS_UPDATE",
            "GROUPS_UPSERT",
        ]

        result = await evolution.set_webhook(webhook_url, events)

        return {
            "status": "ok",
            "message": "Webhook configurado com sucesso",
            "webhook_url": webhook_url,
            "events": events,
            "response": result,
        }
    except Exception as e:
        logger.error(f"Erro ao configurar webhook: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/send-dm/{phone}")
async def send_dm_to_user(
    phone: str,
    request: Request,
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Envia mensagem DM para um usuário específico.

    Body JSON:
    {
        "message": "Olá! Como posso ajudar?"
    }
    """
    try:
        body = await request.json()
        message = body.get("message")

        if not message:
            return {"status": "error", "message": "message é obrigatório"}

        # Limpar número
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "")

        # Enviar mensagem
        result = await evolution.send_text(phone_clean, message)

        # Registrar no histórico do usuário
        user_id = f"{phone_clean}@s.whatsapp.net"
        await user_manager.add_conversation_message(user_id, "assistant", message)

        return {
            "status": "ok",
            "message": "DM enviado com sucesso",
            "phone": phone_clean,
            "response": result,
        }
    except Exception as e:
        logger.error(f"Erro ao enviar DM: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/send-welcome/{group_id}/{phone}")
async def send_manual_welcome(
    group_id: str,
    phone: str,
    evolution: EvolutionAPIClient = Depends(get_evolution_client),
    user_manager: UserManagerKV = Depends(get_user_manager),
):
    """Envia mensagem de boas-vindas manualmente para um usuário.

    Útil para reenviar welcome ou testar configuração.
    """
    try:
        # Limpar número
        phone_clean = phone.replace("+", "").replace("-", "").replace(" ", "")
        user_id = f"{phone_clean}@s.whatsapp.net"

        # Buscar config de welcome
        config = await user_manager.get_welcome_config(group_id)

        # Buscar usuário
        user = await user_manager.get_user(user_id)

        # Formatar mensagem
        welcome_message = config.format_welcome(
            name=user.display_name or phone_clean,
            phone=phone_clean,
        )

        # Enviar
        result = await evolution.send_text(phone_clean, welcome_message)

        # Marcar como welcomed
        await user_manager.mark_user_welcomed(user_id, group_id)

        # Registrar no histórico
        await user_manager.add_conversation_message(user_id, "assistant", welcome_message)

        return {
            "status": "ok",
            "message": "Welcome enviado com sucesso",
            "phone": phone_clean,
            "group_id": group_id,
            "response": result,
        }
    except Exception as e:
        logger.error(f"Erro ao enviar welcome manual: {e}")
        return {"status": "error", "message": str(e)}
