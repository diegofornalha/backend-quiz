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
    hints_given: list[str] = Field(default_factory=list, description="Dicas já dadas para esta pergunta")

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
    current_question: int = Field(default=0, description="Pergunta atual (0-N)")
    total_questions: int = Field(default=0, description="Total de perguntas (dinâmico, 3 por participante)")
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

    # Sistema de turnos
    current_turn_user_id: str | None = Field(default=None, description="User ID de quem é a vez")
    turn_order: list[str] = Field(default_factory=list, description="Ordem dos turnos (lista de user_ids)")

    # Constantes para perguntas dinâmicas (fácil de ajustar!)
    QUESTIONS_PER_PARTICIPANT: int = 3  # <- MUDE AQUI para alterar perguntas por pessoa
    MAX_QUESTIONS: int = 30  # Limite máximo de segurança

    def get_or_create_participant(self, user_id: str, user_name: str) -> ParticipantScore:
        """Obtém ou cria participante, atualizando nome se necessário."""
        if user_id not in self.participants:
            self.participants[user_id] = ParticipantScore(
                user_id=user_id,
                user_name=user_name,
            )
        else:
            # Atualizar nome se era temporário ("Novo (XXXX)")
            participant = self.participants[user_id]
            if participant.user_name.startswith("Novo (") and not user_name.startswith("Novo ("):
                participant.user_name = user_name
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

    def add_bonus_questions(self, num_new_participants: int = 1) -> int:
        """Adiciona perguntas bônus quando novos participantes entram.

        Args:
            num_new_participants: Número de novos participantes

        Returns:
            Número de perguntas adicionadas
        """
        bonus = self.QUESTIONS_PER_PARTICIPANT * num_new_participants
        new_total = min(self.total_questions + bonus, self.MAX_QUESTIONS)
        added = new_total - self.total_questions
        self.total_questions = new_total
        return added

    def calculate_initial_questions(self) -> int:
        """Calcula total de perguntas baseado nos participantes.

        Fórmula simples: participantes × perguntas_por_pessoa
        Exemplo: 2 participantes × 3 = 6 perguntas

        Returns:
            Total de perguntas calculado
        """
        num_participants = max(1, len(self.participants))  # Mínimo 1 participante
        total = num_participants * self.QUESTIONS_PER_PARTICIPANT
        self.total_questions = min(total, self.MAX_QUESTIONS)
        return self.total_questions

    def initialize_turn_order(self) -> None:
        """Inicializa a ordem dos turnos com os participantes atuais."""
        self.turn_order = list(self.participants.keys())
        if self.turn_order:
            self.current_turn_user_id = self.turn_order[0]

    def is_user_turn(self, user_id: str) -> bool:
        """Verifica se é a vez do usuário.

        Args:
            user_id: ID do usuário

        Returns:
            True se for a vez do usuário
        """
        return self.current_turn_user_id == user_id

    def advance_turn(self) -> str | None:
        """Avança para o próximo turno.

        Returns:
            User ID do próximo jogador ou None se não houver
        """
        if not self.turn_order:
            return None

        # Encontrar índice atual
        try:
            current_idx = self.turn_order.index(self.current_turn_user_id)
        except (ValueError, TypeError):
            current_idx = -1

        # Próximo índice (circular)
        next_idx = (current_idx + 1) % len(self.turn_order)
        self.current_turn_user_id = self.turn_order[next_idx]
        return self.current_turn_user_id

    def get_current_turn_name(self) -> str | None:
        """Retorna o nome do jogador da vez.

        Returns:
            Nome do jogador ou None
        """
        if not self.current_turn_user_id:
            return None
        participant = self.participants.get(self.current_turn_user_id)
        return participant.user_name if participant else None

    def get_current_turn_display(self) -> str | None:
        """Retorna nome + últimos 4 dígitos do número do jogador da vez.

        Útil quando há participantes com nomes iguais.

        Returns:
            Nome formatado (ex: "Bianca (****6614)") ou None
        """
        if not self.current_turn_user_id:
            return None
        participant = self.participants.get(self.current_turn_user_id)
        if not participant:
            return None

        # Extrair últimos 4 dígitos do user_id
        user_id = self.current_turn_user_id
        # Remover sufixos como @lid, @s.whatsapp.net
        clean_id = user_id.split("@")[0]
        # Pegar apenas dígitos
        digits = "".join(c for c in clean_id if c.isdigit())
        last_4 = digits[-4:] if len(digits) >= 4 else digits

        return f"{participant.user_name} ({last_4})"

    def get_participant_display(self, user_id: str) -> str | None:
        """Retorna nome + últimos 4 dígitos do número de um participante.

        Args:
            user_id: ID do participante

        Returns:
            Nome formatado ou None
        """
        participant = self.participants.get(user_id)
        if not participant:
            return None

        # Extrair últimos 4 dígitos
        clean_id = user_id.split("@")[0]
        digits = "".join(c for c in clean_id if c.isdigit())
        last_4 = digits[-4:] if len(digits) >= 4 else digits

        return f"{participant.user_name} ({last_4})"

    def add_participant_to_turn_order(self, user_id: str) -> None:
        """Adiciona participante à ordem de turnos se não estiver.

        Args:
            user_id: ID do usuário a adicionar
        """
        if user_id not in self.turn_order:
            self.turn_order.append(user_id)
            # Se não houver turno atual, definir este como primeiro
            if not self.current_turn_user_id:
                self.current_turn_user_id = user_id


class GroupCommand(str, Enum):
    """Comandos disponíveis no grupo."""

    # Comandos gerais
    INICIAR = "INICIAR"
    COMECAR = "COMECAR"  # Inicia o quiz após lobby
    ENTRAR = "ENTRAR"  # Entrar no lobby
    SAIR = "SAIR"  # Sair do quiz/lobby
    PARAR = "PARAR"
    STATUS = "STATUS"
    RANKING = "RANKING"
    PROXIMA = "PROXIMA"
    AJUDA = "AJUDA"
    REGULAMENTO = "REGULAMENTO"
    DICA = "DICA"
    DUVIDA = "DUVIDA"  # Consultar regulamento com pergunta livre

    # Respostas
    A = "A"
    B = "B"
    C = "C"
    D = "D"
