"""
Simple WhatsApp Server - Apenas endpoints básicos para teste
"""

import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simple-server")

app = FastAPI(title="Simple WhatsApp API")

# Estado simples em memória
WHITELIST = set()

@app.get("/health")
async def health():
    return {"status": "ok", "service": "simple-whatsapp"}

@app.get("/whatsapp/group/whitelist")
async def get_whitelist():
    """Lista grupos na whitelist"""
    return {"whitelist": list(WHITELIST)}

@app.post("/whatsapp/group/whitelist/add/{group_id}")
async def add_to_whitelist(group_id: str):
    """Adiciona grupo à whitelist"""
    WHITELIST.add(group_id)
    logger.info(f"Grupo adicionado: {group_id}")
    return {"success": True, "group_id": group_id, "whitelist": list(WHITELIST)}

@app.post("/whatsapp/group/webhook")
async def webhook(payload: dict):
    """Webhook simulado"""
    logger.info(f"Webhook recebido: {payload}")

    # Extrair dados básicos
    remote_jid = payload.get("data", {}).get("key", {}).get("remoteJid")
    message = payload.get("data", {}).get("message", {}).get("conversation", "")

    if not remote_jid:
        return {"error": "remoteJid não encontrado"}

    # Verificar whitelist
    if remote_jid not in WHITELIST:
        return {
            "success": False,
            "error": "Grupo não está na whitelist",
            "group_id": remote_jid
        }

    # Simular resposta
    return {
        "success": True,
        "group_id": remote_jid,
        "message_received": message,
        "response": "Sistema de quiz está online! (modo teste - sem geração de perguntas)"
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando Simple Server na porta 8001...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
