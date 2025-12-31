"""Quiz Engine - Motor principal de geracao de quiz."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agentfs_sdk import AgentFS

from ..llm.factory import LLMClientFactory
from ..models.enums import QuizDifficulty
from ..models.schemas import QuizOption, QuizQuestion
from ..models.state import QuizState
from ..prompts import (
    DEFAULT_DIFFICULTY_DISTRIBUTION,
    FIRST_QUESTION_FALLBACK,
    FIRST_QUESTION_PROMPT,
    SINGLE_QUESTION_PROMPT,
)
from ..storage.quiz_store import QuizStore
from .dedup_engine import TopicDeduplicationEngine

logger = logging.getLogger(__name__)


class QuizEngine:
    """Motor principal de geração de quiz.

    Orquestra a geração de perguntas usando:
    - LLMClientFactory para criar agentes Claude
    - TopicDeduplicationEngine para evitar perguntas repetidas
    - Cache em memória (primário) + QuizStore/AgentFS (backup)

    Fluxo de geração:
    1. start_quiz() - Cria quiz, busca contexto RAG, gera P1
    2. _generate_remaining() - Background task para P2-P10
    3. get_question() - Recupera pergunta específica (com polling)

    Example:
        >>> engine = QuizEngine(agentfs, rag_instance)
        >>> quiz_id, first_question = await engine.start_quiz()
        >>> # P2-P10 geradas em background
        >>> question_2 = await engine.get_question(quiz_id, 2)
    """

    MAX_RETRIES = 1  # DESABILITADO: aceitar primeira pergunta (keywords muito amplas causam falsos positivos)
    TOTAL_QUESTIONS = 3  # Reduzido para testes mais rápidos (~10s de geração)

    # Cache em memória GLOBAL (compartilhado entre instâncias)
    _memory_cache: dict[str, QuizState] = {}

    def __init__(
        self,
        agentfs: AgentFS | None,
        rag: Any,  # ClaudeRAG instance
        llm_factory: LLMClientFactory | None = None,
        dedup_engine: TopicDeduplicationEngine | None = None,
    ):
        """Inicializa engine com dependências.

        Args:
            agentfs: Instância do AgentFS para persistência (pode ser None)
            rag: Instância do ClaudeRAG para busca de contexto
            llm_factory: Factory para criar agentes (opcional)
            dedup_engine: Engine de deduplicação (opcional)
        """
        # Store é opcional - só usa se AgentFS disponível
        self.store = QuizStore(agentfs) if agentfs else None
        self.rag = rag
        self.llm_factory = llm_factory or LLMClientFactory()
        self.dedup = dedup_engine or TopicDeduplicationEngine()

        # Tasks de geração em background (quiz_id -> task)
        self._generation_tasks: dict[str, asyncio.Task] = {}

    def _get_state(self, quiz_id: str) -> QuizState | None:
        """Busca estado do cache em memória."""
        return self._memory_cache.get(quiz_id)

    def _set_state(self, state: QuizState) -> None:
        """Salva estado no cache em memória."""
        self._memory_cache[state.quiz_id] = state

    async def start_quiz(self) -> tuple[str, QuizQuestion]:
        """Inicia um novo quiz.

        Cria estado, busca contexto RAG, gera primeira pergunta
        e inicia geração das restantes em background.

        Returns:
            Tuple de (quiz_id, first_question)
        """
        quiz_id = str(uuid.uuid4())[:8]
        logger.info(f"[Quiz {quiz_id}] Iniciando novo quiz...")

        # Criar estado inicial
        state = QuizState(quiz_id=quiz_id)

        # Buscar contexto RAG
        context = await self._get_rag_context()
        state.context = context

        # Gerar primeira pergunta
        first_question = await self._generate_first_question(quiz_id, context)
        state.add_question(1, first_question)
        state.add_topic(self.dedup.extract_topic(first_question.question))

        # Salvar no cache em memória (primário)
        self._set_state(state)

        # Persistir no AgentFS se disponível (backup)
        if self.store:
            try:
                await self.store.save_state(state)
            except Exception as e:
                logger.warning(f"[Quiz {quiz_id}] Erro ao salvar no AgentFS: {e}")

        # Iniciar geração em background
        task = asyncio.create_task(self._generate_remaining(quiz_id))
        self._generation_tasks[quiz_id] = task

        logger.info(f"[Quiz {quiz_id}] P1 gerada, background iniciado")
        return quiz_id, first_question

    async def _get_rag_context(self) -> str:
        """Busca contexto relevante do RAG.

        Returns:
            String com contexto concatenado dos documentos
        """
        search_query = (
            "Regras, validações, benefícios, prazos, níveis, "
            "recompensas do programa Renda Extra Ton"
        )

        search_results = await self.rag.search(search_query, top_k=10)

        if not search_results:
            logger.warning("Nenhum documento encontrado no RAG")
            return ""

        context_parts = []
        for i, result in enumerate(search_results[:8], 1):
            context_parts.append(f"[Trecho {i}]\n{result.content}\n")

        return "\n".join(context_parts)

    async def _generate_first_question(
        self, quiz_id: str, context: str
    ) -> QuizQuestion:
        """Gera a primeira pergunta do quiz.

        Args:
            quiz_id: ID do quiz
            context: Contexto RAG

        Returns:
            Primeira pergunta gerada
        """
        try:
            agent = self.llm_factory.create_first_question_agent(quiz_id)

            # Seed para variedade
            seed = random.randint(1000, 9999)

            prompt = FIRST_QUESTION_PROMPT.format(context=context, seed=seed)
            response = await agent.query(prompt)

            answer_text = response.answer if hasattr(response, "answer") else str(response)

            # Extrair JSON
            q_data = self._extract_json(answer_text)

            # Criar pergunta
            question = self._create_question_from_data(1, q_data, "easy")

            logger.info(f"[Quiz {quiz_id}] P1 gerada: {question.question[:50]}...")
            return question

        except Exception as e:
            logger.error(f"[Quiz {quiz_id}] Erro ao gerar P1: {e}, usando fallback")
            return FIRST_QUESTION_FALLBACK

    async def _generate_remaining(self, quiz_id: str) -> None:
        """Gera perguntas 2-10 em background.

        Args:
            quiz_id: ID do quiz
        """
        logger.info(f"[Quiz {quiz_id}] Iniciando geração em background...")

        try:
            # Buscar do cache em memória (primário)
            state = self._get_state(quiz_id)
            if state is None:
                logger.error(f"[Quiz {quiz_id}] Estado não encontrado no cache")
                return

            context = state.context
            if not context:
                context = await self._get_rag_context()
                state.context = context

            agent = self.llm_factory.create_remaining_questions_agent(quiz_id)

            # Gerar P2-P10
            for i, difficulty in enumerate(DEFAULT_DIFFICULTY_DISTRIBUTION, start=2):
                question = await self._generate_with_retry(
                    agent, i, difficulty, state
                )

                # Atualizar estado
                state.add_question(i, question)
                topic = self.dedup.extract_topic(question.question)
                state.add_topic(topic)

                # Salvar no cache em memória (primário)
                self._set_state(state)

                # Persistir no AgentFS se disponível (backup)
                if self.store:
                    try:
                        await self.store.save_state(state)
                    except Exception as e:
                        logger.warning(f"[Quiz {quiz_id}] Erro ao salvar P{i} no AgentFS: {e}")

                logger.info(f"[Quiz {quiz_id}] P{i} salva - Tópico: {topic}")

            # Marcar como completo
            state.mark_complete()
            self._set_state(state)

            if self.store:
                try:
                    await self.store.save_state(state)
                except Exception as e:
                    logger.warning(f"[Quiz {quiz_id}] Erro ao salvar estado final: {e}")

            logger.info(f"[Quiz {quiz_id}] Geração completa! {len(state.questions)} perguntas")

        except Exception as e:
            logger.error(f"[Quiz {quiz_id}] Erro fatal na geração: {e}")
            # Marcar erro no cache
            state = self._get_state(quiz_id)
            if state:
                state.set_error(str(e))
                self._set_state(state)

        finally:
            # Limpar task
            self._generation_tasks.pop(quiz_id, None)

    async def _generate_with_retry(
        self,
        agent: Any,
        index: int,
        difficulty: str,
        state: QuizState,
    ) -> QuizQuestion:
        """Gera pergunta com retry para duplicatas.

        Args:
            agent: AgentEngine configurado
            index: Índice da pergunta (2-10)
            difficulty: Dificuldade alvo
            state: Estado atual do quiz

        Returns:
            Pergunta gerada (ou fallback se max retries)
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                # Formatar tópicos anteriores
                topics_str = "\n".join([f"  🚫 {t}" for t in state.previous_topics])

                prompt = SINGLE_QUESTION_PROMPT.format(
                    context=state.context,
                    difficulty=difficulty,
                    question_number=index,
                    previous_topics=topics_str,
                )

                response = await agent.query(prompt)
                answer_text = response.answer if hasattr(response, "answer") else str(response)

                q_data = self._extract_json(answer_text)

                # Validar duplicata
                question_text = q_data["question"]
                is_valid, topic = self.dedup.validate_and_get_topic(
                    question_text, state.previous_topics
                )

                if not is_valid:
                    # RETRY DESABILITADO: aceitar pergunta mesmo com tópico similar
                    logger.info(
                        f"[Quiz {state.quiz_id}] P{index} tópico similar detectado "
                        f"('{topic}'), mas aceitando (retry desabilitado)"
                    )
                    # NÃO fazer continue - aceitar a pergunta

                # Criar pergunta
                question = self._create_question_from_data(index, q_data, difficulty)
                return question

            except Exception as e:
                logger.error(
                    f"[Quiz {state.quiz_id}] Erro P{index} "
                    f"(retry {attempt + 1}): {e}"
                )

        # Fallback após falha (não deveria chegar aqui com MAX_RETRIES=1)
        logger.error(f"[Quiz {state.quiz_id}] P{index}: ERRO CRÍTICO na geração, usando fallback")
        return self._create_fallback_question(index, difficulty)

    def _extract_json(self, text: str) -> dict:
        """Extrai JSON de resposta do Claude.

        Args:
            text: Texto da resposta

        Returns:
            Dict parseado do JSON

        Raises:
            ValueError: Se não conseguir extrair JSON válido
        """
        content = text

        # Remover blocos de código markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        # Tentar encontrar objeto JSON
        if not content.strip().startswith("{"):
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                content = json_match.group(0)

        return json.loads(content.strip())

    def _create_question_from_data(
        self, index: int, q_data: dict, target_difficulty: str
    ) -> QuizQuestion:
        """Cria QuizQuestion a partir de dados do Claude.

        Args:
            index: Índice da pergunta
            q_data: Dados parseados do JSON
            target_difficulty: Dificuldade alvo

        Returns:
            QuizQuestion validada
        """
        # Normalizar dificuldade
        raw_difficulty = q_data.get("difficulty", target_difficulty).lower()
        difficulty_map = {
            "easy": "easy",
            "medium": "medium",
            "hard": "hard",
            "difficult": "hard",
            "fácil": "easy",
            "médio": "medium",
            "difícil": "hard",
        }
        normalized_diff = difficulty_map.get(raw_difficulty, target_difficulty)

        diff_enum = QuizDifficulty(normalized_diff)
        points = 1 if diff_enum == QuizDifficulty.EASY else 2 if diff_enum == QuizDifficulty.MEDIUM else 3

        return QuizQuestion(
            id=index,
            question=q_data["question"],
            options=[QuizOption(**opt) for opt in q_data["options"]],
            correct_index=q_data["correct_index"],
            difficulty=diff_enum,
            points=points,
            explanation=q_data.get("explanation", ""),
            wrong_feedback={int(k): v for k, v in q_data.get("wrong_feedback", {}).items()},
            learning_tip=q_data.get("learning_tip", ""),
            source_reference=q_data.get("source_reference", ""),
        )

    def _create_fallback_question(self, index: int, difficulty: str) -> QuizQuestion:
        """Cria pergunta fallback quando geração falha.

        Args:
            index: Índice da pergunta
            difficulty: Dificuldade alvo

        Returns:
            QuizQuestion genérica
        """
        diff_enum = QuizDifficulty(difficulty)
        points = 1 if diff_enum == QuizDifficulty.EASY else 2 if diff_enum == QuizDifficulty.MEDIUM else 3

        return QuizQuestion(
            id=index,
            question=f"Pergunta {index} sobre o programa Renda Extra Ton",
            options=[
                QuizOption(label="A", text="Opção A"),
                QuizOption(label="B", text="Opção B"),
                QuizOption(label="C", text="Opção C"),
                QuizOption(label="D", text="Opção D"),
            ],
            correct_index=0,
            difficulty=diff_enum,
            points=points,
            explanation="Erro ao gerar pergunta. Consulte o regulamento.",
            wrong_feedback={},
            learning_tip="",
            source_reference="",
        )

    async def get_question(
        self, quiz_id: str, index: int, timeout: float = 30.0
    ) -> QuizQuestion | None:
        """Recupera pergunta específica com polling.

        Aguarda até a pergunta estar pronta ou timeout.

        Args:
            quiz_id: ID do quiz
            index: Índice da pergunta (1-10)
            timeout: Tempo máximo de espera em segundos

        Returns:
            QuizQuestion se pronta, None se timeout/erro
        """
        start = asyncio.get_event_loop().time()

        # Primeira verificação: tentar carregar do AgentFS se não estiver em memória
        state = self._get_state(quiz_id)
        if state is None and self.store:
            try:
                stored_state = await self.store.load_state(quiz_id)
                if stored_state:
                    logger.info(f"[Quiz {quiz_id}] Recuperado do AgentFS (tinha {len(stored_state.questions)} perguntas)")
                    self._set_state(stored_state)
                    state = stored_state
            except Exception as e:
                logger.warning(f"[Quiz {quiz_id}] Erro ao recuperar do AgentFS: {e}")

        while True:
            # Buscar do cache em memória (primário)
            state = self._get_state(quiz_id)
            if state and index in state.questions:
                return state.questions[index]

            # Verificar timeout
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= timeout:
                logger.warning(f"[Quiz {quiz_id}] Timeout aguardando P{index}")
                return None

            # Verificar se houve erro
            if state and state.error:
                logger.error(f"[Quiz {quiz_id}] Erro detectado: {state.error}")
                return None

            # Aguardar antes de próximo poll
            await asyncio.sleep(0.5)

    async def get_status(self, quiz_id: str) -> dict[str, Any]:
        """Retorna status completo do quiz.

        Args:
            quiz_id: ID do quiz

        Returns:
            Dict com status do quiz
        """
        state = self._get_state(quiz_id)

        # Tentar recuperar do AgentFS se não estiver em memória
        if state is None and self.store:
            try:
                stored_state = await self.store.load_state(quiz_id)
                if stored_state:
                    logger.info(f"[Quiz {quiz_id}] Recuperado do AgentFS para status")
                    self._set_state(stored_state)
                    state = stored_state
            except Exception as e:
                logger.warning(f"[Quiz {quiz_id}] Erro ao recuperar status do AgentFS: {e}")

        if state is None:
            return {
                "quiz_id": quiz_id,
                "found": False,
                "error": "Quiz não encontrado",
            }

        return {
            "quiz_id": quiz_id,
            "found": True,
            "generated_count": state.generated_count,
            "total_questions": self.TOTAL_QUESTIONS,
            "complete": state.complete,
            "error": state.error,
            "max_score": state.max_score,
            "questions_ready": list(state.questions.keys()),
            "previous_topics": state.previous_topics,
        }

    async def is_complete(self, quiz_id: str) -> bool:
        """Verifica se quiz está completo.

        Args:
            quiz_id: ID do quiz

        Returns:
            True se todas as perguntas foram geradas
        """
        state = self._get_state(quiz_id)
        return state.complete if state else False
