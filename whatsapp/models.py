"""Modelos Pydantic para integração WhatsApp."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QuizFlowState(str, Enum):
    """Estado do fluxo do quiz no WhatsApp."""

    IDLE = "idle"  # Nenhum quiz ativo
    WAITING_START = "waiting_start"  # Aguardando confirmação para iniciar
    IN_QUIZ = "in_quiz"  # Quiz em andamento
    IN_CHAT = "in_chat"  # Modo chat de dúvidas
    FINISHED = "finished"  # Quiz finalizado


class UserQuizState(BaseModel):
    """Estado de um usuário no quiz."""

    user_id: str = Field(..., description="ID do usuário no WhatsApp (número de telefone)")
    flow_state: QuizFlowState = Field(default=QuizFlowState.IDLE)
    quiz_id: str | None = Field(default=None, description="ID do quiz ativo")
    current_question: int = Field(default=0, description="Índice da pergunta atual (1-10)")
    answers: list[int] = Field(default_factory=list, description="Respostas do usuário")
    score: int = Field(default=0, description="Pontuação atual")
    chat_session_id: str | None = Field(default=None, description="ID da sessão de chat de dúvidas")

    class Config:
        use_enum_values = True


class EvolutionWebhookMessage(BaseModel):
    """Webhook message da Evolution API."""

    event: str
    instance: str
    data: dict[str, Any]
    destination: str | None = None
    date_time: str | None = None
    sender: str | None = None
    server_url: str | None = None
    apikey: str | None = None


class WhatsAppTextMessage(BaseModel):
    """Mensagem de texto para enviar via WhatsApp."""

    number: str = Field(..., description="Número do destinatário (com DDI)")
    text: str = Field(..., description="Texto da mensagem")
    delay: int = Field(default=1000, description="Delay antes de enviar (ms)")


class WhatsAppButtonMessage(BaseModel):
    """Mensagem com botões para WhatsApp."""

    number: str
    title: str
    description: str
    footer: str | None = None
    buttons: list[dict[str, str]] = Field(..., description="Lista de botões [{'id': '1', 'text': 'Opção A'}]")
