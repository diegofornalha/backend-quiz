"""Modelos para gerenciamento de usuários individuais no WhatsApp."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UserStatus(str, Enum):
    """Status do usuário no sistema."""

    NEW = "new"  # Acabou de entrar
    WELCOMED = "welcomed"  # Recebeu mensagem de boas-vindas
    ENGAGED = "engaged"  # Já interagiu
    ACTIVE = "active"  # Usuário ativo
    INACTIVE = "inactive"  # Sem interação há muito tempo


class ConversationMessage(BaseModel):
    """Mensagem na conversa com o usuário."""

    role: str = Field(..., description="user ou assistant")
    content: str = Field(..., description="Conteúdo da mensagem")
    timestamp: datetime = Field(default_factory=datetime.now)


class GroupMembership(BaseModel):
    """Informações de participação em grupo."""

    group_id: str = Field(..., description="ID do grupo (@g.us)")
    group_name: str = Field(default="", description="Nome do grupo")
    joined_at: datetime = Field(default_factory=datetime.now)
    welcomed: bool = Field(default=False, description="Se já recebeu DM de boas-vindas")
    welcomed_at: datetime | None = Field(default=None)


class UserProfile(BaseModel):
    """Perfil completo de um usuário."""

    user_id: str = Field(..., description="ID do usuário (número@s.whatsapp.net)")
    phone_number: str = Field(default="", description="Número limpo (sem @)")
    display_name: str = Field(default="", description="Nome no WhatsApp")
    status: UserStatus = Field(default=UserStatus.NEW)

    # Timestamps
    first_seen_at: datetime = Field(default_factory=datetime.now)
    last_interaction_at: datetime | None = Field(default=None)
    last_dm_sent_at: datetime | None = Field(default=None)

    # Grupos que participa
    groups: dict[str, GroupMembership] = Field(
        default_factory=dict,
        description="Grupos que o usuário participa (group_id -> membership)",
    )

    # Histórico de conversa DM
    conversation_history: list[ConversationMessage] = Field(
        default_factory=list,
        description="Histórico de mensagens no DM",
    )

    # Metadados customizados
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Dados extras (tags, preferências, etc.)",
    )

    # Contadores
    total_messages_sent: int = Field(default=0, description="Mensagens enviadas pelo usuário")
    total_messages_received: int = Field(default=0, description="Mensagens que enviamos para ele")

    def add_to_group(self, group_id: str, group_name: str = "") -> GroupMembership:
        """Adiciona usuário a um grupo.

        Args:
            group_id: ID do grupo
            group_name: Nome do grupo

        Returns:
            Membership criado ou existente
        """
        if group_id not in self.groups:
            self.groups[group_id] = GroupMembership(
                group_id=group_id,
                group_name=group_name,
            )
        return self.groups[group_id]

    def mark_welcomed(self, group_id: str) -> None:
        """Marca que usuário foi welcomed para um grupo específico.

        Args:
            group_id: ID do grupo
        """
        if group_id in self.groups:
            self.groups[group_id].welcomed = True
            self.groups[group_id].welcomed_at = datetime.now()
            self.last_dm_sent_at = datetime.now()
            self.total_messages_received += 1

        if self.status == UserStatus.NEW:
            self.status = UserStatus.WELCOMED

    def was_welcomed_for_group(self, group_id: str) -> bool:
        """Verifica se usuário já foi welcomed para um grupo.

        Args:
            group_id: ID do grupo

        Returns:
            True se já recebeu DM de boas-vindas para este grupo
        """
        if group_id not in self.groups:
            return False
        return self.groups[group_id].welcomed

    def add_message(self, role: str, content: str) -> None:
        """Adiciona mensagem ao histórico.

        Args:
            role: "user" ou "assistant"
            content: Conteúdo da mensagem
        """
        self.conversation_history.append(
            ConversationMessage(role=role, content=content)
        )

        # Atualizar contadores e timestamps
        if role == "user":
            self.total_messages_sent += 1
            self.last_interaction_at = datetime.now()
            if self.status in [UserStatus.NEW, UserStatus.WELCOMED]:
                self.status = UserStatus.ENGAGED
        else:
            self.total_messages_received += 1
            self.last_dm_sent_at = datetime.now()

    def get_recent_history(self, limit: int = 10) -> list[ConversationMessage]:
        """Retorna histórico recente de conversa.

        Args:
            limit: Número máximo de mensagens

        Returns:
            Lista de mensagens recentes
        """
        return self.conversation_history[-limit:]

    def get_context_for_llm(self, limit: int = 10) -> list[dict[str, str]]:
        """Retorna histórico formatado para LLM.

        Args:
            limit: Número máximo de mensagens

        Returns:
            Lista de dicts com role e content
        """
        recent = self.get_recent_history(limit)
        return [{"role": msg.role, "content": msg.content} for msg in recent]

    @property
    def phone_clean(self) -> str:
        """Retorna número limpo (sem @s.whatsapp.net)."""
        if self.phone_number:
            return self.phone_number
        return self.user_id.split("@")[0]

    @property
    def group_count(self) -> int:
        """Número de grupos que participa."""
        return len(self.groups)


class WelcomeConfig(BaseModel):
    """Configuração de mensagem de boas-vindas por grupo."""

    group_id: str = Field(..., description="ID do grupo")
    group_name: str = Field(default="", description="Nome do grupo")
    enabled: bool = Field(default=True, description="Se DM de boas-vindas está ativo")
    welcome_message: str = Field(
        default="Olá {name}! 👋\n\nVi que você entrou no grupo *{group}*.\n\nSou um assistente de IA e estou aqui para ajudar!\n\nMe conta, como posso te ajudar hoje?",
        description="Mensagem de boas-vindas (suporta {name}, {group}, {phone})",
    )
    delay_seconds: int = Field(
        default=5,
        description="Delay antes de enviar DM (evita parecer bot)",
    )
    follow_up_enabled: bool = Field(
        default=True,
        description="Se deve continuar conversando após boas-vindas",
    )
    ai_enabled: bool = Field(
        default=True,
        description="Se deve usar IA para responder mensagens subsequentes",
    )

    def format_welcome(self, name: str, phone: str = "") -> str:
        """Formata mensagem de boas-vindas.

        Args:
            name: Nome do usuário
            phone: Número do telefone

        Returns:
            Mensagem formatada
        """
        return (
            self.welcome_message
            .replace("{name}", name)
            .replace("{group}", self.group_name)
            .replace("{phone}", phone)
        )
