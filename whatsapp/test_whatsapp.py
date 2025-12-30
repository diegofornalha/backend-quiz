"""Script de teste para integração WhatsApp."""

import asyncio
import os

from dotenv import load_dotenv

from evolution_client import EvolutionAPIClient
from message_formatter import WhatsAppFormatter

load_dotenv()


async def test_connection():
    """Testa conexão com Evolution API."""
    print("🔍 Testando conexão com Evolution API...")

    client = EvolutionAPIClient(
        base_url=os.getenv("EVOLUTION_API_URL", "http://localhost:8080"),
        api_key=os.getenv("EVOLUTION_API_KEY", ""),
        instance_name=os.getenv("EVOLUTION_INSTANCE", "quiz-instance"),
    )

    try:
        status = await client.get_instance_status()
        print("✅ Conexão OK!")
        print(f"Status: {status}")
        return True
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
        return False


async def test_send_message():
    """Testa envio de mensagem."""
    print("\n📤 Testando envio de mensagem...")

    # Solicitar número de telefone de teste
    test_number = input("Digite o número de teste (com DDI, ex: 5511999999999): ")

    client = EvolutionAPIClient(
        base_url=os.getenv("EVOLUTION_API_URL", "http://localhost:8080"),
        api_key=os.getenv("EVOLUTION_API_KEY", ""),
        instance_name=os.getenv("EVOLUTION_INSTANCE", "quiz-instance"),
    )

    formatter = WhatsAppFormatter()

    try:
        # Enviar mensagem de boas-vindas
        message = formatter.format_welcome()
        result = await client.send_text(test_number, message)
        print("✅ Mensagem enviada!")
        print(f"Resultado: {result}")
        return True
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem: {e}")
        return False


async def test_formatters():
    """Testa formatadores de mensagem."""
    print("\n📝 Testando formatadores...")

    formatter = WhatsAppFormatter()

    # Mock de pergunta
    from quiz.models.schemas import QuizOption, QuizQuestion
    from quiz.models.enums import QuizDifficulty

    question = QuizQuestion(
        id=1,
        question="Qual é a capital do Brasil?",
        options=[
            QuizOption(label="A", text="São Paulo"),
            QuizOption(label="B", text="Brasília"),
            QuizOption(label="C", text="Rio de Janeiro"),
            QuizOption(label="D", text="Salvador"),
        ],
        correct_index=1,
        explanation="Brasília é a capital federal do Brasil desde 1960.",
        difficulty=QuizDifficulty.EASY,
        points=10,
    )

    # Testar formatação de pergunta
    print("\n--- Pergunta Formatada ---")
    print(formatter.format_question(question, 1))

    # Testar formatação de feedback
    print("\n--- Feedback Correto ---")
    print(formatter.format_feedback(True, question.explanation))

    print("\n--- Feedback Incorreto ---")
    print(formatter.format_feedback(False, question.explanation, "B) Brasília"))

    # Testar formatação de resultado
    print("\n--- Resultado Final ---")
    print(
        formatter.format_results(
            score=180,
            max_score=200,
            correct=9,
            total=10,
            percentage=90.0,
            rank="especialista_iii",
            rank_title="Especialista III",
            rank_message="Excelente! Você possui conhecimento profundo do programa.",
        )
    )

    print("\n✅ Formatadores testados!")
    return True


async def test_webhook_setup():
    """Testa configuração de webhook."""
    print("\n🔗 Testando configuração de webhook...")

    webhook_url = input(
        "Digite a URL pública do webhook (ex: https://abc123.ngrok.io/whatsapp/webhook): "
    )

    client = EvolutionAPIClient(
        base_url=os.getenv("EVOLUTION_API_URL", "http://localhost:8080"),
        api_key=os.getenv("EVOLUTION_API_KEY", ""),
        instance_name=os.getenv("EVOLUTION_INSTANCE", "quiz-instance"),
    )

    try:
        result = await client.set_webhook(webhook_url)
        print("✅ Webhook configurado!")
        print(f"Resultado: {result}")
        return True
    except Exception as e:
        print(f"❌ Erro ao configurar webhook: {e}")
        return False


async def main():
    """Menu principal."""
    print("=" * 60)
    print("🧪 TESTE DE INTEGRAÇÃO WHATSAPP")
    print("=" * 60)

    while True:
        print("\nEscolha uma opção:")
        print("1. Testar conexão com Evolution API")
        print("2. Testar envio de mensagem")
        print("3. Testar formatadores")
        print("4. Configurar webhook")
        print("5. Executar todos os testes")
        print("0. Sair")

        choice = input("\nOpção: ")

        if choice == "1":
            await test_connection()
        elif choice == "2":
            await test_send_message()
        elif choice == "3":
            await test_formatters()
        elif choice == "4":
            await test_webhook_setup()
        elif choice == "5":
            print("\n🚀 Executando todos os testes...")
            await test_connection()
            await test_formatters()
            print("\n✅ Testes básicos concluídos!")
            print("⚠️ Testes de envio e webhook requerem entrada manual.")
        elif choice == "0":
            print("\n👋 Até logo!")
            break
        else:
            print("❌ Opção inválida!")


if __name__ == "__main__":
    asyncio.run(main())
