"""Cliente para Evolution API v2."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EvolutionAPIClient:
    """Cliente HTTP para Evolution API.

    Documentação: https://doc.evolution-api.com/
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        instance_name: str,
        timeout: float = 30.0,
    ):
        """Inicializa cliente Evolution API.

        Args:
            base_url: URL base da Evolution API (ex: http://localhost:8080)
            api_key: API key global da Evolution
            instance_name: Nome da instância WhatsApp
            timeout: Timeout para requisições HTTP
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instance_name = instance_name
        self.timeout = timeout

        self.headers = {
            "Content-Type": "application/json",
            "apikey": api_key,
        }

        logger.info(
            f"EvolutionAPIClient inicializado: {base_url} (instance: {instance_name})"
        )

    async def send_text(
        self,
        number: str,
        text: str,
        delay: int = 1000,
    ) -> dict[str, Any]:
        """Envia mensagem de texto.

        Args:
            number: Número do destinatário (com DDI, ex: 5511999999999)
            text: Texto da mensagem
            delay: Delay antes de enviar (ms)

        Returns:
            Resposta da API
        """
        url = f"{self.base_url}/message/sendText/{self.instance_name}"
        payload = {
            "number": number,
            "text": text,
            "delay": delay,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Mensagem enviada para {number}: {len(text)} chars")
                return result
        except httpx.HTTPError as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            raise

    async def send_buttons(
        self,
        number: str,
        title: str,
        description: str,
        buttons: list[dict[str, str]],
        footer: str | None = None,
    ) -> dict[str, Any]:
        """Envia mensagem com botões interativos.

        Args:
            number: Número do destinatário
            title: Título da mensagem
            description: Descrição/corpo da mensagem
            buttons: Lista de botões [{"id": "1", "text": "Opção A"}]
            footer: Texto do rodapé (opcional)

        Returns:
            Resposta da API
        """
        url = f"{self.base_url}/message/sendButtons/{self.instance_name}"
        payload = {
            "number": number,
            "title": title,
            "description": description,
            "buttons": buttons,
        }
        if footer:
            payload["footer"] = footer

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Botões enviados para {number}: {len(buttons)} opções")
                return result
        except httpx.HTTPError as e:
            logger.error(f"Erro ao enviar botões: {e}")
            raise

    async def send_list(
        self,
        number: str,
        title: str,
        description: str,
        sections: list[dict[str, Any]],
        button_text: str = "Ver opções",
        footer: str | None = None,
    ) -> dict[str, Any]:
        """Envia mensagem com lista interativa.

        Args:
            number: Número do destinatário
            title: Título da lista
            description: Descrição da lista
            sections: Seções da lista (formato Evolution API)
            button_text: Texto do botão para abrir lista
            footer: Texto do rodapé (opcional)

        Returns:
            Resposta da API
        """
        url = f"{self.base_url}/message/sendList/{self.instance_name}"
        payload = {
            "number": number,
            "title": title,
            "description": description,
            "sections": sections,
            "buttonText": button_text,
        }
        if footer:
            payload["footer"] = footer

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Lista enviada para {number}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"Erro ao enviar lista: {e}")
            raise

    async def get_instance_status(self) -> dict[str, Any]:
        """Verifica status da instância WhatsApp.

        Returns:
            Status da instância
        """
        url = f"{self.base_url}/instance/connectionState/{self.instance_name}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erro ao verificar status: {e}")
            raise

    async def send_presence(
        self,
        number: str,
        presence: str = "composing",
        delay: int = 2000,
    ) -> dict[str, Any]:
        """Envia presença (typing, recording, etc).

        Args:
            number: Número/grupo destinatário
            presence: Tipo de presença ("composing", "recording", "available", "paused")
            delay: Duração da presença em ms

        Returns:
            Resposta da API
        """
        url = f"{self.base_url}/chat/sendPresence/{self.instance_name}"
        payload = {
            "number": number,
            "delay": delay,
            "presence": presence,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.debug(f"Presença '{presence}' enviada para {number}")
                return result
        except httpx.HTTPError as e:
            logger.warning(f"Erro ao enviar presença (não crítico): {e}")
            return {}

    async def send_typing(self, number: str, duration: int = 2000) -> dict[str, Any]:
        """Simula digitação (atalho para send_presence).

        Args:
            number: Número/grupo destinatário
            duration: Duração em ms

        Returns:
            Resposta da API
        """
        return await self.send_presence(number, "composing", duration)

    async def set_webhook(self, webhook_url: str, events: list[str] | None = None) -> dict[str, Any]:
        """Configura webhook para receber mensagens.

        Args:
            webhook_url: URL do webhook (ex: https://seu-dominio.com/whatsapp/webhook)
            events: Lista de eventos para receber (default: ["MESSAGES_UPSERT"])

        Returns:
            Resposta da API
        """
        if events is None:
            events = ["MESSAGES_UPSERT"]

        url = f"{self.base_url}/webhook/set/{self.instance_name}"
        payload = {
            "url": webhook_url,
            "enabled": True,
            "events": events,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Webhook configurado: {webhook_url}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"Erro ao configurar webhook: {e}")
            raise
