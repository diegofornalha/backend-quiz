"""Gerenciador de estado de usuários do WhatsApp."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .models import QuizFlowState, UserQuizState

logger = logging.getLogger(__name__)


class UserStateManager:
    """Gerencia estado de quiz por usuário WhatsApp.

    Persiste estado em arquivo JSON para sobreviver a reinicializações.
    """

    def __init__(self, storage_path: str = ".whatsapp_states"):
        """Inicializa gerenciador de estado.

        Args:
            storage_path: Diretório para persistir estados
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self._cache: dict[str, UserQuizState] = {}
        logger.info(f"UserStateManager inicializado: {self.storage_path}")

    def _get_user_file(self, user_id: str) -> Path:
        """Retorna caminho do arquivo de estado do usuário."""
        # Sanitizar user_id para nome de arquivo válido
        safe_id = user_id.replace("+", "").replace("@", "_at_")
        return self.storage_path / f"{safe_id}.json"

    def get_state(self, user_id: str) -> UserQuizState:
        """Busca estado do usuário (cache ou disco).

        Args:
            user_id: ID do usuário no WhatsApp

        Returns:
            Estado do usuário (novo se não existir)
        """
        # Verificar cache primeiro
        if user_id in self._cache:
            return self._cache[user_id]

        # Tentar carregar do disco
        user_file = self._get_user_file(user_id)
        if user_file.exists():
            try:
                data = json.loads(user_file.read_text())
                state = UserQuizState(**data)
                self._cache[user_id] = state
                logger.debug(f"Estado carregado do disco: {user_id}")
                return state
            except Exception as e:
                logger.error(f"Erro ao carregar estado de {user_id}: {e}")

        # Criar novo estado
        state = UserQuizState(user_id=user_id)
        self._cache[user_id] = state
        self.save_state(state)
        logger.info(f"Novo estado criado: {user_id}")
        return state

    def save_state(self, state: UserQuizState) -> None:
        """Persiste estado do usuário.

        Args:
            state: Estado a ser salvo
        """
        try:
            # Atualizar cache
            self._cache[state.user_id] = state

            # Salvar em disco
            user_file = self._get_user_file(state.user_id)
            user_file.write_text(state.model_dump_json(indent=2))
            logger.debug(f"Estado salvo: {state.user_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar estado de {state.user_id}: {e}")

    def reset_user(self, user_id: str) -> None:
        """Reseta estado do usuário (novo quiz).

        Args:
            user_id: ID do usuário
        """
        state = UserQuizState(user_id=user_id, flow_state=QuizFlowState.IDLE)
        self.save_state(state)
        logger.info(f"Estado resetado: {user_id}")

    def get_active_users(self) -> list[UserQuizState]:
        """Retorna lista de usuários com quiz ativo.

        Returns:
            Lista de estados de usuários em quiz
        """
        active = []
        for user_file in self.storage_path.glob("*.json"):
            try:
                data = json.loads(user_file.read_text())
                state = UserQuizState(**data)
                if state.flow_state in [QuizFlowState.IN_QUIZ, QuizFlowState.IN_CHAT]:
                    active.append(state)
            except Exception as e:
                logger.error(f"Erro ao ler {user_file}: {e}")
        return active

    def clear_cache(self) -> None:
        """Limpa cache de estados (forçar reload do disco)."""
        self._cache.clear()
        logger.info("Cache de estados limpo")
