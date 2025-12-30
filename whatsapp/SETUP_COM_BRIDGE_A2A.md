# 🚀 Setup Quiz com Bridge A2A Existente

Guia para integrar o quiz em grupo usando seu bridge A2A já configurado.

## 📋 Arquitetura

```
WhatsApp                Evolution API            Bridge A2A           Backend Quiz
  Grupo    ────────>   zp.agentes...  ────────>  porta 4000  ────────>  porta 8001
           mensagens                   webhook                 processa quiz
```

**Vantagens de usar o Bridge:**
- ✅ Já está configurado e funcionando
- ✅ Mantém toda lógica A2A existente
- ✅ Adiciona quiz sem quebrar nada
- ✅ Rate limiting e cache já prontos

---

## 🎯 Passo a Passo

### 1. Configurar .env do Bridge

```bash
cd /caminho/do/seu/bridge
cp .env .env.backup  # Backup do atual

# Adicionar novas variáveis ao .env existente
cat >> .env << 'EOF'

# Backend do Quiz
QUIZ_BACKEND_URL=http://localhost:8001
QUIZ_GROUP_ID=120363422852368877@g.us
QUIZ_MODE=group
EOF
```

Seu `.env` completo deve ficar assim:

```bash
# Bridge Configuration
PORT=4000

# Evolution API (já configurado)
EVOLUTION_API_URL=http://zp.agentesintegrados.com
EVOLUTION_API_KEY=2392A322B4FF-47D3-B87F-B0B081EDB8C7
EVOLUTION_INSTANCE_NAME=Diego

# Backend do Quiz (NOVO)
QUIZ_BACKEND_URL=http://localhost:8001
QUIZ_GROUP_ID=120363422852368877@g.us
QUIZ_MODE=group

# Rate Limiting
RATE_LIMIT_SECONDS=2
BRIDGE_CACHE_TTL=60

# LiteLLM / AI
LITELLM_MODEL=gemini/gemini-2.0-flash-001
GOOGLE_API_KEY=sua-chave-google
```

### 2. Substituir Bridge Atual

```bash
# Parar bridge atual
# (Ctrl+C se estiver rodando)

# Backup do bridge antigo
cp seu_bridge_atual.py seu_bridge_atual.py.backup

# Copiar novo bridge
cp /Users/2a/.claude/backend-quiz/whatsapp/a2a_quiz_bridge.py ./bridge_quiz.py
```

### 3. Configurar Backend do Quiz

```bash
cd /Users/2a/.claude/backend-quiz

# Copiar .env
cp .env.example .env

# Editar .env
nano .env
```

Adicionar:

```bash
ANTHROPIC_API_KEY=sk-ant-sua-chave
API_KEYS=dev-key-123
ENVIRONMENT=development
```

### 4. Adicionar Grupo à Whitelist

```bash
# Iniciar backend primeiro
cd /Users/2a/.claude/backend-quiz
python server.py &

# Adicionar grupo à whitelist
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/120363422852368877@g.us
```

**Resposta esperada:**
```json
{
  "status": "ok",
  "message": "Grupo 120363422852368877@g.us adicionado à whitelist"
}
```

### 5. Ingerir Documentos no RAG

```bash
cd /Users/2a/.claude/backend-quiz

# Ingerir regulamento (substitua pelo seu arquivo)
python scripts/ingest.py ./docs/regulamento_renda_extra.pdf

# Verificar ingestão
curl http://localhost:8001/rag/stats
```

### 6. Iniciar Bridge

```bash
cd /caminho/do/seu/bridge

# Instalar dependências (se necessário)
pip install aiohttp python-dotenv litellm

# Iniciar bridge
python bridge_quiz.py
```

**Saída esperada:**
```
============================================================
🚀 BRIDGE WHATSAPP A2A + QUIZ EM GRUPO
   📡 Porta: 4000
   🔗 URL: http://localhost:4000
   📱 Evolution API: http://zp.agentesintegrados.com
   🎯 Quiz Backend: http://localhost:8001
   🎮 Modo: group
   👥 Grupo Quiz: 120363422852368877@g.us
   📝 Instância: Diego
============================================================
🚀 Sincronizando whitelist do backend...
✅ Whitelist sincronizada: 1 grupos
```

### 7. Configurar Webhook na Evolution API

```bash
curl -X POST "http://zp.agentesintegrados.com/webhook/set/Diego" \
  -H "Content-Type: application/json" \
  -H "apikey: 2392A322B4FF-47D3-B87F-B0B081EDB8C7" \
  -d '{
    "url": "http://SEU_IP_PUBLICO:4000/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

**⚠️ IMPORTANTE:**

Se seu servidor não tem IP público, use **ngrok**:

```bash
# Instalar ngrok
brew install ngrok  # macOS
# ou baixe de https://ngrok.com/download

# Expor porta 4000
ngrok http 4000

# Copie a URL gerada (ex: https://abc123.ngrok.io)
# Use essa URL no webhook acima
```

### 8. Testar no Grupo!

No grupo "Quiz - Ton", envie:

```
INICIAR
```

**Resposta esperada:**
```
🎮 Quiz Iniciado!
João iniciou o quiz!

🔥 Preparem-se...
A primeira pergunta vem aí!

❓ Pergunta 1/10
💎 Vale 10 pontos

[Pergunta aqui]

A) Opção 1
B) Opção 2
C) Opção 3
D) Opção 4

📱 Responda com: A, B, C ou D
```

---

## 🔧 Troubleshooting

### Problema: Bridge não inicia

**Verificar logs:**
```bash
tail -f logs/a2a_quiz_bridge.log
```

**Soluções comuns:**
- Verificar se porta 4000 está livre: `lsof -i :4000`
- Verificar variáveis de ambiente: `cat .env | grep QUIZ`

### Problema: Backend não responde

**Verificar se está rodando:**
```bash
curl http://localhost:8001/health
```

**Se não estiver:**
```bash
cd /Users/2a/.claude/backend-quiz
python server.py
```

### Problema: Grupo não recebe mensagens

**Verificar whitelist:**
```bash
curl http://localhost:8001/whatsapp/group/whitelist
```

**Adicionar se necessário:**
```bash
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/120363422852368877@g.us
```

### Problema: Evolution API não envia webhook

**Verificar configuração:**
```bash
curl -X GET "http://zp.agentesintegrados.com/webhook/find/Diego" \
  -H "apikey: 2392A322B4FF-47D3-B87F-B0B081EDB8C7"
```

**Reconfigurar:**
```bash
# Ver comando no passo 7
```

### Problema: RAG vazio

**Erro:** "Nenhum documento encontrado no RAG"

**Solução:**
```bash
cd /Users/2a/.claude/backend-quiz
python scripts/ingest.py ./docs/seu-regulamento.pdf
curl http://localhost:8001/rag/stats  # Verificar
```

---

## 📊 Monitoramento

### Health Check do Bridge

```bash
curl http://localhost:4000/health
```

**Resposta:**
```json
{
  "status": "healthy",
  "bridge": "whatsapp-a2a-quiz",
  "mode": "group",
  "stats": {
    "processed_messages": 42,
    "allowed_groups": 1
  },
  "config": {
    "quiz_group_id": "120363422852368877@g.us",
    "instance": "Diego"
  }
}
```

### Health Check do Backend

```bash
curl http://localhost:8001/health
```

### Grupos Ativos

```bash
curl http://localhost:8001/whatsapp/group/active
```

### Sincronizar Whitelist Manualmente

```bash
curl -X POST http://localhost:4000/api/sync-whitelist
```

---

## 🎮 Comandos no Grupo

| Comando | Função |
|---------|--------|
| `INICIAR` | Começar quiz |
| `A / B / C / D` | Responder |
| `RANKING` | Ver placar |
| `STATUS` | Ver progresso |
| `PROXIMA` | Avançar pergunta |
| `PARAR` | Cancelar quiz |
| `AJUDA` | Mostrar comandos |
| `REGULAMENTO` | Link regulamento |

---

## 🔄 Fluxo de Mensagens

```
1. Usuário no grupo: "INICIAR"
   ↓
2. WhatsApp → Evolution API
   ↓
3. Evolution API → Bridge (porta 4000)
   POST http://localhost:4000/webhook
   ↓
4. Bridge valida grupo e encaminha
   POST http://localhost:8001/whatsapp/group/webhook
   ↓
5. Backend processa e responde
   ↓
6. Backend → Evolution API diretamente
   POST http://zp.agentesintegrados.com/message/sendText/Diego
   ↓
7. Evolution API → WhatsApp → Grupo
```

---

## 📝 Comandos Úteis

### Iniciar tudo de uma vez

```bash
# Terminal 1: Backend
cd /Users/2a/.claude/backend-quiz
python server.py

# Terminal 2: Bridge
cd /caminho/do/seu/bridge
python bridge_quiz.py

# Terminal 3: Ngrok (se necessário)
ngrok http 4000
```

### Parar tudo

```bash
# Parar backend
pkill -f "python server.py"

# Parar bridge
pkill -f "python bridge_quiz.py"

# Parar ngrok
pkill -f ngrok
```

### Ver logs em tempo real

```bash
# Bridge
tail -f logs/a2a_quiz_bridge.log

# Backend (se configurado)
tail -f logs/server.log
```

---

## 🎯 Resumo

Você precisa de **3 coisas rodando**:

1. **Backend Quiz** (porta 8001)
   ```bash
   python server.py
   ```

2. **Bridge A2A** (porta 4000)
   ```bash
   python bridge_quiz.py
   ```

3. **Ngrok** (se não tiver IP público)
   ```bash
   ngrok http 4000
   ```

E configurar:
- ✅ Grupo na whitelist
- ✅ Webhook na Evolution API
- ✅ Documentos no RAG

**Pronto! O quiz já funciona no grupo! 🎉**

---

## 📞 Suporte

Arquivos importantes:
- `a2a_quiz_bridge.py` - Bridge adaptado
- `.env` - Configurações
- `logs/a2a_quiz_bridge.log` - Logs do bridge
- `GROUP_MODE.md` - Documentação completa

**Dúvidas? Verifique os logs primeiro!** 🐛
