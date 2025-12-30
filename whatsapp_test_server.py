#!/usr/bin/env python3
"""
Servidor MÍNIMO para testar WhatsApp em Grupo
Sem dependências do RAG - apenas para validar integração
"""

import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Importar apenas módulos WhatsApp (sem dependências do RAG)
from whatsapp.group_models import (
    GroupQuizState,
    ParticipantAnswer,
    QuestionState,
    ParticipantScore,
    GroupQuizSession,
)
from whatsapp.group_manager import GroupStateManager
from whatsapp.group_formatter import GroupMessageFormatter
from whatsapp.evolution_client import EvolutionAPIClient

import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="WhatsApp Quiz Test Server",
    description="Servidor mínimo para testar integração WhatsApp",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# GLOBALS
# =============================================================================

group_manager = GroupStateManager()
formatter = GroupMessageFormatter()

# Evolution API client
evolution = EvolutionAPIClient(
    base_url=os.getenv("EVOLUTION_API_URL", "http://zp.agentesintegrados.com"),
    api_key=os.getenv("EVOLUTION_API_KEY", ""),
    instance_name=os.getenv("EVOLUTION_INSTANCE", "Diego"),
)

# =============================================================================
# MOCK DATA (Para Testar)
# =============================================================================

MOCK_QUESTION = {
    "id": 1,
    "question": "Como funciona o programa Renda Extra Ton?",
    "options": [
        {"label": "A", "text": "Cashback automático em todas as vendas"},
        {"label": "B", "text": "Programa de pontos acumulados"},
        {"label": "C", "text": "Bônus mensal fixo"},
        {"label": "D", "text": "Desconto em produtos"},
    ],
    "correct_index": 0,
    "explanation": "O programa oferece cashback automático em todas as transações realizadas.",
    "difficulty": "easy",
    "points": 10,
}

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "server": "whatsapp-quiz-test",
        "message": "Servidor mínimo para teste WhatsApp",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "server": "whatsapp-quiz-test",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/whatsapp/group/whitelist")
async def get_whitelist():
    """Lista grupos autorizados."""
    groups = group_manager.list_allowed_groups()
    return {"total": len(groups), "groups": groups}


@app.post("/whatsapp/group/whitelist/add/{group_id}")
async def add_to_whitelist(group_id: str):
    """Adiciona grupo à whitelist."""
    success = group_manager.add_allowed_group(group_id)
    return {
        "status": "ok" if success else "already_exists",
        "message": f"Grupo {group_id} {'adicionado' if success else 'já estava'} na whitelist"
    }


@app.delete("/whatsapp/group/whitelist/remove/{group_id}")
async def remove_from_whitelist(group_id: str):
    """Remove grupo da whitelist."""
    success = group_manager.remove_allowed_group(group_id)
    return {
        "status": "ok" if success else "not_found",
        "message": f"Grupo {group_id} {'removido' if success else 'não estava'} na whitelist"
    }


@app.get("/whatsapp/group/active")
async def get_active_groups():
    """Lista grupos com quiz ativo."""
    active = group_manager.get_active_groups()
    return {
        "total": len(active),
        "groups": [
            {
                "group_id": s.group_id,
                "group_name": s.group_name,
                "quiz_id": s.quiz_id,
                "current_question": s.current_question,
                "participants": len(s.participants),
                "state": s.state,
            }
            for s in active
        ],
    }


@app.post("/whatsapp/group/webhook")
async def group_webhook(request: Request):
    """Webhook para Evolution API - TESTE SIMPLIFICADO."""
    try:
        data = await request.json()
        logger.info("=" * 60)
        logger.info("📨 WEBHOOK RECEBIDO")
        logger.info(f"Data: {data}")

        # Extrair dados
        instance_data = data.get("data", {})
        key = instance_data.get("key", {})
        remote_jid = key.get("remoteJid", "")
        from_me = key.get("fromMe", False)

        # Verificar se é grupo ANTES de ignorar fromMe
        is_group = "@g.us" in remote_jid

        # Apenas ignorar fromMe se NÃO for grupo
        # Em grupos, precisamos processar nossas próprias mensagens também
        if from_me and not is_group:
            logger.info("ℹ️ Mensagem individual de nós mesmos, ignorando")
            return JSONResponse({"success": True, "message": "from me individual"})

        # Verificar se é grupo
        is_group = "@g.us" in remote_jid

        if not is_group:
            # Mensagem individual - ignorar silenciosamente (não responder)
            logger.info("📱 Mensagem individual - ignorando silenciosamente")
            return JSONResponse({"success": True, "message": "private ignored"})

        # É grupo - verificar whitelist
        group_id = remote_jid
        if not group_manager.is_group_allowed(group_id):
            logger.warning(f"⚠️ Grupo não autorizado: {group_id}")
            await evolution.send_text(group_id, formatter.format_group_not_allowed())
            return JSONResponse({"success": True, "message": "group not whitelisted"})

        # Extrair texto
        message_obj = instance_data.get("message", {})
        text = (
            message_obj.get("conversation") or
            message_obj.get("extendedTextMessage", {}).get("text") or
            ""
        )

        if not text:
            return JSONResponse({"success": True, "message": "no text"})

        # Extrair participante
        participant = key.get("participant", "")
        user_id = participant.replace("@s.whatsapp.net", "") if participant else "unknown"
        user_name = instance_data.get("pushName", "Participante")

        logger.info(f"👥 Grupo: {group_id}")
        logger.info(f"👤 De: {user_name} ({user_id})")
        logger.info(f"📝 Texto: {text}")

        # Processar comandos simples (TESTE)
        text_upper = text.upper().strip()

        if text_upper in ["OI", "OLÁ", "HELLO"]:
            await evolution.send_text(group_id, formatter.format_welcome())

        elif text_upper == "AJUDA":
            await evolution.send_text(group_id, formatter.format_help())

        elif text_upper == "REGULAMENTO":
            await evolution.send_text(group_id, formatter.format_regulamento())

        elif text_upper == "INICIAR":
            # Teste: responder que vai iniciar
            await evolution.send_text(
                group_id,
                f"🎮 *Quiz Iniciado!*\n\n{user_name} iniciou o quiz!\n\n"
                f"⚠️ *MODO TESTE* - Backend completo não está disponível.\n"
                f"Este é apenas um teste de comunicação WhatsApp.\n\n"
                f"✅ Webhook funcionando!\n"
                f"✅ Grupo autorizado!\n"
                f"✅ Mensagens sendo recebidas e enviadas!\n\n"
                f"Para usar o quiz completo, configure o backend com RAG."
            )

        else:
            # Outros comandos - apenas confirmar recebimento
            logger.info(f"ℹ️ Comando '{text}' recebido (não implementado em modo teste)")

        logger.info("=" * 60)
        return JSONResponse({"success": True, "message": "processed"})

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🚀 SERVIDOR DE TESTE - WHATSAPP QUIZ")
    logger.info("   📡 Porta: 8001")
    logger.info("   🔗 URL: http://localhost:8001")
    logger.info("   ⚠️  MODO TESTE (sem RAG)")
    logger.info("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8001)
