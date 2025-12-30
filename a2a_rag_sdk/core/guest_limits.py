"""Guest Limits Manager - Controle de limites para usuários não autenticados"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class GuestLimitAction(str, Enum):
    """Ações que podem ter limite"""
    CHAT = "chat"
    SEARCH = "search"
    QUIZ = "quiz"


@dataclass
class GuestLimit:
    """Configuração de limite"""
    action: GuestLimitAction
    max_per_hour: int = 10
    max_per_day: int = 50


class GuestLimitManager:
    """Gerenciador de limites para guests"""

    def __init__(self):
        self._usage: Dict[str, Dict[str, int]] = {}
        self._limits = {
            GuestLimitAction.CHAT: GuestLimit(GuestLimitAction.CHAT, 20, 100),
            GuestLimitAction.SEARCH: GuestLimit(GuestLimitAction.SEARCH, 30, 150),
            GuestLimitAction.QUIZ: GuestLimit(GuestLimitAction.QUIZ, 5, 20),
        }

    def check_limit(
        self,
        guest_id: str,
        action: GuestLimitAction,
    ) -> bool:
        """Verifica se guest pode executar ação.

        Args:
            guest_id: ID único do guest (IP, fingerprint, etc)
            action: Ação a ser executada

        Returns:
            True se permitido, False se excedeu limite
        """
        # Por enquanto, sempre permitir (implementar se necessário)
        return True

    def record_usage(
        self,
        guest_id: str,
        action: GuestLimitAction,
    ) -> None:
        """Registra uso de ação pelo guest."""
        if guest_id not in self._usage:
            self._usage[guest_id] = {}

        key = action.value
        self._usage[guest_id][key] = self._usage[guest_id].get(key, 0) + 1

    def get_remaining(
        self,
        guest_id: str,
        action: GuestLimitAction,
    ) -> int:
        """Retorna quantas ações restam para o guest."""
        limit = self._limits.get(action)
        if not limit:
            return 999

        current = self._usage.get(guest_id, {}).get(action.value, 0)
        return max(0, limit.max_per_hour - current)

    def reset_limits(self, guest_id: Optional[str] = None) -> None:
        """Reset limites de um guest ou todos."""
        if guest_id:
            self._usage.pop(guest_id, None)
        else:
            self._usage.clear()


# Singleton
_manager: Optional[GuestLimitManager] = None


def get_guest_limit_manager() -> GuestLimitManager:
    """Get or create guest limit manager"""
    global _manager
    if _manager is None:
        _manager = GuestLimitManager()
    return _manager
