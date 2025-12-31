"""Formatadores de mensagem para Quiz em Grupo."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quiz.models.schemas import QuizQuestion

    from .group_models import GroupQuizSession, GroupQuizState, ParticipantScore, QuestionState

from .group_models import GroupQuizState

RANK_EMOJI = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}


def _format_participant_name(user_id: str, user_name: str) -> str:
    """Formata nome do participante com últimos 4 dígitos do número.

    Args:
        user_id: ID do usuário (número WhatsApp)
        user_name: Nome do usuário

    Returns:
        Nome formatado (ex: "Bianca (7291)")
    """
    import re

    # Se o nome já termina com (XXXX), não adicionar novamente
    if re.search(r'\(\d{4}\)$', user_name):
        return user_name

    clean_id = user_id.split("@")[0]
    digits = "".join(c for c in clean_id if c.isdigit())
    last_4 = digits[-4:] if len(digits) >= 4 else digits
    return f"{user_name} ({last_4})" if last_4 else user_name


class GroupMessageFormatter:
    """Formata mensagens do quiz para grupos WhatsApp."""

    @staticmethod
    def format_welcome() -> str:
        """Mensagem de boas-vindas ao grupo."""
        return """🎯 *Quiz Renda Extra Ton - Modo Grupo!*

Bem-vindos ao quiz interativo! Vocês vão competir entre si respondendo perguntas sobre o programa.

📝 *Como Funciona:*
• Todos veem a mesma pergunta
• Cada pessoa responde individualmente (A/B/C/D)
• Ganha quem fizer mais pontos
• Ranking atualizado em tempo real
• 🎁 Novos participantes = mais perguntas!

🏆 *Para Começar:*
Digite *INICIAR* para criar o lobby!

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
        total_questions: int = 10,
        current_turn_name: str | None = None,
    ) -> str:
        """Formata pergunta para o grupo.

        Args:
            question: Objeto QuizQuestion
            question_num: Número da pergunta (1-N)
            already_answered: Lista de nomes que já responderam
            total_questions: Total de perguntas no quiz
            current_turn_name: Nome de quem é a vez (sistema de turnos)

        Returns:
            Mensagem formatada
        """
        lines = [
            f"❓ *Pergunta {question_num}/{total_questions}*",
            f"💎 *Vale {question.points} pontos*",
        ]

        # Mostrar de quem é a vez (sistema de turnos)
        if current_turn_name:
            lines.append("")
            lines.append(f"🎯 *Vez de:* {current_turn_name}")

        lines.extend([
            "",
            f"*{question.question}*",
            "",
        ])

        # Adicionar opções
        for opt in question.options:
            lines.append(f"*{opt.label})* {opt.text}")

        lines.append("")
        if current_turn_name:
            lines.append(f"📱 *{current_turn_name}, responda:* A, B, C ou D")
        else:
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

        lines = ["🏆 *Ranking Atual*"]

        # Só mostrar progresso se o quiz já começou
        if session.current_question > 0:
            lines.append(f"Pergunta {session.current_question}/{session.total_questions}")

        lines.append("")

        # Mostrar ranking
        limit = len(ranking) if show_full else min(3, len(ranking))
        for i, participant in enumerate(ranking[:limit], 1):
            emoji = RANK_EMOJI.get(i, f"{i}º")
            percentage = participant.percentage
            display_name = _format_participant_name(participant.user_id, participant.user_name)
            lines.append(
                f"{emoji} *{display_name}*\n"
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
            display_name = _format_participant_name(participant.user_id, participant.user_name)
            lines.append(
                f"{emoji} *{display_name}*\n"
                f"    🎯 {participant.total_score} pontos\n"
                f"    ✅ {participant.correct_answers}/{session.total_questions} corretas ({percentage:.0f}%)\n"
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
            f"📝 Pergunta: {session.current_question}/{session.total_questions}",
            f"👥 Participantes: {len(session.participants)}",
            "",
        ]

        # Top 3 atual
        top3 = session.get_top_3()
        if top3:
            lines.append("🏆 *Top 3 Atual:*")
            for i, p in enumerate(top3, 1):
                emoji = RANK_EMOJI.get(i, f"{i}º")
                display_name = _format_participant_name(p.user_id, p.user_name)
                lines.append(f"{emoji} {display_name} - {p.total_score} pts")

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
• *DICA* - Receber dica do regulamento
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

    @staticmethod
    def format_lobby_created(created_by: str, session: GroupQuizSession) -> str:
        """Lobby criado - aguardando participantes.

        Args:
            created_by: Nome de quem criou o lobby
            session: Sessão do grupo

        Returns:
            Mensagem formatada
        """
        # Usar get_participant_display para mostrar nome + últimos 4 dígitos
        participant_displays = [
            session.get_participant_display(user_id) or p.user_name
            for user_id, p in session.participants.items()
        ]

        # Formatar lista de participantes
        if participant_displays:
            participants_text = '\n'.join([f"* {p}" for p in participant_displays])
        else:
            participants_text = "* Nenhum ainda"

        return f"""🎮 *Lobby do Quiz Criado!*

👥 *Participantes ({len(participant_displays)}):*
{participants_text}

🚀 Digite *COMECAR* quando todos estiverem prontos"""

    @staticmethod
    def format_lobby_status(session: GroupQuizSession) -> str:
        """Status do lobby.

        Args:
            session: Sessão do grupo

        Returns:
            Mensagem formatada
        """
        # Usar get_participant_display para mostrar nome + últimos 4 dígitos
        participant_displays = [
            session.get_participant_display(user_id) or p.user_name
            for user_id, p in session.participants.items()
        ]

        return f"""🎮 *Lobby do Quiz*

👥 *Participantes ({len(participant_displays)}):*
{chr(10).join(f'• {name}' for name in participant_displays) if participant_displays else '• Nenhum ainda'}

🚀 Digite *COMECAR* quando todos estiverem prontos

📢 *Convide mais pessoas:*
https://chat.whatsapp.com/BKrn8SOMBYG8v9LWtFOTJk"""

    @staticmethod
    def format_quiz_started_with_participants(session: GroupQuizSession) -> str:
        """Quiz iniciado com lista de participantes.

        Args:
            session: Sessão do grupo

        Returns:
            Mensagem formatada
        """
        # Usar get_participant_display para mostrar nome + últimos 4 dígitos
        participant_displays = [
            session.get_participant_display(user_id) or p.user_name
            for user_id, p in session.participants.items()
        ]

        return f"""🎯 *Quiz Iniciado!*

📊 *{session.total_questions} perguntas* sobre Renda Extra Ton
🎁 _Novos participantes = +3 perguntas extras!_

👥 *Participantes ({len(participant_displays)}):*
{chr(10).join(f'• {name}' for name in participant_displays)}

_Respondam com A, B, C ou D_"""
