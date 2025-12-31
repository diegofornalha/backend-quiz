"""Gerenciador de Quiz em Grupo usando AgentFS KVStore (SQLite/Turso)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from .group_models import GroupQuizSession, GroupQuizState

logger = logging.getLogger(__name__)

# Prefixos de chave no KVStore
KEY_PREFIX_SESSION = "group:session:"
KEY_PREFIX_WHITELIST = "group:whitelist"


class GroupWhitelistKV:
    """Gerencia grupos autorizados usando KVStore."""

    def __init__(self, agentfs: "AgentFS"):
        """Inicializa whitelist com AgentFS.

        Args:
            agentfs: Instância do AgentFS
        """
        self._agentfs = agentfs
        self._cache: set[str] | None = None
        logger.info("GroupWhitelistKV inicializado com AgentFS")

    async def _load(self) -> set[str]:
        """Carrega whitelist do KVStore."""
        if self._cache is not None:
            return self._cache

        try:
            data = await self._agentfs.kv.get(KEY_PREFIX_WHITELIST, default={"groups": []})
            self._cache = set(data.get("groups", []))
            logger.debug(f"Whitelist carregada: {len(self._cache)} grupos")
        except Exception as e:
            logger.error(f"Erro ao carregar whitelist: {e}")
            self._cache = set()

        return self._cache

    async def _save(self) -> None:
        """Salva whitelist no KVStore."""
        if self._cache is None:
            return

        try:
            await self._agentfs.kv.set(KEY_PREFIX_WHITELIST, {"groups": list(self._cache)})
            logger.debug(f"Whitelist salva: {len(self._cache)} grupos")
        except Exception as e:
            logger.error(f"Erro ao salvar whitelist: {e}")

    async def is_allowed(self, group_id: str) -> bool:
        """Verifica se grupo está autorizado.

        Args:
            group_id: ID do grupo (ex: 123456789@g.us)

        Returns:
            True se grupo está na whitelist
        """
        whitelist = await self._load()
        return group_id in whitelist

    async def add_group(self, group_id: str) -> bool:
        """Adiciona grupo à whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi adicionado (não estava antes)
        """
        whitelist = await self._load()
        if group_id in whitelist:
            return False

        whitelist.add(group_id)
        self._cache = whitelist
        await self._save()
        logger.info(f"Grupo adicionado à whitelist: {group_id}")
        return True

    async def remove_group(self, group_id: str) -> bool:
        """Remove grupo da whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi removido (estava antes)
        """
        whitelist = await self._load()
        if group_id not in whitelist:
            return False

        whitelist.remove(group_id)
        self._cache = whitelist
        await self._save()
        logger.info(f"Grupo removido da whitelist: {group_id}")
        return True

    async def list_groups(self) -> list[str]:
        """Lista todos os grupos autorizados."""
        whitelist = await self._load()
        return list(whitelist)

    async def clear(self) -> None:
        """Remove todos os grupos da whitelist."""
        self._cache = set()
        await self._save()
        logger.warning("Whitelist limpa")


class GroupStateManagerKV:
    """Gerencia estado de quiz por grupo usando KVStore (SQLite/Turso)."""

    def __init__(self, agentfs: "AgentFS"):
        """Inicializa gerenciador de grupos com AgentFS.

        Args:
            agentfs: Instância do AgentFS
        """
        self._agentfs = agentfs
        self._cache: dict[str, GroupQuizSession] = {}
        self.whitelist = GroupWhitelistKV(agentfs)
        logger.info("GroupStateManagerKV inicializado com AgentFS")

    def _get_session_key(self, group_id: str) -> str:
        """Retorna chave do KVStore para sessão do grupo."""
        return f"{KEY_PREFIX_SESSION}{group_id}"

    async def get_session(self, group_id: str, group_name: str = "Quiz Group") -> GroupQuizSession:
        """Busca sessão do grupo (cache ou KVStore).

        Args:
            group_id: ID do grupo no WhatsApp
            group_name: Nome do grupo (para criar novo)

        Returns:
            Sessão do grupo (nova se não existir)
        """
        # Verificar cache primeiro
        if group_id in self._cache:
            return self._cache[group_id]

        # Tentar carregar do KVStore
        key = self._get_session_key(group_id)
        try:
            data = await self._agentfs.kv.get(key)
            if data:
                # Usar model_validate para reconstruir objetos aninhados corretamente
                session = GroupQuizSession.model_validate(data)
                self._cache[group_id] = session
                logger.debug(f"Sessão carregada do KVStore: {group_id}")
                return session
        except Exception as e:
            logger.error(f"Erro ao carregar sessão de {group_id}: {e}")

        # Criar nova sessão
        session = GroupQuizSession(group_id=group_id, group_name=group_name)
        self._cache[group_id] = session
        await self.save_session(session)
        logger.info(f"Nova sessão criada: {group_id}")
        return session

    async def save_session(self, session: GroupQuizSession) -> None:
        """Persiste sessão do grupo no KVStore.

        Args:
            session: Sessão a ser salva
        """
        try:
            # Atualizar cache
            self._cache[session.group_id] = session

            # Salvar no KVStore
            key = self._get_session_key(session.group_id)
            await self._agentfs.kv.set(key, session.model_dump(mode="json"))
            logger.debug(f"Sessão salva no KVStore: {session.group_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar sessão de {session.group_id}: {e}")

    async def reset_group(self, group_id: str, group_name: str = "Quiz Group") -> None:
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
        await self.save_session(session)
        logger.info(f"Sessão resetada: {group_id}")

    async def get_active_groups(self) -> list[GroupQuizSession]:
        """Retorna lista de grupos com quiz ativo.

        Returns:
            Lista de sessões de grupos em quiz
        """
        active = []
        try:
            # Listar todas as sessões com prefixo
            items = await self._agentfs.kv.list(KEY_PREFIX_SESSION)
            for item in items:
                try:
                    session = GroupQuizSession.model_validate(item["value"])
                    if session.state in [GroupQuizState.ACTIVE, GroupQuizState.WAITING_NEXT]:
                        active.append(session)
                except Exception as e:
                    logger.error(f"Erro ao parsear sessão {item.get('key')}: {e}")
        except Exception as e:
            logger.error(f"Erro ao listar sessões ativas: {e}")
        return active

    def clear_cache(self) -> None:
        """Limpa cache de sessões (forçar reload do KVStore)."""
        self._cache.clear()
        logger.info("Cache de sessões limpo")

    async def is_group_allowed(self, group_id: str) -> bool:
        """Verifica se grupo está autorizado.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo pode usar o bot
        """
        return await self.whitelist.is_allowed(group_id)

    async def add_allowed_group(self, group_id: str) -> bool:
        """Adiciona grupo à whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi adicionado
        """
        return await self.whitelist.add_group(group_id)

    async def remove_allowed_group(self, group_id: str) -> bool:
        """Remove grupo da whitelist.

        Args:
            group_id: ID do grupo

        Returns:
            True se grupo foi removido
        """
        return await self.whitelist.remove_group(group_id)

    async def list_allowed_groups(self) -> list[str]:
        """Lista grupos autorizados."""
        return await self.whitelist.list_groups()

    async def delete_session(self, group_id: str) -> bool:
        """Deleta sessão do grupo permanentemente.

        Args:
            group_id: ID do grupo

        Returns:
            True se sessão foi deletada
        """
        try:
            key = self._get_session_key(group_id)
            await self._agentfs.kv.delete(key)
            if group_id in self._cache:
                del self._cache[group_id]
            logger.info(f"Sessão deletada: {group_id}")
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar sessão {group_id}: {e}")
            return False
