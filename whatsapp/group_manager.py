"""Gerenciador de Quiz em Grupo com Whitelist."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .group_models import GroupQuizSession, GroupQuizState

logger = logging.getLogger(__name__)


class GroupWhitelist:
    """Gerencia grupos autorizados a usar o bot."""

    def __init__(self, whitelist_file: str = ".whatsapp_groups/whitelist.json"):
        """Inicializa whitelist.

        Args:
            whitelist_file: Caminho do arquivo de whitelist
        """
        self.whitelist_file = Path(whitelist_file)
        self.whitelist_file.parent.mkdir(exist_ok=True)
        self._whitelist: set[str] = set()
        self._load()
        logger.info(f"Whitelist carregada: {len(self._whitelist)} grupos")

    def _load(self) -> None:
        """Carrega whitelist do disco."""
        if self.whitelist_file.exists():
            try:
                data = json.loads(self.whitelist_file.read_text())
                self._whitelist = set(data.get("groups", []))
                logger.debug(f"Whitelist carregada: {self._whitelist}")
            except Exception as e:
                logger.error(f"Erro ao carregar whitelist: {e}")
                self._whitelist = set()

    def _save(self) -> None:
        """Salva whitelist no disco."""
        try:
            data = {"groups": list(self._whitelist)}
            self.whitelist_file.write_text(json.dumps(data, indent=2))
            logger.debug(f"Whitelist salva: {self._whitelist}")
        except Exception as e:
            logger.error(f"Erro ao salvar whitelist: {e}")

    def is_allowed(self, group_id: str) -> bool:
        """Verifica se grupo está autorizado.

        Args:
            group_id: ID do grupo (ex: 123456789@g.us)

        Returns:
            True se grupo está na whitelist
        """
        return group_id in self._whitelist

    def add_group(self, group_id: str) -> bool:
        """Adiciona grupo à whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi adicionado (não estava antes)
        """
        if group_id in self._whitelist:
            return False
        self._whitelist.add(group_id)
        self._save()
        logger.info(f"Grupo adicionado à whitelist: {group_id}")
        return True

    def remove_group(self, group_id: str) -> bool:
        """Remove grupo da whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi removido (estava antes)
        """
        if group_id not in self._whitelist:
            return False
        self._whitelist.remove(group_id)
        self._save()
        logger.info(f"Grupo removido da whitelist: {group_id}")
        return True

    def list_groups(self) -> list[str]:
        """Lista todos os grupos autorizados."""
        return list(self._whitelist)

    def clear(self) -> None:
        """Remove todos os grupos da whitelist."""
        self._whitelist.clear()
        self._save()
        logger.warning("Whitelist limpa")


class GroupStateManager:
    """Gerencia estado de quiz por grupo."""

    def __init__(self, storage_path: str = ".whatsapp_groups"):
        """Inicializa gerenciador de grupos.

        Args:
            storage_path: Diretório para persistir estados
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        self._cache: dict[str, GroupQuizSession] = {}
        self.whitelist = GroupWhitelist()
        logger.info(f"GroupStateManager inicializado: {self.storage_path}")

    def _get_group_file(self, group_id: str) -> Path:
        """Retorna caminho do arquivo de estado do grupo."""
        # Sanitizar group_id para nome de arquivo válido
        safe_id = group_id.replace("@", "_at_").replace("-", "_")
        return self.storage_path / f"{safe_id}.json"

    def get_session(self, group_id: str, group_name: str = "Quiz Group") -> GroupQuizSession:
        """Busca sessão do grupo (cache ou disco).

        Args:
            group_id: ID do grupo no WhatsApp
            group_name: Nome do grupo (para criar novo)

        Returns:
            Sessão do grupo (nova se não existir)
        """
        # Verificar cache primeiro
        if group_id in self._cache:
            return self._cache[group_id]

        # Tentar carregar do disco
        group_file = self._get_group_file(group_id)
        if group_file.exists():
            try:
                data = json.loads(group_file.read_text())
                session = GroupQuizSession(**data)
                self._cache[group_id] = session
                logger.debug(f"Sessão carregada do disco: {group_id}")
                return session
            except Exception as e:
                logger.error(f"Erro ao carregar sessão de {group_id}: {e}")

        # Criar nova sessão
        session = GroupQuizSession(group_id=group_id, group_name=group_name)
        self._cache[group_id] = session
        self.save_session(session)
        logger.info(f"Nova sessão criada: {group_id}")
        return session

    def save_session(self, session: GroupQuizSession) -> None:
        """Persiste sessão do grupo.

        Args:
            session: Sessão a ser salva
        """
        try:
            # Atualizar cache
            self._cache[session.group_id] = session

            # Salvar em disco
            group_file = self._get_group_file(session.group_id)
            group_file.write_text(session.model_dump_json(indent=2))
            logger.debug(f"Sessão salva: {session.group_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar sessão de {session.group_id}: {e}")

    def reset_group(self, group_id: str, group_name: str = "Quiz Group") -> None:
        """Reseta sessão do grupo (novo quiz).

        Args:
            group_id: ID do grupo
            group_name: Nome do grupo
        """
        session = GroupQuizSession(
            group_id=group_id,
            group_name=group_name,
            state=GroupQuizState.IDLE,
        )
        self.save_session(session)
        logger.info(f"Sessão resetada: {group_id}")

    def get_active_groups(self) -> list[GroupQuizSession]:
        """Retorna lista de grupos com quiz ativo.

        Returns:
            Lista de sessões de grupos em quiz
        """
        active = []
        for group_file in self.storage_path.glob("*.json"):
            # Pular whitelist
            if group_file.name == "whitelist.json":
                continue

            try:
                data = json.loads(group_file.read_text())
                session = GroupQuizSession(**data)
                if session.state in [GroupQuizState.ACTIVE, GroupQuizState.WAITING_NEXT]:
                    active.append(session)
            except Exception as e:
                logger.error(f"Erro ao ler {group_file}: {e}")
        return active

    def clear_cache(self) -> None:
        """Limpa cache de sessões (forçar reload do disco)."""
        self._cache.clear()
        logger.info("Cache de sessões limpo")

    def is_group_allowed(self, group_id: str) -> bool:
        """Verifica se grupo está autorizado.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo pode usar o bot
        """
        return self.whitelist.is_allowed(group_id)

    def add_allowed_group(self, group_id: str) -> bool:
        """Adiciona grupo à whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi adicionado
        """
        return self.whitelist.add_group(group_id)

    def remove_allowed_group(self, group_id: str) -> bool:
        """Remove grupo da whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi removido
        """
        return self.whitelist.remove_group(group_id)

    def list_allowed_groups(self) -> list[str]:
        """Lista grupos autorizados."""
        return self.whitelist.list_groups()
