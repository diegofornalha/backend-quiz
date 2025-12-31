"""Sistema de Logs Estruturado para Quiz usando AgentFS KVStore (Turso/SQLite)."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

logger = logging.getLogger(__name__)

# Prefixos de chave no KVStore
KEY_PREFIX_LOG = "log:"
KEY_PREFIX_LOG_INDEX = "log:index:"


class LogLevel(str, Enum):
    """Níveis de log."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(str, Enum):
    """Categorias de eventos."""
    WEBHOOK = "webhook"           # Recebimento de webhook
    MESSAGE = "message"           # Processamento de mensagem
    COMMAND = "command"           # Comando executado (INICIAR, DICA, etc)
    QUIZ = "quiz"                 # Eventos do quiz (start, answer, finish)
    PARTICIPANT = "participant"   # Eventos de participante (join, checkin)
    RAG = "rag"                   # Busca RAG
    LLM = "llm"                   # Chamadas LLM
    ERROR = "error"               # Erros
    SYSTEM = "system"             # Sistema (startup, shutdown)
    API = "api"                   # Chamadas de API admin


class QuizLogEntry(BaseModel):
    """Entrada de log estruturada."""

    id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    timestamp: datetime = Field(default_factory=datetime.now)
    level: LogLevel = LogLevel.INFO
    category: LogCategory

    # Contexto
    group_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    quiz_id: str | None = None
    question_num: int | None = None

    # Evento
    event: str  # Nome do evento (ex: "message_received", "quiz_started")
    message: str  # Descrição legível

    # Dados extras
    data: dict[str, Any] = Field(default_factory=dict)

    # Erro (se houver)
    error: str | None = None
    error_traceback: str | None = None


class QuizLogger:
    """Logger estruturado para quiz usando AgentFS KVStore."""

    def __init__(self, agentfs: "AgentFS"):
        """Inicializa logger com AgentFS.

        Args:
            agentfs: Instância do AgentFS
        """
        self._agentfs = agentfs
        self._buffer: list[QuizLogEntry] = []
        self._buffer_size = 10  # Flush a cada 10 logs
        logger.info("QuizLogger inicializado com AgentFS")

    def _get_log_key(self, log_id: str) -> str:
        """Retorna chave do KVStore para um log."""
        return f"{KEY_PREFIX_LOG}{log_id}"

    def _get_index_key(self, category: LogCategory, date: str) -> str:
        """Retorna chave do índice por categoria e data."""
        return f"{KEY_PREFIX_LOG_INDEX}{category.value}:{date}"

    async def log(
        self,
        category: LogCategory,
        event: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        group_id: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        quiz_id: str | None = None,
        question_num: int | None = None,
        data: dict | None = None,
        error: str | None = None,
        error_traceback: str | None = None,
    ) -> QuizLogEntry:
        """Registra um evento de log.

        Args:
            category: Categoria do evento
            event: Nome do evento
            message: Descrição legível
            level: Nível do log
            group_id: ID do grupo (opcional)
            user_id: ID do usuário (opcional)
            user_name: Nome do usuário (opcional)
            quiz_id: ID do quiz (opcional)
            question_num: Número da pergunta (opcional)
            data: Dados extras (opcional)
            error: Mensagem de erro (opcional)
            error_traceback: Traceback do erro (opcional)

        Returns:
            Entrada de log criada
        """
        entry = QuizLogEntry(
            level=level,
            category=category,
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
            question_num=question_num,
            event=event,
            message=message,
            data=data or {},
            error=error,
            error_traceback=error_traceback,
        )

        # Salvar no KVStore
        try:
            key = self._get_log_key(entry.id)
            await self._agentfs.kv.set(key, entry.model_dump(mode="json"))

            # Atualizar índice por categoria/data
            date_str = entry.timestamp.strftime("%Y-%m-%d")
            index_key = self._get_index_key(category, date_str)

            # Adicionar ao índice
            index = await self._agentfs.kv.get(index_key, default={"ids": []})
            index["ids"].append(entry.id)
            await self._agentfs.kv.set(index_key, index)

            # Log também no console para debug
            log_msg = f"[{category.value.upper()}] {event}: {message}"
            if group_id:
                log_msg = f"[{group_id[:8]}] {log_msg}"

            if level == LogLevel.ERROR or level == LogLevel.CRITICAL:
                logger.error(log_msg)
            elif level == LogLevel.WARNING:
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

        except Exception as e:
            logger.error(f"Erro ao salvar log: {e}")

        return entry

    # === Métodos de conveniência ===

    async def webhook_received(
        self,
        group_id: str,
        event_type: str,
        message_type: str | None = None,
        data: dict | None = None,
    ):
        """Log de webhook recebido."""
        await self.log(
            category=LogCategory.WEBHOOK,
            event="webhook_received",
            message=f"Webhook {event_type} recebido",
            group_id=group_id,
            data={"event_type": event_type, "message_type": message_type, **(data or {})},
        )

    async def message_received(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        text: str,
        quiz_id: str | None = None,
    ):
        """Log de mensagem recebida."""
        await self.log(
            category=LogCategory.MESSAGE,
            event="message_received",
            message=f"Mensagem de {user_name}: '{text[:50]}...' " if len(text) > 50 else f"Mensagem de {user_name}: '{text}'",
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
            data={"text": text},
        )

    async def command_executed(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        command: str,
        quiz_id: str | None = None,
        success: bool = True,
        error: str | None = None,
    ):
        """Log de comando executado."""
        await self.log(
            category=LogCategory.COMMAND,
            event="command_executed",
            message=f"Comando {command} por {user_name}" + (" (sucesso)" if success else f" (erro: {error})"),
            level=LogLevel.INFO if success else LogLevel.ERROR,
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
            data={"command": command, "success": success},
            error=error,
        )

    async def quiz_started(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        quiz_id: str,
    ):
        """Log de quiz iniciado."""
        await self.log(
            category=LogCategory.QUIZ,
            event="quiz_started",
            message=f"Quiz iniciado por {user_name}",
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
        )

    async def question_sent(
        self,
        group_id: str,
        quiz_id: str,
        question_num: int,
        topic: str | None = None,
    ):
        """Log de pergunta enviada."""
        await self.log(
            category=LogCategory.QUIZ,
            event="question_sent",
            message=f"Pergunta {question_num}/10 enviada" + (f" (tópico: {topic})" if topic else ""),
            group_id=group_id,
            quiz_id=quiz_id,
            question_num=question_num,
            data={"topic": topic},
        )

    async def answer_received(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
        quiz_id: str,
        question_num: int,
        answer: str,
        is_correct: bool,
        points: int,
    ):
        """Log de resposta recebida."""
        await self.log(
            category=LogCategory.QUIZ,
            event="answer_received",
            message=f"{user_name} respondeu {answer} - {'✓ Correto' if is_correct else '✗ Errado'} ({points} pts)",
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
            question_num=question_num,
            data={"answer": answer, "is_correct": is_correct, "points": points},
        )

    async def hint_requested(
        self,
        group_id: str,
        user_id: str | None,
        user_name: str | None,
        quiz_id: str,
        question_num: int,
        rag_results: int,
    ):
        """Log de dica solicitada."""
        await self.log(
            category=LogCategory.QUIZ,
            event="hint_requested",
            message=f"Dica solicitada para P{question_num} (RAG: {rag_results} resultados)",
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            quiz_id=quiz_id,
            question_num=question_num,
            data={"rag_results": rag_results},
        )

    async def quiz_finished(
        self,
        group_id: str,
        quiz_id: str,
        participants: int,
        winner: str | None = None,
        winner_score: int | None = None,
    ):
        """Log de quiz finalizado."""
        await self.log(
            category=LogCategory.QUIZ,
            event="quiz_finished",
            message=f"Quiz finalizado ({participants} participantes)" + (f" - Vencedor: {winner} ({winner_score} pts)" if winner else ""),
            group_id=group_id,
            quiz_id=quiz_id,
            data={"participants": participants, "winner": winner, "winner_score": winner_score},
        )

    async def participant_joined(
        self,
        group_id: str,
        user_id: str,
        user_name: str,
    ):
        """Log de participante cadastrado."""
        await self.log(
            category=LogCategory.PARTICIPANT,
            event="participant_joined",
            message=f"Novo participante: {user_name}",
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
        )

    async def rag_search(
        self,
        group_id: str,
        query: str,
        results_count: int,
        quiz_id: str | None = None,
    ):
        """Log de busca RAG."""
        await self.log(
            category=LogCategory.RAG,
            event="rag_search",
            message=f"Busca RAG: '{query[:50]}...' -> {results_count} resultados",
            group_id=group_id,
            quiz_id=quiz_id,
            data={"query": query, "results_count": results_count},
        )

    async def llm_call(
        self,
        group_id: str,
        purpose: str,
        model: str,
        tokens: int | None = None,
        quiz_id: str | None = None,
    ):
        """Log de chamada LLM."""
        await self.log(
            category=LogCategory.LLM,
            event="llm_call",
            message=f"LLM ({model}): {purpose}" + (f" [{tokens} tokens]" if tokens else ""),
            group_id=group_id,
            quiz_id=quiz_id,
            data={"purpose": purpose, "model": model, "tokens": tokens},
        )

    async def error(
        self,
        message: str,
        error: str,
        traceback: str | None = None,
        group_id: str | None = None,
        user_id: str | None = None,
        quiz_id: str | None = None,
    ):
        """Log de erro."""
        await self.log(
            category=LogCategory.ERROR,
            event="error",
            message=message,
            level=LogLevel.ERROR,
            group_id=group_id,
            user_id=user_id,
            quiz_id=quiz_id,
            error=error,
            error_traceback=traceback,
        )

    # === Métodos de consulta ===

    async def get_logs(
        self,
        category: LogCategory | None = None,
        date: str | None = None,
        group_id: str | None = None,
        limit: int = 100,
    ) -> list[QuizLogEntry]:
        """Busca logs com filtros.

        Args:
            category: Filtrar por categoria
            date: Filtrar por data (YYYY-MM-DD)
            group_id: Filtrar por grupo
            limit: Limite de resultados

        Returns:
            Lista de logs
        """
        logs = []

        try:
            if category and date:
                # Buscar por índice específico
                index_key = self._get_index_key(category, date)
                index = await self._agentfs.kv.get(index_key, default={"ids": []})

                for log_id in index["ids"][-limit:]:
                    key = self._get_log_key(log_id)
                    data = await self._agentfs.kv.get(key)
                    if data:
                        entry = QuizLogEntry(**data)
                        if group_id is None or entry.group_id == group_id:
                            logs.append(entry)
            else:
                # Buscar todos os logs (mais lento)
                items = await self._agentfs.kv.list(KEY_PREFIX_LOG)
                for item in items[-limit:]:
                    if item["key"].startswith(KEY_PREFIX_LOG) and not item["key"].startswith(KEY_PREFIX_LOG_INDEX):
                        entry = QuizLogEntry(**item["value"])

                        # Aplicar filtros
                        if category and entry.category != category:
                            continue
                        if group_id and entry.group_id != group_id:
                            continue

                        logs.append(entry)

        except Exception as e:
            logger.error(f"Erro ao buscar logs: {e}")

        # Ordenar por timestamp (mais recente primeiro)
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        return logs[:limit]

    async def get_recent_errors(self, limit: int = 20) -> list[QuizLogEntry]:
        """Busca erros recentes."""
        today = datetime.now().strftime("%Y-%m-%d")
        return await self.get_logs(category=LogCategory.ERROR, date=today, limit=limit)

    async def get_group_activity(self, group_id: str, limit: int = 50) -> list[QuizLogEntry]:
        """Busca atividade de um grupo."""
        return await self.get_logs(group_id=group_id, limit=limit)


# Singleton global
_quiz_logger: QuizLogger | None = None


async def get_quiz_logger() -> QuizLogger:
    """Obtém instância do QuizLogger."""
    global _quiz_logger

    if _quiz_logger is None:
        import app_state
        agentfs = await app_state.get_group_agentfs()
        _quiz_logger = QuizLogger(agentfs)

    return _quiz_logger
