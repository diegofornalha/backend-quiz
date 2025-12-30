"""LLM Client Factory - Abstração para criação de agentes de quiz usando LiteLLM."""

from dataclasses import dataclass

from llm import LiteLLMProvider

from ..prompts import QUIZ_SYSTEM_PROMPT


@dataclass
class QuizAgentResponse:
    """Resposta do agente de quiz."""

    answer: str


class QuizAgent:
    """Agente de quiz usando LiteLLM.

    Wrapper compatível com a interface anterior do AgentEngine.
    Permite usar LiteLLM mantendo a mesma API.

    Example:
        >>> agent = QuizAgent(system_prompt="Gere questões...")
        >>> response = await agent.query("Gere a primeira pergunta...")
        >>> print(response.answer)
    """

    # Mapeamento de qualidade para modelos
    MODEL_MAP = {
        "fast": "gemini/gemini-2.0-flash",      # Rápido e econômico
        "quality": "gemini/gemini-1.5-pro",     # Melhor qualidade
    }

    def __init__(
        self,
        agent_id: str,
        model_quality: str = "fast",
        system_prompt: str | None = None,
    ):
        """Inicializa agente de quiz.

        Args:
            agent_id: ID único do agente (usado para tracking/logging)
            model_quality: "fast" para Gemini Flash, "quality" para Gemini Pro
            system_prompt: Prompt de sistema customizado
        """
        self.agent_id = agent_id
        self.model = self.MODEL_MAP.get(model_quality, self.MODEL_MAP["fast"])
        self.system_prompt = system_prompt or QUIZ_SYSTEM_PROMPT
        self._llm = LiteLLMProvider(model=self.model)

    async def query(self, prompt: str) -> QuizAgentResponse:
        """Executa query no LLM.

        Args:
            prompt: Prompt do usuário

        Returns:
            QuizAgentResponse com a resposta
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        response = await self._llm.completion(messages)
        return QuizAgentResponse(answer=response.content)


class LLMClientFactory:
    """Factory para criar agentes de quiz com diferentes configurações.

    Centraliza a criação de agentes LLM para o quiz, permitindo:
    - Configuração consistente de system prompt
    - Seleção de modelo (fast para velocidade, quality para qualidade)
    - IDs únicos por quiz para tracking

    Example:
        >>> factory = LLMClientFactory()
        >>> agent = factory.create_first_question_agent("quiz-abc123")
        >>> response = await agent.query("Gere a primeira pergunta...")
    """

    @staticmethod
    def create_agent(
        agent_id: str,
        model_quality: str = "fast",
        system_prompt: str | None = None,
    ) -> QuizAgent:
        """Cria um QuizAgent genérico.

        Args:
            agent_id: ID único do agente (usado para tracking)
            model_quality: "fast" (Gemini Flash) ou "quality" (Gemini Pro)
            system_prompt: Prompt de sistema customizado

        Returns:
            QuizAgent configurado
        """
        return QuizAgent(
            agent_id=agent_id,
            model_quality=model_quality,
            system_prompt=system_prompt or QUIZ_SYSTEM_PROMPT,
        )

    @classmethod
    def create_first_question_agent(cls, quiz_id: str) -> QuizAgent:
        """Cria agente otimizado para primeira pergunta.

        Usa modelo rápido para resposta rápida na P1 (primeira impressão do usuário).

        Args:
            quiz_id: ID do quiz

        Returns:
            QuizAgent configurado para P1
        """
        return cls.create_agent(
            agent_id=f"quiz-{quiz_id}-p1",
            model_quality="fast",
            system_prompt=QUIZ_SYSTEM_PROMPT,
        )

    @classmethod
    def create_remaining_questions_agent(cls, quiz_id: str) -> QuizAgent:
        """Cria agente para perguntas P2-P10.

        Usa modelo rápido para manter velocidade na geração em background.

        Args:
            quiz_id: ID do quiz

        Returns:
            QuizAgent configurado para P2-P10
        """
        return cls.create_agent(
            agent_id=f"quiz-{quiz_id}-remaining",
            model_quality="fast",
            system_prompt=QUIZ_SYSTEM_PROMPT,
        )

    @classmethod
    def create_quality_agent(cls, quiz_id: str) -> QuizAgent:
        """Cria agente de alta qualidade para casos especiais.

        Use quando qualidade é mais importante que velocidade.

        Args:
            quiz_id: ID do quiz

        Returns:
            QuizAgent com Gemini Pro
        """
        return cls.create_agent(
            agent_id=f"quiz-{quiz_id}-quality",
            model_quality="quality",
            system_prompt=QUIZ_SYSTEM_PROMPT,
        )

    @classmethod
    def create_batch_agent(cls, quiz_id: str) -> QuizAgent:
        """Cria agente para geração em lote (todas as perguntas de uma vez).

        Usa modelo de qualidade para melhor resultado em geração complexa.

        Args:
            quiz_id: ID do quiz

        Returns:
            QuizAgent configurado para batch
        """
        return cls.create_agent(
            agent_id=f"quiz-{quiz_id}-batch",
            model_quality="quality",
            system_prompt=QUIZ_SYSTEM_PROMPT,
        )
