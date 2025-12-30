"""Modelos para Quiz em Grupo no WhatsApp."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GroupQuizState(str, Enum):
    """Estado do quiz no grupo."""

    IDLE = "idle"  # Nenhum quiz ativo
    WAITING_START = "waiting_start"  # Aguardando iniciar
    ACTIVE = "active"  # Quiz em andamento
    WAITING_NEXT = "waiting_next"  # Aguardando próxima pergunta
    FINISHED = "finished"  # Quiz finalizado


class ParticipantAnswer(BaseModel):
    """Resposta de um participante."""

    user_id: str = Field(..., description="ID do participante (número WhatsApp)")
    user_name: str = Field(..., description="Nome do participante no WhatsApp")
    answer_index: int = Field(..., description="Índice da resposta (0-3)")
    is_correct: bool = Field(..., description="Se a resposta está correta")
    points_earned: int = Field(..., description="Pontos ganhos nesta resposta")
    answered_at: datetime = Field(default_factory=datetime.now)


class QuestionState(BaseModel):
    """Estado de uma pergunta no grupo."""

    question_id: int = Field(..., description="ID da pergunta (1-10)")
    started_at: datetime = Field(default_factory=datetime.now)
    answers: list[ParticipantAnswer] = Field(default_factory=list)

    def get_participants_answered(self) -> set[str]:
        """Retorna set de user_ids que já responderam."""
        return {ans.user_id for ans in self.answers}

    def get_correct_count(self) -> int:
        """Conta quantos acertaram."""
        return sum(1 for ans in self.answers if ans.is_correct)

    def get_participant_answer(self, user_id: str) -> ParticipantAnswer | None:
        """Busca resposta de um participante específico."""
        for ans in self.answers:
            if ans.user_id == user_id:
                return ans
        return None


class ParticipantScore(BaseModel):
    """Pontuação de um participante."""

    user_id: str
    user_name: str
    total_score: int = 0
    correct_answers: int = 0
    total_answers: int = 0

    @property
    def percentage(self) -> float:
        """Percentual de acerto."""
        if self.total_answers == 0:
            return 0.0
        return (self.correct_answers / self.total_answers) * 100


class GroupQuizSession(BaseModel):
    """Sessão de quiz de um grupo."""

    group_id: str = Field(..., description="ID do grupo no WhatsApp")
    group_name: str = Field(default="Quiz Group", description="Nome do grupo")
    state: GroupQuizState = Field(default=GroupQuizState.IDLE)
    quiz_id: str | None = Field(default=None, description="ID do quiz ativo")
    current_question: int = Field(default=0, description="Pergunta atual (0-10)")
    questions_history: list[QuestionState] = Field(
        default_factory=list,
        description="Histórico de perguntas e respostas",
    )
    participants: dict[str, ParticipantScore] = Field(
        default_factory=dict,
        description="Pontuação de cada participante (user_id -> score)",
    )
    started_by: str | None = Field(default=None, description="User ID de quem iniciou")
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)

    def get_or_create_participant(self, user_id: str, user_name: str) -> ParticipantScore:
        """Obtém ou cria participante."""
        if user_id not in self.participants:
            self.participants[user_id] = ParticipantScore(
                user_id=user_id,
                user_name=user_name,
            )
        return self.participants[user_id]

    def get_current_question_state(self) -> QuestionState | None:
        """Retorna estado da pergunta atual."""
        if not self.questions_history:
            return None
        return self.questions_history[-1]

    def add_answer(
        self,
        user_id: str,
        user_name: str,
        answer_index: int,
        is_correct: bool,
        points: int,
    ) -> None:
        """Adiciona resposta de participante."""
        # Atualizar estado da pergunta atual
        current = self.get_current_question_state()
        if current:
            answer = ParticipantAnswer(
                user_id=user_id,
                user_name=user_name,
                answer_index=answer_index,
                is_correct=is_correct,
                points_earned=points if is_correct else 0,
            )
            current.answers.append(answer)

        # Atualizar score do participante
        participant = self.get_or_create_participant(user_id, user_name)
        participant.total_answers += 1
        if is_correct:
            participant.correct_answers += 1
            participant.total_score += points

    def get_ranking(self) -> list[ParticipantScore]:
        """Retorna ranking ordenado por pontuação."""
        return sorted(
            self.participants.values(),
            key=lambda p: (p.total_score, p.correct_answers),
            reverse=True,
        )

    def get_top_3(self) -> list[ParticipantScore]:
        """Retorna top 3 participantes."""
        return self.get_ranking()[:3]

    def has_answered(self, user_id: str) -> bool:
        """Verifica se usuário já respondeu a pergunta atual."""
        current = self.get_current_question_state()
        if not current:
            return False
        return user_id in current.get_participants_answered()

    def start_new_question(self, question_id: int) -> None:
        """Inicia nova pergunta."""
        self.current_question = question_id
        self.questions_history.append(QuestionState(question_id=question_id))


class GroupCommand(str, Enum):
    """Comandos disponíveis no grupo."""

    # Comandos gerais
    INICIAR = "INICIAR"
    PARAR = "PARAR"
    STATUS = "STATUS"
    RANKING = "RANKING"
    PROXIMA = "PROXIMA"
    AJUDA = "AJUDA"
    REGULAMENTO = "REGULAMENTO"

    # Respostas
    A = "A"
    B = "B"
    C = "C"
    D = "D"
