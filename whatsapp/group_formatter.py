"""Formatadores de mensagem para Quiz em Grupo."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quiz.models.schemas import QuizQuestion

    from .group_models import GroupQuizSession, ParticipantScore, QuestionState

RANK_EMOJI = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}


class GroupMessageFormatter:
    """Formata mensagens do quiz para grupos WhatsApp."""

    @staticmethod
    def format_welcome() -> str:
        """Mensagem de boas-vindas ao grupo."""
        return """🎯 *Quiz Renda Extra Ton - Modo Grupo!*

Bem-vindos ao quiz interativo! Vocês vão competir entre si respondendo 10 perguntas sobre o programa.

📝 *Como Funciona:*
• Todos veem a mesma pergunta
• Cada pessoa responde individualmente (A/B/C/D)
• Ganha quem fizer mais pontos
• Ranking atualizado em tempo real

🏆 *Para Começar:*
Digite *INICIAR* para iniciar o quiz!

💡 *Comandos Úteis:*
• *RANKING* - Ver placar atual
• *STATUS* - Ver progresso
• *AJUDA* - Mostrar comandos"""

    @staticmethod
    def format_quiz_started(started_by_name: str) -> str:
        """Mensagem de quiz iniciado.

        Args:
            started_by_name: Nome de quem iniciou

        Returns:
            Mensagem formatada
        """
        return f"""🎮 *Quiz Iniciado!*

{started_by_name} iniciou o quiz!

🔥 Preparem-se...
A primeira pergunta vem aí!

_Respondam com A, B, C ou D_"""

    @staticmethod
    def format_question(
        question: QuizQuestion,
        question_num: int,
        already_answered: list[str] | None = None,
    ) -> str:
        """Formata pergunta para o grupo.

        Args:
            question: Objeto QuizQuestion
            question_num: Número da pergunta (1-10)
            already_answered: Lista de nomes que já responderam

        Returns:
            Mensagem formatada
        """
        lines = [
            f"❓ *Pergunta {question_num}/10*",
            f"💎 *Vale {question.points} pontos*",
            "",
            f"*{question.question}*",
            "",
        ]

        # Adicionar opções
        for opt in question.options:
            lines.append(f"*{opt.label})* {opt.text}")

        lines.append("")
        lines.append("📱 *Responda com:* A, B, C ou D")

        # Mostrar quem já respondeu
        if already_answered:
            lines.append("")
            lines.append(f"✅ *Já responderam:* {', '.join(already_answered)}")

        return "\n".join(lines)

    @staticmethod
    def format_answer_feedback(
        user_name: str,
        is_correct: bool,
        points_earned: int,
        answered_count: int,
        total_participants: int,
    ) -> str:
        """Feedback quando alguém responde.

        Args:
            user_name: Nome do participante
            is_correct: Se acertou
            points_earned: Pontos ganhos
            answered_count: Quantos já responderam
            total_participants: Total de participantes ativos

        Returns:
            Mensagem formatada
        """
        emoji = "✅" if is_correct else "❌"
        status = "acertou" if is_correct else "errou"
        points_msg = f"+{points_earned} pontos" if is_correct else "0 pontos"

        return (
            f"{emoji} *{user_name}* {status}! ({points_msg})\n"
            f"📊 {answered_count}/{total_participants} participantes responderam"
        )

    @staticmethod
    def format_question_results(
        question_state: QuestionState,
        correct_answer: str,
        explanation: str,
    ) -> str:
        """Resultado da pergunta (quando todos responderam ou timeout).

        Args:
            question_state: Estado da pergunta
            correct_answer: Resposta correta formatada
            explanation: Explicação da resposta

        Returns:
            Mensagem formatada
        """
        correct_count = question_state.get_correct_count()
        total_count = len(question_state.answers)

        lines = [
            "📊 *Resultado da Pergunta*",
            "",
            f"✔️ *Resposta correta:* {correct_answer}",
            "",
            f"💡 {explanation}",
            "",
            f"🎯 *{correct_count}/{total_count}* acertaram",
            "",
        ]

        # Mostrar quem acertou
        correct_users = [
            ans.user_name for ans in question_state.answers if ans.is_correct
        ]
        if correct_users:
            lines.append(f"✅ *Acertaram:* {', '.join(correct_users)}")
        else:
            lines.append("❌ _Ninguém acertou esta pergunta_")

        lines.extend([
            "",
            "⏭️ Digite *PROXIMA* para continuar",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_ranking(
        session: GroupQuizSession,
        show_full: bool = False,
    ) -> str:
        """Formata ranking do grupo.

        Args:
            session: Sessão do grupo
            show_full: Se deve mostrar todos (ou apenas top 3)

        Returns:
            Mensagem formatada
        """
        ranking = session.get_ranking()

        if not ranking:
            return "📊 *Ranking*\n\nNenhum participante ainda."

        lines = [
            "🏆 *Ranking Atual*",
            f"Pergunta {session.current_question}/10",
            "",
        ]

        # Mostrar ranking
        limit = len(ranking) if show_full else min(3, len(ranking))
        for i, participant in enumerate(ranking[:limit], 1):
            emoji = RANK_EMOJI.get(i, f"{i}º")
            percentage = participant.percentage
            lines.append(
                f"{emoji} *{participant.user_name}*\n"
                f"    🎯 {participant.total_score} pts | "
                f"✅ {participant.correct_answers}/{participant.total_answers} "
                f"({percentage:.0f}%)"
            )

        if len(ranking) > limit:
            lines.append("")
            lines.append(f"_... e mais {len(ranking) - limit} participantes_")

        return "\n".join(lines)

    @staticmethod
    def format_final_results(session: GroupQuizSession) -> str:
        """Resultado final do quiz em grupo.

        Args:
            session: Sessão do grupo

        Returns:
            Mensagem formatada
        """
        ranking = session.get_ranking()

        lines = [
            "🎊 *Quiz Finalizado!*",
            "",
            "🏆 *PÓDIO FINAL*",
            "",
        ]

        # Top 3
        for i, participant in enumerate(ranking[:3], 1):
            emoji = RANK_EMOJI.get(i, "")
            percentage = participant.percentage
            lines.append(
                f"{emoji} *{participant.user_name}*\n"
                f"    🎯 {participant.total_score} pontos\n"
                f"    ✅ {participant.correct_answers}/10 corretas ({percentage:.0f}%)\n"
            )

        # Estatísticas gerais
        if ranking:
            total_participants = len(ranking)
            avg_score = sum(p.total_score for p in ranking) / total_participants
            best_score = ranking[0].total_score

            lines.extend([
                "",
                "📊 *Estatísticas:*",
                f"👥 {total_participants} participantes",
                f"📈 Média: {avg_score:.0f} pontos",
                f"🏆 Melhor: {best_score} pontos",
            ])

        lines.extend([
            "",
            "🎯 *Quer jogar novamente?*",
            "Digite *INICIAR* para um novo quiz!",
            "",
            "📋 Consulte o regulamento:",
            "https://drive.google.com/file/d/1IGdnWI8CD4ltMSM5bJ5RN4sjP5Tu0REO/view",
        ])

        return "\n".join(lines)

    @staticmethod
    def format_status(session: GroupQuizSession) -> str:
        """Status atual do quiz.

        Args:
            session: Sessão do grupo

        Returns:
            Mensagem formatada
        """
        if session.state == GroupQuizState.IDLE:
            return "⏸️ Nenhum quiz ativo. Digite *INICIAR* para começar!"

        lines = [
            "📊 *Status do Quiz*",
            "",
            f"📝 Pergunta: {session.current_question}/10",
            f"👥 Participantes: {len(session.participants)}",
            "",
        ]

        # Top 3 atual
        top3 = session.get_top_3()
        if top3:
            lines.append("🏆 *Top 3 Atual:*")
            for i, p in enumerate(top3, 1):
                emoji = RANK_EMOJI.get(i, f"{i}º")
                lines.append(f"{emoji} {p.user_name} - {p.total_score} pts")

        return "\n".join(lines)

    @staticmethod
    def format_already_answered(user_name: str) -> str:
        """Mensagem quando usuário tenta responder duas vezes.

        Args:
            user_name: Nome do usuário

        Returns:
            Mensagem formatada
        """
        return f"⚠️ *{user_name}*, você já respondeu esta pergunta!"

    @staticmethod
    def format_quiz_not_active() -> str:
        """Mensagem quando quiz não está ativo."""
        return """⚠️ *Nenhum quiz ativo*

Digite *INICIAR* para começar um novo quiz!"""

    @staticmethod
    def format_help() -> str:
        """Mensagem de ajuda."""
        return """📖 *Comandos do Quiz em Grupo*

*Durante o Quiz:*
• *A, B, C, D* - Responder pergunta
• *RANKING* - Ver placar atual
• *STATUS* - Ver progresso
• *PROXIMA* - Avançar pergunta (após todos responderem)
• *PARAR* - Cancelar quiz

*Geral:*
• *INICIAR* - Começar novo quiz
• *REGULAMENTO* - Link do regulamento
• *AJUDA* - Esta mensagem

🎯 *Dica:* Responda rápido para não perder pontos!"""

    @staticmethod
    def format_group_not_allowed() -> str:
        """Mensagem quando grupo não está autorizado."""
        return """🔒 *Grupo Não Autorizado*

Este bot funciona apenas em grupos autorizados.

Para adicionar este grupo à lista de permitidos, o administrador do bot precisa executar o comando de autorização.

_Entre em contato com o administrador do sistema._"""

    @staticmethod
    def format_private_message_blocked() -> str:
        """Mensagem para mensagens privadas (individual)."""
        return """🤖 *Bot de Quiz em Grupo*

Olá! Este bot funciona apenas em grupos autorizados.

Para usar o quiz, adicione-me a um grupo e peça ao administrador para autorizar o grupo.

🎯 _Este é um quiz interativo para grupos!_"""

    @staticmethod
    def format_waiting_next() -> str:
        """Mensagem aguardando próxima pergunta."""
        return """⏳ *Aguardando...*

Digite *PROXIMA* para continuar para a próxima pergunta!"""

    @staticmethod
    def format_quiz_cancelled(cancelled_by: str) -> str:
        """Quiz cancelado.

        Args:
            cancelled_by: Nome de quem cancelou

        Returns:
            Mensagem formatada
        """
        return f"""❌ *Quiz Cancelado*

{cancelled_by} cancelou o quiz.

Digite *INICIAR* para começar um novo quiz!"""
