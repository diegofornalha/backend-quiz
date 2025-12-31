"""
Router para Welcome DMs - Mensagens individuais automáticas.

Responsabilidade ÚNICA:
- Detectar quando alguém entra em um grupo monitorado
- Enviar DM de boas-vindas personalizada
- Manter relacionamento/conversa com o usuário

Separado do group_router.py que cuida do Quiz.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

import app_state
from .evolution_client import EvolutionAPIClient
from .user_manager_kv import UserManagerKV
from .user_models import WelcomeConfig

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/welcome", tags=["WhatsApp Welcome DM"])

# Singleton do UserManager
_user_manager: UserManagerKV | None = None


async def get_user_manager() -> UserManagerKV:
    """Obtém ou cria singleton do UserManager."""
    global _user_manager
    if _user_manager is None:
        agentfs = await app_state.get_agentfs()
        _user_manager = UserManagerKV(agentfs)
        logger.info("UserManagerKV inicializado para Welcome DMs")
    return _user_manager


def get_evolution_client() -> EvolutionAPIClient:
    """Obtém cliente Evolution API."""
    return EvolutionAPIClient()


# =============================================================================
# WEBHOOK - Recebe eventos de participantes
# =============================================================================


@router.post("/webhook")
async def welcome_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Webhook dedicado para eventos de entrada em grupos.

    Recebe GROUP_PARTICIPANTS_UPDATE e processa DMs de boas-vindas.
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Erro ao parsear payload: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    event = payload.get("event", "")

    # Só processa eventos de participantes
    if event.upper() != "GROUP_PARTICIPANTS_UPDATE":
        return {"status": "ignored", "event": event}

    logger.info(f"[WELCOME] Evento recebido: {event}")

    # Processar em background
    user_manager = await get_user_manager()
    evolution = get_evolution_client()

    background_tasks.add_task(
        process_group_join,
        payload=payload,
        user_manager=user_manager,
        evolution=evolution,
    )

    return {"status": "processing", "event": event}


async def process_group_join(
    payload: dict,
    user_manager: UserManagerKV,
    evolution: EvolutionAPIClient,
) -> None:
    """
    Processa entrada de participante e envia DM de boas-vindas.

    Args:
        payload: Dados do webhook
        user_manager: Gerenciador de usuários
        evolution: Cliente Evolution API
    """
    try:
        data = payload.get("data", {})
        action = data.get("action", "").lower()

        group_id = data.get("groupJid", "") or data.get("id", "")
        participants = data.get("participants", [])
        group_name = data.get("subject", "") or data.get("groupName", "")

        if not group_id or not participants:
            logger.warning("[WELCOME] Dados incompletos no payload")
            return

        # Verificar se welcome está ativo para este grupo
        welcome_config = await user_manager.get_welcome_config(group_id)
        if not welcome_config.enabled:
            logger.info(f"[WELCOME] Welcome desabilitado para grupo {group_id}")
            return

        # Atualizar nome do grupo se disponível
        if group_name and not welcome_config.group_name:
            welcome_config.group_name = group_name
            await user_manager.save_welcome_config(welcome_config)

        # =====================================================
        # ENTRADA no grupo (add/join/invite)
        # =====================================================
        if action in ["add", "join", "invite"]:
            logger.info(
                f"[WELCOME] {len(participants)} novos membros no grupo {group_name or group_id}"
            )
            for participant in participants:
                await _send_welcome_dm(
                    participant=participant,
                    group_id=group_id,
                    group_name=group_name or welcome_config.group_name,
                    user_manager=user_manager,
                    evolution=evolution,
                    config=welcome_config,
                )

        # =====================================================
        # SAÍDA do grupo (remove/leave)
        # =====================================================
        elif action in ["remove", "leave"]:
            logger.info(
                f"[GOODBYE] {len(participants)} saíram do grupo {group_name or group_id}"
            )
            for participant in participants:
                await _send_goodbye_dm(
                    participant=participant,
                    group_id=group_id,
                    group_name=group_name or welcome_config.group_name,
                    user_manager=user_manager,
                    evolution=evolution,
                    config=welcome_config,
                )

        else:
            logger.debug(f"[WELCOME] Ação ignorada: {action}")

    except Exception as e:
        logger.error(f"[WELCOME] Erro ao processar evento: {e}", exc_info=True)


async def _send_welcome_dm(
    participant: str,
    group_id: str,
    group_name: str,
    user_manager: UserManagerKV,
    evolution: EvolutionAPIClient,
    config: WelcomeConfig,
) -> None:
    """
    Envia DM de boas-vindas para um participante.

    Args:
        participant: ID do participante (número@...)
        group_id: ID do grupo
        group_name: Nome do grupo
        user_manager: Gerenciador de usuários
        evolution: Cliente Evolution
        config: Configuração de welcome
    """
    try:
        # Extrair dados do participante
        # Evolution pode enviar: {"id": "xxx@lid", "phoneNumber": "5521...@s.whatsapp.net"}
        if isinstance(participant, dict):
            # Preferir phoneNumber para o número real
            phone_number = participant.get("phoneNumber", "")
            user_id = participant.get("id", participant.get("jid", ""))
            user_name = participant.get("name", participant.get("pushName", ""))

            # Se temos phoneNumber, usar ele para extrair telefone
            if phone_number:
                phone_clean = phone_number.split("@")[0]
            else:
                phone_clean = user_id.split("@")[0]
        else:
            user_id = str(participant)
            phone_clean = user_id.split("@")[0]
            user_name = ""

        if not phone_clean:
            logger.warning(f"[WELCOME] Não foi possível extrair telefone do participante")
            return

        # ID para armazenamento (usar phoneNumber se disponível)
        storage_id = f"{phone_clean}@s.whatsapp.net"

        logger.info(f"[WELCOME] Processando participante: phone={phone_clean}, id={user_id}")

        # Verificar se já foi welcomed para este grupo
        should_send = await user_manager.should_send_welcome(storage_id, group_id)
        if not should_send:
            logger.info(f"[WELCOME] Usuário {phone_clean} já foi welcomed para este grupo")
            return

        # Registrar usuário no grupo
        user, is_new = await user_manager.user_joined_group(
            user_id=storage_id,
            user_name=user_name or phone_clean,
            group_id=group_id,
            group_name=group_name,
        )

        # Delay para não parecer bot (configurável)
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)

        # Formatar mensagem de boas-vindas
        message = config.format_welcome(
            name=user.display_name,
            phone=phone_clean,
        )

        # Enviar DM usando o número de telefone real
        logger.info(f"[WELCOME] Enviando DM para {phone_clean}")
        success = await evolution.send_text(phone_clean, message)

        if success:
            # Marcar como welcomed e salvar histórico
            await user_manager.mark_user_welcomed(storage_id, group_id)
            await user_manager.add_conversation_message(
                user_id=storage_id,
                role="assistant",
                content=message,
            )
            logger.info(f"[WELCOME] DM enviada para {user.display_name} ({phone_clean})")
        else:
            logger.error(f"[WELCOME] Falha ao enviar DM para {phone_clean}")

    except Exception as e:
        logger.error(f"[WELCOME] Erro ao enviar welcome DM: {e}", exc_info=True)


async def _send_goodbye_dm(
    participant: str,
    group_id: str,
    group_name: str,
    user_manager: UserManagerKV,
    evolution: EvolutionAPIClient,
    config: WelcomeConfig,
) -> None:
    """
    Envia DM de despedida quando participante sai do grupo.

    Args:
        participant: ID do participante (número@...)
        group_id: ID do grupo
        group_name: Nome do grupo
        user_manager: Gerenciador de usuários
        evolution: Cliente Evolution
        config: Configuração de welcome
    """
    try:
        # Extrair dados do participante
        # Evolution pode enviar: {"id": "xxx@lid", "phoneNumber": "5521...@s.whatsapp.net"}
        if isinstance(participant, dict):
            phone_number = participant.get("phoneNumber", "")
            user_id = participant.get("id", participant.get("jid", ""))
            user_name = participant.get("name", participant.get("pushName", ""))

            if phone_number:
                phone_clean = phone_number.split("@")[0]
            else:
                phone_clean = user_id.split("@")[0]
        else:
            user_id = str(participant)
            phone_clean = user_id.split("@")[0]
            user_name = ""

        if not phone_clean:
            logger.warning(f"[GOODBYE] Não foi possível extrair telefone do participante")
            return

        storage_id = f"{phone_clean}@s.whatsapp.net"
        logger.info(f"[GOODBYE] Processando saída: phone={phone_clean}")

        # Buscar usuário (pode já existir no sistema)
        user = await user_manager.get_user(storage_id, user_name)

        # Delay para não parecer bot
        if config.delay_seconds > 0:
            await asyncio.sleep(config.delay_seconds)

        # Mensagem de despedida com link para voltar
        name = user.display_name or user_name or phone_clean

        # Link do grupo Quiz - Ton
        invite_link = "https://chat.whatsapp.com/BKrn8SOMBYG8v9LWtFOTJk"

        goodbye_message = (
            f"Oi {name}! 👋\n\n"
            f"Vi que você saiu do grupo.\n\n"
            f"Sentiremos sua falta! 😢\n\n"
            f"Se quiser voltar a qualquer momento, é só clicar no link abaixo:\n"
            f"👉 {invite_link}\n\n"
            f"Estaremos te esperando! 🎮"
        )

        # Enviar DM
        logger.info(f"[GOODBYE] Enviando DM para {phone_clean}")
        success = await evolution.send_text(phone_clean, goodbye_message)

        if success:
            # Salvar no histórico de conversa
            await user_manager.add_conversation_message(
                user_id=storage_id,
                role="assistant",
                content=goodbye_message,
            )
            logger.info(f"[GOODBYE] DM de despedida enviada para {name} ({phone_clean})")
        else:
            logger.error(f"[GOODBYE] Falha ao enviar DM de despedida para {phone_clean}")

    except Exception as e:
        logger.error(f"[GOODBYE] Erro ao enviar goodbye DM: {e}", exc_info=True)


# =============================================================================
# API ENDPOINTS - Configuração e gerenciamento
# =============================================================================


class WelcomeConfigUpdate(BaseModel):
    """Payload para atualizar configuração de welcome."""
    message: str | None = None
    group_name: str | None = None
    delay_seconds: int | None = None
    ai_enabled: bool | None = None


@router.get("/config/{group_id}")
async def get_welcome_config(
    group_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Retorna configuração de welcome para um grupo."""
    config = await user_manager.get_welcome_config(group_id)
    return {
        "group_id": config.group_id,
        "group_name": config.group_name,
        "enabled": config.enabled,
        "welcome_message": config.welcome_message,
        "delay_seconds": config.delay_seconds,
        "ai_enabled": config.ai_enabled,
    }


@router.post("/config/{group_id}")
async def update_welcome_config(
    group_id: str,
    update: WelcomeConfigUpdate,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Atualiza configuração de welcome para um grupo."""
    config = await user_manager.get_welcome_config(group_id)

    if update.message is not None:
        config.welcome_message = update.message
    if update.group_name is not None:
        config.group_name = update.group_name
    if update.delay_seconds is not None:
        config.delay_seconds = update.delay_seconds
    if update.ai_enabled is not None:
        config.ai_enabled = update.ai_enabled

    await user_manager.save_welcome_config(config)

    return {
        "status": "updated",
        "config": {
            "group_id": config.group_id,
            "welcome_message": config.welcome_message,
            "delay_seconds": config.delay_seconds,
            "ai_enabled": config.ai_enabled,
        }
    }


@router.post("/config/{group_id}/toggle")
async def toggle_welcome(
    group_id: str,
    enabled: bool = True,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Ativa/desativa welcome DM para um grupo."""
    config = await user_manager.toggle_welcome(group_id, enabled)
    return {
        "status": "toggled",
        "group_id": group_id,
        "enabled": config.enabled,
    }


@router.get("/users")
async def list_all_users(
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Lista estatísticas de todos os usuários."""
    stats = await user_manager.get_stats()
    return stats


@router.get("/users/{group_id}")
async def list_group_users(
    group_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Lista usuários de um grupo específico."""
    users = await user_manager.get_users_in_group(group_id)
    return {
        "group_id": group_id,
        "total": len(users),
        "users": [
            {
                "user_id": u.user_id,
                "display_name": u.display_name,
                "status": u.status.value,
                "welcomed": u.was_welcomed_for_group(group_id),
                "total_messages": u.total_messages_sent,
            }
            for u in users
        ],
    }


@router.get("/user/{user_id}")
async def get_user_profile(
    user_id: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Retorna perfil completo de um usuário."""
    user = await user_manager.get_user(user_id)
    return {
        "user_id": user.user_id,
        "display_name": user.display_name,
        "phone_number": user.phone_clean,
        "status": user.status.value,
        "groups": list(user.groups.keys()),
        "total_messages_sent": user.total_messages_sent,
        "total_messages_received": user.total_messages_received,
        "first_seen": user.first_seen_at.isoformat() if user.first_seen_at else None,
        "last_interaction": user.last_interaction_at.isoformat() if user.last_interaction_at else None,
        "conversation_history": len(user.conversation_history),
    }


class ManualDMRequest(BaseModel):
    """Payload para envio manual de DM."""
    phone: str
    message: str


@router.post("/send-dm")
async def send_manual_dm(
    request: ManualDMRequest,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Envia DM manual para um usuário."""
    evolution = get_evolution_client()

    # Normalizar telefone
    phone = request.phone.replace("+", "").replace("-", "").replace(" ", "")

    success = await evolution.send_text(phone, request.message)

    if success:
        # Salvar no histórico se existir usuário
        user_id = f"{phone}@s.whatsapp.net"
        try:
            await user_manager.add_conversation_message(
                user_id=user_id,
                role="assistant",
                content=request.message,
            )
        except Exception:
            pass

        return {"status": "sent", "phone": phone}

    raise HTTPException(status_code=500, detail="Falha ao enviar mensagem")


@router.post("/send-welcome/{group_id}/{phone}")
async def send_manual_welcome(
    group_id: str,
    phone: str,
    user_manager: UserManagerKV = Depends(get_user_manager),
) -> dict:
    """Envia welcome DM manual para um usuário específico."""
    evolution = get_evolution_client()

    # Normalizar telefone
    phone = phone.replace("+", "").replace("-", "").replace(" ", "")
    user_id = f"{phone}@s.whatsapp.net"

    # Carregar ou criar usuário
    user = await user_manager.get_user(user_id)

    # Carregar config do grupo
    config = await user_manager.get_welcome_config(group_id)

    # Formatar e enviar mensagem
    message = config.format_welcome(
        name=user.display_name or phone,
        phone=phone,
    )

    success = await evolution.send_text(phone, message)

    if success:
        await user_manager.mark_user_welcomed(user_id, group_id)
        await user_manager.add_conversation_message(
            user_id=user_id,
            role="assistant",
            content=message,
        )
        return {
            "status": "sent",
            "phone": phone,
            "message_preview": message[:100] + "..." if len(message) > 100 else message,
        }

    raise HTTPException(status_code=500, detail="Falha ao enviar mensagem")
