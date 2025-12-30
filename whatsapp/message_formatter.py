"""Formatadores de mensagem para WhatsApp."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quiz.models.schemas import QuizQuestion

EMOJI_MAP = {
    "iniciante": "🌱",
    "especialista_i": "📚",
    "especialista_ii": "⭐",
    "especialista_iii": "🌟",
    "embaixador": "🏆",
}


class WhatsAppFormatter:
    """Formata mensagens do quiz para WhatsApp."""

    @staticmethod
    def format_welcome() -> str:
        """Mensagem de boas-vindas."""
        return """🎯 *Bem-vindo ao Quiz Renda Extra Ton!*

Teste seus conhecimentos sobre o programa e descubra seu nível na trilha de carreira.

📝 *10 perguntas* de múltipla escolha
💬 Tire dúvidas durante o quiz
🏆 Ranking baseado no seu desempenho

Para começar, digite: *INICIAR*

Você também pode:
• *AJUDA* - Ver comandos disponíveis
• *REGULAMENTO* - Consultar regulamento oficial"""

    @staticmethod
    def format_help() -> str:
        """Mensagem de ajuda."""
        return """📖 *Comandos Disponíveis:*

*INICIAR* - Começar um novo quiz
*PARAR* - Cancelar quiz atual
*DUVIDA* + sua pergunta - Tirar dúvida sobre a questão atual
*REGULAMENTO* - Link para o regulamento oficial
*STATUS* - Ver progresso atual
*AJUDA* - Mostrar esta mensagem

Durante o quiz, responda com:
*A*, *B*, *C* ou *D*"""

    @staticmethod
    def format_question(question: QuizQuestion, question_num: int) -> str:
        """Formata pergunta para WhatsApp.

        Args:
            question: Objeto QuizQuestion
            question_num: Número da pergunta (1-10)

        Returns:
            Mensagem formatada
        """
        lines = [
            f"📝 *Pergunta {question_num}/10*",
            "",
            f"❓ {question.question}",
            "",
        ]

        # Adicionar opções
        for opt in question.options:
            lines.append(f"*{opt.label})* {opt.text}")

        lines.extend([
            "",
            "💬 *Responda com:* A, B, C ou D",
            "ℹ️ *Tem dúvida?* Digite: DUVIDA + sua pergunta",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_feedback(is_correct: bool, explanation: str, correct_answer: str | None = None) -> str:
        """Formata feedback da resposta.

        Args:
            is_correct: Se a resposta está correta
            explanation: Explicação da resposta
            correct_answer: Resposta correta (se usuário errou)

        Returns:
            Mensagem formatada
        """
        if is_correct:
            lines = [
                "✅ *Resposta Correta!*",
                "",
                f"💡 {explanation}",
                "",
                "Digite *PROXIMA* para continuar",
            ]
        else:
            lines = [
                "❌ *Resposta Incorreta*",
                "",
            ]
            if correct_answer:
                lines.append(f"✔️ *Resposta correta:* {correct_answer}")
                lines.append("")
            lines.extend([
                f"💡 {explanation}",
                "",
                "Digite *PROXIMA* para continuar",
            ])

        return "\n".join(lines)

    @staticmethod
    def format_results(
        score: int,
        max_score: int,
        correct: int,
        total: int,
        percentage: float,
        rank: str,
        rank_title: str,
        rank_message: str,
    ) -> str:
        """Formata resultado final do quiz.

        Args:
            score: Pontos obtidos
            max_score: Pontos máximos
            correct: Respostas corretas
            total: Total de perguntas
            percentage: Percentual de aproveitamento
            rank: ID do ranking
            rank_title: Título do ranking
            rank_message: Mensagem do ranking

        Returns:
            Mensagem formatada
        """
        emoji = EMOJI_MAP.get(rank, "🎯")

        lines = [
            f"{emoji} *{rank_title}*",
            "",
            f"📊 *Resultado:* {correct}/{total} corretas",
            f"🎯 *Pontos:* {score}/{max_score}",
            f"📈 *Aproveitamento:* {percentage:.1f}%",
            "",
            f"💬 {rank_message}",
            "",
        ]

        # Adicionar recomendações
        if percentage < 100:
            lines.extend([
                "💡 *Dica:*",
                "Tente novamente e consulte o regulamento para melhorar!",
                "",
                "📋 *Regulamento:*",
                "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view",
                "",
            ])
        else:
            lines.extend([
                "🎉 *Parabéns!*",
                "Você dominou completamente o regulamento!",
                "",
            ])

        lines.append("Digite *INICIAR* para fazer novamente")

        return "\n".join(lines)

    @staticmethod
    def format_chat_response(response: str) -> str:
        """Formata resposta do chat de dúvidas.

        Args:
            response: Resposta do agente de chat

        Returns:
            Mensagem formatada
        """
        return f"💬 *Assistente:*\n\n{response}\n\n_Digite sua resposta (A/B/C/D) quando estiver pronto_"

    @staticmethod
    def format_progress(question_num: int, total: int = 10) -> str:
        """Formata indicador de progresso.

        Args:
            question_num: Número da pergunta atual
            total: Total de perguntas

        Returns:
            Barra de progresso
        """
        filled = "🟩" * question_num
        empty = "⬜" * (total - question_num)
        return f"{filled}{empty} {question_num}/{total}"

    @staticmethod
    def format_regulamento() -> str:
        """Formata link do regulamento."""
        return """📋 *Regulamento Oficial*

Consulte o regulamento completo do programa Renda Extra Ton:

🔗 https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view

_Após ler, digite *INICIAR* para fazer o quiz!_"""

    @staticmethod
    def format_error(message: str = "Ocorreu um erro. Tente novamente.") -> str:
        """Formata mensagem de erro.

        Args:
            message: Mensagem de erro

        Returns:
            Mensagem formatada
        """
        return f"⚠️ *Erro*\n\n{message}\n\nDigite *AJUDA* para ver comandos disponíveis"

    @staticmethod
    def format_quiz_cancelled() -> str:
        """Mensagem de quiz cancelado."""
        return """❌ *Quiz Cancelado*

Seu progresso foi perdido.

Digite *INICIAR* para começar um novo quiz"""

    @staticmethod
    def format_status(question_num: int, score: int, correct: int) -> str:
        """Formata status atual do quiz.

        Args:
            question_num: Pergunta atual
            score: Pontos atuais
            correct: Respostas corretas até agora

        Returns:
            Mensagem formatada
        """
        progress = WhatsAppFormatter.format_progress(question_num - 1)
        return f"""📊 *Status do Quiz*

{progress}

📝 Pergunta atual: {question_num}/10
✅ Respostas corretas: {correct}
🎯 Pontos: {score}

Digite *CONTINUAR* para voltar ao quiz"""
