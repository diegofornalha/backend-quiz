"""Agent Engine - Migrado para LiteLLM/Gemini"""
from typing import Optional

from llm import LiteLLMProvider

from .options import ClaudeRAGOptions


class AgentEngine:
    """Wrapper around LiteLLM for RAG queries"""

    def __init__(self, options: ClaudeRAGOptions):
        self.options = options
        self._llm = LiteLLMProvider(
            model=options.agent_model.value,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
        )

    async def query(
        self,
        user_message: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Query LLM with a message"""
        system = system_prompt or self.options.system_prompt or ""

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        response = await self._llm.completion(messages)
        return response.content

    def query_sync(
        self,
        user_message: str,
        system_prompt: Optional[str] = None
    ) -> str:
        """Synchronous version of query"""
        import asyncio

        # Usar asyncio.run para chamada síncrona
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Se já está em um loop async, criar task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.query(user_message, system_prompt)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.query(user_message, system_prompt)
                )
        except RuntimeError:
            # Sem loop existente
            return asyncio.run(self.query(user_message, system_prompt))
