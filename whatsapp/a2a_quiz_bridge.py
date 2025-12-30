#!/usr/bin/env python3
"""
Bridge WhatsApp A2A + Quiz em Grupo
Integração Evolution API + Quiz Backend + LiteLLM

Baseado no bridge A2A original, adaptado para quiz em grupo.
"""

import asyncio
import json
import logging
import os
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, List
from aiohttp import web, ClientSession
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de logging
script_dir = os.path.dirname(os.path.abspath(__file__))
log_dir = os.path.join(script_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'a2a_quiz_bridge.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

PORT = int(os.getenv('BRIDGE_PORT', 4000))

# Evolution API
EVOLUTION_API_URL = os.getenv('EVOLUTION_API_URL', 'https://zp.agentesintegrados.com')
EVOLUTION_API_KEY = os.getenv('EVOLUTION_API_KEY', '')
EVOLUTION_INSTANCE_NAME = os.getenv('EVOLUTION_INSTANCE_NAME', 'Diego')

# Backend Quiz
QUIZ_BACKEND_URL = os.getenv('QUIZ_BACKEND_URL', 'http://localhost:8001')

# LiteLLM / AI (para chat de dúvidas)
LITELLM_MODEL = os.getenv('LITELLM_MODEL', 'gemini/gemini-2.0-flash-001')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')

# Configurações do Quiz
QUIZ_GROUP_ID = os.getenv('QUIZ_GROUP_ID', '120363422852368877@g.us')
QUIZ_MODE = os.getenv('QUIZ_MODE', 'group')  # 'group' ou 'individual'

# Sistema
SYSTEM_PROMPT = os.getenv('SYSTEM_PROMPT', '''Você é um assistente do Quiz Renda Extra Ton.
Ajude os participantes com dúvidas sobre as perguntas do quiz.
Seja conciso e educativo. NUNCA revele a resposta correta diretamente.''')

# ============================================================================
# CACHES E CONTROLES
# ============================================================================

# Cache para evitar processar mensagem duplicada
processed_messages: set = set()
MAX_CACHE_SIZE = 1000

# Cache para evitar loop (mensagens enviadas pela bridge)
bridge_sent_messages: Dict[str, float] = {}
BRIDGE_CACHE_TTL = 60

# Rate limiting
last_send_time: Dict[str, float] = {}
RATE_LIMIT_SECONDS = 2

# Lock por número/grupo
send_locks: Dict[str, asyncio.Lock] = {}

# Histórico de conversas
conversation_history: Dict[str, List[Dict]] = {}
MAX_HISTORY_SIZE = 20

# Whitelist de grupos (carregada do backend)
allowed_groups: set = set()

# ============================================================================
# EVOLUTION API CLIENT
# ============================================================================

async def send_via_evolution(target: str, message: str, is_group: bool = False) -> bool:
    """Envia mensagem via Evolution API

    Args:
        target: Número do telefone ou ID do grupo
        message: Texto da mensagem
        is_group: Se True, target é ID de grupo
    """
    try:
        url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE_NAME}"

        headers = {
            'Content-Type': 'application/json',
            'apikey': EVOLUTION_API_KEY
        }

        # Formatar destinatário
        if is_group:
            number = target  # Já vem no formato correto (xxxxx@g.us)
        else:
            target_clean = target.replace('+', '').replace('-', '').replace(' ', '')
            number = f"{target_clean}@s.whatsapp.net"

        payload = {
            'number': number,
            'text': message
        }

        async with ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status == 201:
                    data = await response.json()
                    message_id = data.get('key', {}).get('id', 'unknown')
                    logger.info(f"✅ Mensagem enviada! ID: {message_id}")

                    # Adicionar ao cache da bridge
                    cache_key = f"{target}:{hashlib.md5(message[:100].encode()).hexdigest()}"
                    bridge_sent_messages[cache_key] = time.time()

                    # Limpar cache antigo
                    now = time.time()
                    expired = [k for k, v in bridge_sent_messages.items() if now - v > BRIDGE_CACHE_TTL]
                    for k in expired:
                        del bridge_sent_messages[k]

                    return True
                else:
                    error = await response.text()
                    logger.error(f"❌ Erro Evolution {response.status}: {error}")
                    return False

    except Exception as e:
        logger.error(f"❌ Erro ao enviar via Evolution: {e}")
        return False


# ============================================================================
# QUIZ BACKEND CLIENT
# ============================================================================

async def sync_whitelist_from_backend():
    """Sincroniza whitelist de grupos do backend"""
    global allowed_groups
    try:
        url = f"{QUIZ_BACKEND_URL}/whatsapp/group/whitelist"

        async with ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    allowed_groups = set(data.get('groups', []))
                    logger.info(f"✅ Whitelist sincronizada: {len(allowed_groups)} grupos")
                    return True
                else:
                    logger.error(f"❌ Erro ao sincronizar whitelist: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar whitelist: {e}")
        return False


async def forward_to_quiz_backend(group_id: str, user_id: str, user_name: str, text: str) -> Optional[str]:
    """Encaminha mensagem para o backend do quiz

    Simula o webhook que o Evolution API enviaria diretamente.
    """
    try:
        url = f"{QUIZ_BACKEND_URL}/whatsapp/group/webhook"

        # Montar payload no formato Evolution API
        payload = {
            "event": "messages.upsert",
            "instance": EVOLUTION_INSTANCE_NAME,
            "data": {
                "key": {
                    "remoteJid": group_id,
                    "fromMe": False,
                    "id": f"bridge_{int(time.time()*1000)}",
                    "participant": f"{user_id}@s.whatsapp.net"
                },
                "pushName": user_name,
                "message": {
                    "messageType": "conversation",
                    "conversation": text
                }
            }
        }

        async with ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                if response.status == 200:
                    logger.info("✅ Mensagem encaminhada para backend do quiz")
                    return None  # Backend processa e envia resposta diretamente
                else:
                    error = await response.text()
                    logger.error(f"❌ Erro no backend do quiz: {error}")
                    return "⚠️ Erro ao processar mensagem no quiz."

    except Exception as e:
        logger.error(f"❌ Erro ao encaminhar para backend: {e}")
        return "⚠️ Erro de comunicação com o sistema de quiz."


# ============================================================================
# AI / LITELLM (para chat de dúvidas)
# ============================================================================

async def get_ai_response(context_id: str, text: str) -> str:
    """Processa mensagem com IA (para dúvidas fora do quiz)"""
    try:
        import litellm

        # Configurar API keys
        if GOOGLE_API_KEY:
            os.environ['GEMINI_API_KEY'] = GOOGLE_API_KEY

        # Recuperar histórico
        if context_id not in conversation_history:
            conversation_history[context_id] = []

        history = conversation_history[context_id]

        # Montar mensagens
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": text})

        logger.info(f"🤖 Processando com {LITELLM_MODEL}...")

        # Chamar LiteLLM
        response = await litellm.acompletion(
            model=LITELLM_MODEL,
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        ai_response = response.choices[0].message.content

        # Atualizar histórico
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": ai_response})

        if len(history) > MAX_HISTORY_SIZE * 2:
            conversation_history[context_id] = history[-(MAX_HISTORY_SIZE * 2):]

        return ai_response

    except ImportError:
        return "Sistema de IA não disponível."
    except Exception as e:
        logger.error(f"❌ Erro na IA: {e}")
        return f"Erro ao processar: {str(e)[:100]}"


# ============================================================================
# WEBHOOK HANDLERS
# ============================================================================

async def handle_evolution_webhook(request):
    """Webhook principal da Evolution API"""
    try:
        data = await request.json()

        logger.info("=" * 60)
        logger.info("📨 EVOLUTION WEBHOOK RECEBIDO")
        logger.debug(json.dumps(data, indent=2, ensure_ascii=False))

        # Extrair dados
        instance_data = data.get('data', {})
        key = instance_data.get('key', {})
        remote_jid = key.get('remoteJid', '')
        message_id = key.get('id', '')
        from_me = key.get('fromMe', False)

        # Verificar se é grupo
        is_group = '@g.us' in remote_jid

        # Extrair texto
        message_obj = instance_data.get('message', {})
        text = (
            message_obj.get('conversation') or
            message_obj.get('extendedTextMessage', {}).get('text') or
            ''
        )

        sender_name = instance_data.get('pushName', 'Participante')

        # Ignorar mensagens sem texto
        if not text:
            return web.json_response({'success': True, 'message': 'No text'})

        # Se é mensagem enviada por nós
        if from_me:
            cache_key = f"{remote_jid}:{hashlib.md5(text[:100].encode()).hexdigest()}"
            if cache_key in bridge_sent_messages:
                return web.json_response({'success': True, 'message': 'From bridge'})
            else:
                logger.info(f"📤 Mensagem manual: {text[:50]}...")
                return web.json_response({'success': True, 'message': 'Manual message'})

        # Deduplicação
        dedup_key = f"{message_id}:{remote_jid}:{text[:30]}"
        if dedup_key in processed_messages:
            return web.json_response({'success': True, 'message': 'Duplicate'})

        processed_messages.add(dedup_key)
        if len(processed_messages) > MAX_CACHE_SIZE:
            processed_messages.pop()

        # ====================================================================
        # ROTEAMENTO: GRUPO vs INDIVIDUAL
        # ====================================================================

        if is_group:
            # MODO GRUPO
            group_id = remote_jid

            # Extrair ID do usuário que enviou
            participant = key.get('participant', '')
            user_id = participant.replace('@s.whatsapp.net', '') if participant else 'unknown'

            logger.info(f"👥 Grupo: {group_id}")
            logger.info(f"👤 De: {sender_name} ({user_id})")
            logger.info(f"📝 Texto: {text}")

            # Verificar se grupo está autorizado
            if group_id not in allowed_groups:
                # Tentar sincronizar whitelist
                await sync_whitelist_from_backend()

                if group_id not in allowed_groups:
                    logger.warning(f"⚠️ Grupo não autorizado: {group_id}")
                    # Backend já envia mensagem de bloqueio
                    return web.json_response({'success': True, 'message': 'Group not whitelisted'})

            # Obter lock para este grupo
            if group_id not in send_locks:
                send_locks[group_id] = asyncio.Lock()

            async with send_locks[group_id]:
                # Rate limiting
                now = time.time()
                if group_id in last_send_time:
                    time_since_last = now - last_send_time[group_id]
                    if time_since_last < RATE_LIMIT_SECONDS:
                        await asyncio.sleep(RATE_LIMIT_SECONDS - time_since_last)

                # Encaminhar para backend do quiz
                last_send_time[group_id] = time.time()
                error_msg = await forward_to_quiz_backend(group_id, user_id, sender_name, text)

                # Se houve erro, enviar mensagem de erro
                if error_msg:
                    await send_via_evolution(group_id, error_msg, is_group=True)

        else:
            # MODO INDIVIDUAL - ignorar ou responder com IA
            phone = remote_jid.replace('@s.whatsapp.net', '').replace('@c.us', '')

            logger.info(f"📱 Individual de: {sender_name} ({phone})")
            logger.info(f"📝 Texto: {text}")

            # Enviar mensagem informando que bot é só para grupos
            response = """🤖 *Bot de Quiz em Grupo*

Olá! Este bot funciona apenas em grupos autorizados.

Para usar o quiz, adicione-me ao grupo *Quiz - Ton* e interaja lá!

🎯 _Este é um quiz interativo para grupos!_"""

            if phone not in send_locks:
                send_locks[phone] = asyncio.Lock()

            async with send_locks[phone]:
                await send_via_evolution(phone, response, is_group=False)

        logger.info("=" * 60)
        return web.json_response({'success': True, 'message': 'Processed'})

    except Exception as e:
        logger.error(f"❌ Erro no webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return web.json_response({'error': str(e)}, status=500)


async def handle_send_message(request):
    """API para enviar mensagem manualmente"""
    try:
        data = await request.json()
        target = data.get('target', '')  # Pode ser phone ou group_id
        message = data.get('message', '')
        is_group = data.get('is_group', False)

        if not target or not message:
            return web.json_response({'error': 'target and message required'}, status=400)

        success = await send_via_evolution(target, message, is_group=is_group)

        return web.json_response({
            'success': success,
            'target': target,
            'is_group': is_group,
            'message': message[:100]
        })

    except Exception as e:
        logger.error(f"❌ Erro ao enviar: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def handle_sync_whitelist(request):
    """API para sincronizar whitelist"""
    try:
        success = await sync_whitelist_from_backend()
        return web.json_response({
            'success': success,
            'groups': list(allowed_groups),
            'count': len(allowed_groups)
        })
    except Exception as e:
        return web.json_response({'error': str(e)}, status=500)


async def handle_health(request):
    """Health check"""
    return web.json_response({
        'status': 'healthy',
        'bridge': 'whatsapp-a2a-quiz',
        'mode': QUIZ_MODE,
        'evolution_api': EVOLUTION_API_URL,
        'quiz_backend': QUIZ_BACKEND_URL,
        'ai_model': LITELLM_MODEL,
        'timestamp': datetime.utcnow().isoformat(),
        'stats': {
            'processed_messages': len(processed_messages),
            'active_conversations': len(conversation_history),
            'allowed_groups': len(allowed_groups)
        },
        'config': {
            'quiz_group_id': QUIZ_GROUP_ID,
            'instance': EVOLUTION_INSTANCE_NAME
        }
    })


# ============================================================================
# STARTUP
# ============================================================================

async def on_startup(app):
    """Executado ao iniciar a aplicação"""
    logger.info("🚀 Sincronizando whitelist do backend...")
    await sync_whitelist_from_backend()


# ============================================================================
# APP SETUP
# ============================================================================

def create_app():
    """Cria aplicação aiohttp"""
    app = web.Application()

    # Webhooks da Evolution API
    app.router.add_post('/webhook', handle_evolution_webhook)
    app.router.add_post('/webhook/MESSAGES_UPSERT', handle_evolution_webhook)
    app.router.add_post('/webhook/messages-upsert', handle_evolution_webhook)

    # APIs
    app.router.add_post('/api/send', handle_send_message)
    app.router.add_post('/api/sync-whitelist', handle_sync_whitelist)

    # Health
    app.router.add_get('/health', handle_health)

    # Startup
    app.on_startup.append(on_startup)

    return app


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 BRIDGE WHATSAPP A2A + QUIZ EM GRUPO")
    logger.info(f"   📡 Porta: {PORT}")
    logger.info(f"   🔗 URL: http://localhost:{PORT}")
    logger.info(f"   📱 Evolution API: {EVOLUTION_API_URL}")
    logger.info(f"   🎯 Quiz Backend: {QUIZ_BACKEND_URL}")
    logger.info(f"   🎮 Modo: {QUIZ_MODE}")
    logger.info(f"   👥 Grupo Quiz: {QUIZ_GROUP_ID}")
    logger.info(f"   📝 Instância: {EVOLUTION_INSTANCE_NAME}")
    logger.info("=" * 60)

    app = create_app()
    web.run_app(app, host='0.0.0.0', port=PORT)
