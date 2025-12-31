"""Gerenciador de Usuários Individuais usando AgentFS KVStore (SQLite/Turso)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from .user_models import UserProfile, UserStatus, WelcomeConfig

logger = logging.getLogger(__name__)

# Prefixos de chave no KVStore
KEY_PREFIX_USER = "user:profile:"
KEY_PREFIX_WELCOME_CONFIG = "user:welcome_config:"
KEY_WELCOMED_USERS = "user:welcomed_set"


class UserManagerKV:
    """Gerencia usuários individuais usando KVStore (Turso/SQLite)."""

    def __init__(self, agentfs: "AgentFS"):
        """Inicializa gerenciador com AgentFS.

        Args:
            agentfs: Instância do AgentFS
        """
        self._agentfs = agentfs
        self._cache: dict[str, UserProfile] = {}
        self._welcome_configs: dict[str, WelcomeConfig] = {}
        logger.info("UserManagerKV inicializado com AgentFS")

    def _get_user_key(self, user_id: str) -> str:
        """Retorna chave do KVStore para perfil do usuário."""
        return f"{KEY_PREFIX_USER}{user_id}"

    def _get_welcome_config_key(self, group_id: str) -> str:
        """Retorna chave do KVStore para config de welcome do grupo."""
        return f"{KEY_PREFIX_WELCOME_CONFIG}{group_id}"

    # =========================================================================
    # USER PROFILE MANAGEMENT
    # =========================================================================

    async def get_user(self, user_id: str, display_name: str = "") -> UserProfile:
        """Busca ou cria perfil de usuário.

        Args:
            user_id: ID do usuário (número@s.whatsapp.net)
            display_name: Nome do usuário no WhatsApp

        Returns:
            Perfil do usuário
        """
        # Verificar cache primeiro
        if user_id in self._cache:
            user = self._cache[user_id]
            # Atualizar nome se fornecido e diferente
            if display_name and display_name != user.display_name:
                user.display_name = display_name
                await self.save_user(user)
            return user

        # Tentar carregar do KVStore
        key = self._get_user_key(user_id)
        try:
            data = await self._agentfs.kv.get(key)
            if data:
                user = UserProfile.model_validate(data)
                self._cache[user_id] = user
                logger.debug(f"Usuário carregado do KVStore: {user_id}")

                # Atualizar nome se fornecido e diferente
                if display_name and display_name != user.display_name:
                    user.display_name = display_name
                    await self.save_user(user)
                return user
        except Exception as e:
            logger.error(f"Erro ao carregar usuário {user_id}: {e}")

        # Criar novo perfil
        phone_clean = user_id.split("@")[0]
        user = UserProfile(
            user_id=user_id,
            phone_number=phone_clean,
            display_name=display_name or phone_clean,
        )
        self._cache[user_id] = user
        await self.save_user(user)
        logger.info(f"Novo usuário criado: {user_id} ({display_name})")
        return user

    async def save_user(self, user: UserProfile) -> None:
        """Persiste perfil do usuário no KVStore.

        Args:
            user: Perfil a ser salvo
        """
        try:
            self._cache[user.user_id] = user
            key = self._get_user_key(user.user_id)
            await self._agentfs.kv.set(key, user.model_dump(mode="json"))
            logger.debug(f"Usuário salvo no KVStore: {user.user_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar usuário {user.user_id}: {e}")

    async def user_joined_group(
        self,
        user_id: str,
        user_name: str,
        group_id: str,
        group_name: str = "",
    ) -> tuple[UserProfile, bool]:
        """Registra que usuário entrou em um grupo.

        Args:
            user_id: ID do usuário
            user_name: Nome do usuário
            group_id: ID do grupo
            group_name: Nome do grupo

        Returns:
            Tuple (perfil do usuário, se é novo no grupo)
        """
        user = await self.get_user(user_id, user_name)
        is_new = group_id not in user.groups

        user.add_to_group(group_id, group_name)
        await self.save_user(user)

        if is_new:
            logger.info(f"Usuário {user_name} entrou no grupo {group_name}")

        return user, is_new

    async def mark_user_welcomed(self, user_id: str, group_id: str) -> None:
        """Marca que usuário recebeu DM de boas-vindas para um grupo.

        Args:
            user_id: ID do usuário
            group_id: ID do grupo
        """
        user = await self.get_user(user_id)
        user.mark_welcomed(group_id)
        await self.save_user(user)
        logger.info(f"Usuário {user.display_name} welcomed para grupo {group_id}")

    async def should_send_welcome(self, user_id: str, group_id: str) -> bool:
        """Verifica se deve enviar DM de boas-vindas.

        Args:
            user_id: ID do usuário
            group_id: ID do grupo

        Returns:
            True se deve enviar DM
        """
        user = await self.get_user(user_id)
        return not user.was_welcomed_for_group(group_id)

    async def add_conversation_message(
        self,
        user_id: str,
        role: str,
        content: str,
    ) -> UserProfile:
        """Adiciona mensagem ao histórico de conversa.

        Args:
            user_id: ID do usuário
            role: "user" ou "assistant"
            content: Conteúdo da mensagem

        Returns:
            Perfil atualizado
        """
        user = await self.get_user(user_id)
        user.add_message(role, content)
        await self.save_user(user)
        return user

    async def get_user_context(self, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        """Retorna contexto de conversa para LLM.

        Args:
            user_id: ID do usuário
            limit: Máximo de mensagens

        Returns:
            Lista de mensagens para contexto
        """
        user = await self.get_user(user_id)
        return user.get_context_for_llm(limit)

    # =========================================================================
    # WELCOME CONFIG MANAGEMENT
    # =========================================================================

    async def get_welcome_config(self, group_id: str) -> WelcomeConfig:
        """Busca ou cria configuração de boas-vindas para grupo.

        Args:
            group_id: ID do grupo

        Returns:
            Configuração de boas-vindas
        """
        # Verificar cache
        if group_id in self._welcome_configs:
            return self._welcome_configs[group_id]

        # Tentar carregar do KVStore
        key = self._get_welcome_config_key(group_id)
        try:
            data = await self._agentfs.kv.get(key)
            if data:
                config = WelcomeConfig.model_validate(data)
                self._welcome_configs[group_id] = config
                return config
        except Exception as e:
            logger.error(f"Erro ao carregar welcome config {group_id}: {e}")

        # Criar config padrão
        config = WelcomeConfig(group_id=group_id)
        self._welcome_configs[group_id] = config
        await self.save_welcome_config(config)
        return config

    async def save_welcome_config(self, config: WelcomeConfig) -> None:
        """Salva configuração de boas-vindas.

        Args:
            config: Configuração a salvar
        """
        try:
            self._welcome_configs[config.group_id] = config
            key = self._get_welcome_config_key(config.group_id)
            await self._agentfs.kv.set(key, config.model_dump(mode="json"))
            logger.debug(f"Welcome config salva: {config.group_id}")
        except Exception as e:
            logger.error(f"Erro ao salvar welcome config {config.group_id}: {e}")

    async def update_welcome_message(
        self,
        group_id: str,
        message: str,
        group_name: str = "",
    ) -> WelcomeConfig:
        """Atualiza mensagem de boas-vindas de um grupo.

        Args:
            group_id: ID do grupo
            message: Nova mensagem
            group_name: Nome do grupo (opcional)

        Returns:
            Config atualizada
        """
        config = await self.get_welcome_config(group_id)
        config.welcome_message = message
        if group_name:
            config.group_name = group_name
        await self.save_welcome_config(config)
        return config

    async def toggle_welcome(self, group_id: str, enabled: bool) -> WelcomeConfig:
        """Ativa/desativa boas-vindas para um grupo.

        Args:
            group_id: ID do grupo
            enabled: Se deve ativar ou desativar

        Returns:
            Config atualizada
        """
        config = await self.get_welcome_config(group_id)
        config.enabled = enabled
        await self.save_welcome_config(config)
        return config

    # =========================================================================
    # QUERIES
    # =========================================================================

    async def get_users_in_group(self, group_id: str) -> list[UserProfile]:
        """Lista todos os usuários de um grupo.

        Args:
            group_id: ID do grupo

        Returns:
            Lista de perfis de usuários
        """
        users = []
        try:
            items = await self._agentfs.kv.list(KEY_PREFIX_USER)
            for item in items:
                try:
                    user = UserProfile.model_validate(item["value"])
                    if group_id in user.groups:
                        users.append(user)
                except Exception as e:
                    logger.error(f"Erro ao parsear usuário: {e}")
        except Exception as e:
            logger.error(f"Erro ao listar usuários do grupo {group_id}: {e}")
        return users

    async def get_active_users(self, days: int = 7) -> list[UserProfile]:
        """Lista usuários ativos nos últimos N dias.

        Args:
            days: Número de dias para considerar ativo

        Returns:
            Lista de usuários ativos
        """
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)
        users = []

        try:
            items = await self._agentfs.kv.list(KEY_PREFIX_USER)
            for item in items:
                try:
                    user = UserProfile.model_validate(item["value"])
                    if user.last_interaction_at and user.last_interaction_at > cutoff:
                        users.append(user)
                except Exception as e:
                    logger.error(f"Erro ao parsear usuário: {e}")
        except Exception as e:
            logger.error(f"Erro ao listar usuários ativos: {e}")

        return users

    async def get_unwelcomed_users(self, group_id: str) -> list[UserProfile]:
        """Lista usuários que ainda não receberam welcome de um grupo.

        Args:
            group_id: ID do grupo

        Returns:
            Lista de usuários não welcomed
        """
        users = await self.get_users_in_group(group_id)
        return [u for u in users if not u.was_welcomed_for_group(group_id)]

    async def get_stats(self) -> dict:
        """Retorna estatísticas gerais.

        Returns:
            Dict com estatísticas
        """
        total_users = 0
        welcomed_users = 0
        engaged_users = 0
        total_messages = 0

        try:
            items = await self._agentfs.kv.list(KEY_PREFIX_USER)
            for item in items:
                try:
                    user = UserProfile.model_validate(item["value"])
                    total_users += 1
                    total_messages += user.total_messages_sent + user.total_messages_received

                    if user.status != UserStatus.NEW:
                        welcomed_users += 1
                    if user.status in [UserStatus.ENGAGED, UserStatus.ACTIVE]:
                        engaged_users += 1
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Erro ao calcular stats: {e}")

        return {
            "total_users": total_users,
            "welcomed_users": welcomed_users,
            "engaged_users": engaged_users,
            "total_messages": total_messages,
        }

    def clear_cache(self) -> None:
        """Limpa caches locais."""
        self._cache.clear()
        self._welcome_configs.clear()
        logger.info("Cache de usuários limpo")

    async def delete_user(self, user_id: str) -> bool:
        """Remove usuário do sistema.

        Args:
            user_id: ID do usuário

        Returns:
            True se removido com sucesso
        """
        try:
            key = self._get_user_key(user_id)
            await self._agentfs.kv.delete(key)
            if user_id in self._cache:
                del self._cache[user_id]
            logger.info(f"Usuário removido: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Erro ao remover usuário {user_id}: {e}")
            return False
