# 🧪 Testes com cURL - Quiz WhatsApp

Exemplos de comandos cURL para testar a integração localmente.

## 📋 Setup

```bash
# Exportar variáveis de ambiente
export API_KEY="B6D711FCDE4D4FD5936544120E713976"  # Sua API key da Evolution
export INSTANCE="quiz-instance"
export BACKEND_URL="http://localhost:8001"
export EVOLUTION_URL="http://localhost:8080"
```

---

## 🔧 Evolution API - Testes Básicos

### 1. Verificar Status da Instância

```bash
curl -X GET "$EVOLUTION_URL/instance/connectionState/$INSTANCE" \
  -H "apikey: $API_KEY"
```

**Resposta esperada:**
```json
{
  "instance": "quiz-instance",
  "state": "open"
}
```

### 2. Listar Todas as Instâncias

```bash
curl -X GET "$EVOLUTION_URL/instance/fetchInstances" \
  -H "apikey: $API_KEY"
```

### 3. Criar Nova Instância

```bash
curl -X POST "$EVOLUTION_URL/instance/create" \
  -H "Content-Type: application/json" \
  -H "apikey: $API_KEY" \
  -d '{
    "instanceName": "quiz-instance",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS"
  }'
```

### 4. Configurar Webhook

```bash
curl -X POST "$EVOLUTION_URL/webhook/set/$INSTANCE" \
  -H "Content-Type: application/json" \
  -H "apikey: $API_KEY" \
  -d '{
    "url": "https://sua-url-ngrok.ngrok.io/whatsapp/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

### 5. Verificar Webhook Configurado

```bash
curl -X GET "$EVOLUTION_URL/webhook/find/$INSTANCE" \
  -H "apikey: $API_KEY"
```

---

## 💬 Enviar Mensagens de Teste

### 1. Enviar Mensagem de Texto

```bash
# Substitua 5511999999999 pelo número de teste
curl -X POST "$EVOLUTION_URL/message/sendText/$INSTANCE" \
  -H "Content-Type: application/json" \
  -H "apikey: $API_KEY" \
  -d '{
    "number": "5511999999999",
    "text": "🎯 *Teste de mensagem*\n\nSistema funcionando!",
    "delay": 1000
  }'
```

### 2. Enviar Mensagem com Botões

```bash
curl -X POST "$EVOLUTION_URL/message/sendButtons/$INSTANCE" \
  -H "Content-Type: application/json" \
  -H "apikey: $API_KEY" \
  -d '{
    "number": "5511999999999",
    "title": "Quiz Renda Extra",
    "description": "Escolha uma opção:",
    "buttons": [
      {"id": "1", "text": "Iniciar Quiz"},
      {"id": "2", "text": "Ver Regulamento"},
      {"id": "3", "text": "Ajuda"}
    ],
    "footer": "Sistema de Quiz WhatsApp"
  }'
```

### 3. Enviar Lista Interativa

```bash
curl -X POST "$EVOLUTION_URL/message/sendList/$INSTANCE" \
  -H "Content-Type: application/json" \
  -H "apikey: $API_KEY" \
  -d '{
    "number": "5511999999999",
    "title": "Menu do Quiz",
    "description": "Escolha uma opção abaixo:",
    "buttonText": "Ver Opções",
    "sections": [
      {
        "title": "Ações Principais",
        "rows": [
          {"id": "start", "title": "Iniciar Quiz", "description": "Começar um novo quiz"},
          {"id": "status", "title": "Ver Status", "description": "Ver progresso atual"}
        ]
      },
      {
        "title": "Ajuda",
        "rows": [
          {"id": "help", "title": "Comandos", "description": "Lista de comandos disponíveis"},
          {"id": "reg", "title": "Regulamento", "description": "Consultar regulamento"}
        ]
      }
    ]
  }'
```

---

## 🎯 Backend Quiz - Endpoints Administrativos

### 1. Health Check

```bash
curl -X GET "$BACKEND_URL/health"
```

### 2. Status da Integração WhatsApp

```bash
curl -X GET "$BACKEND_URL/whatsapp/status"
```

**Resposta esperada:**
```json
{
  "status": "ok",
  "evolution": {
    "instance": "quiz-instance",
    "state": "open"
  }
}
```

### 3. Listar Usuários Ativos

```bash
curl -X GET "$BACKEND_URL/whatsapp/active-users"
```

**Resposta esperada:**
```json
{
  "total": 2,
  "users": [
    {
      "user_id": "5511999999999",
      "quiz_id": "abc-123",
      "current_question": 5,
      "score": 40,
      "flow_state": "in_quiz"
    }
  ]
}
```

### 4. Resetar Estado de Usuário

```bash
# Substitua pelo número do usuário
curl -X POST "$BACKEND_URL/whatsapp/reset-user/5511999999999"
```

### 5. Configurar Webhook (via Backend)

```bash
curl -X POST "$BACKEND_URL/whatsapp/configure-webhook?webhook_url=https://sua-url.ngrok.io/whatsapp/webhook"
```

---

## 🧪 Simular Webhook (Testes Locais)

### 1. Simular Mensagem Recebida

```bash
curl -X POST "$BACKEND_URL/whatsapp/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "instance": "quiz-instance",
    "data": {
      "key": {
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false,
        "id": "test-msg-id"
      },
      "message": {
        "messageType": "conversation",
        "conversation": "INICIAR"
      }
    }
  }'
```

### 2. Simular Resposta de Pergunta

```bash
curl -X POST "$BACKEND_URL/whatsapp/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "instance": "quiz-instance",
    "data": {
      "key": {
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false,
        "id": "test-msg-id-2"
      },
      "message": {
        "messageType": "conversation",
        "conversation": "A"
      }
    }
  }'
```

### 3. Simular Dúvida

```bash
curl -X POST "$BACKEND_URL/whatsapp/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "instance": "quiz-instance",
    "data": {
      "key": {
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": false,
        "id": "test-msg-id-3"
      },
      "message": {
        "messageType": "conversation",
        "conversation": "DUVIDA como funciona o programa?"
      }
    }
  }'
```

---

## 📊 RAG - Verificar Base de Conhecimento

### 1. Stats do RAG

```bash
curl -X GET "$BACKEND_URL/rag/stats"
```

**Resposta esperada:**
```json
{
  "total_chunks": 245,
  "embedding_model": "BAAI/bge-small-en-v1.5",
  "database": "sqlite-vec"
}
```

### 2. Buscar no RAG

```bash
curl -X POST "$BACKEND_URL/rag/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "como funciona o programa",
    "top_k": 3
  }'
```

### 3. Ingerir Documento (via API)

```bash
# Ingestão de texto direto
curl -X POST "$BACKEND_URL/rag/ingest/text" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Conteúdo do documento...",
    "metadata": {
      "source": "manual",
      "type": "test"
    }
  }'
```

---

## 🔄 Quiz API - Testes do Engine

### 1. Iniciar Quiz (Lazy Generation)

```bash
curl -X POST "$BACKEND_URL/quiz/start" \
  -H "Content-Type: application/json"
```

**Resposta esperada:**
```json
{
  "quiz_id": "abc-123-def",
  "total_questions": 10,
  "first_question": {
    "id": 1,
    "question": "Pergunta...",
    "options": [...],
    "difficulty": "easy",
    "points": 10
  }
}
```

### 2. Buscar Pergunta Específica

```bash
# Substitua abc-123-def pelo quiz_id e 2 pelo índice da pergunta
curl -X GET "$BACKEND_URL/quiz/question/abc-123-def/2"
```

### 3. Status do Quiz

```bash
curl -X GET "$BACKEND_URL/quiz/status/abc-123-def"
```

**Resposta esperada:**
```json
{
  "found": true,
  "complete": false,
  "generated_count": 7,
  "total_questions": 10,
  "max_score": 140
}
```

### 4. Todas as Perguntas

```bash
curl -X GET "$BACKEND_URL/quiz/all/abc-123-def"
```

---

## 🎯 Fluxo Completo de Teste

### Script de Teste Automatizado

```bash
#!/bin/bash

echo "🧪 Teste Completo da Integração WhatsApp"
echo "========================================"

# 1. Verificar backend
echo "1. Verificando backend..."
curl -s $BACKEND_URL/health | jq .

# 2. Verificar Evolution
echo "2. Verificando Evolution API..."
curl -s -X GET "$EVOLUTION_URL/instance/connectionState/$INSTANCE" \
  -H "apikey: $API_KEY" | jq .

# 3. Verificar RAG
echo "3. Verificando base de conhecimento..."
curl -s $BACKEND_URL/rag/stats | jq .

# 4. Verificar webhook
echo "4. Verificando webhook..."
curl -s -X GET "$EVOLUTION_URL/webhook/find/$INSTANCE" \
  -H "apikey: $API_KEY" | jq .

# 5. Listar usuários ativos
echo "5. Usuários ativos..."
curl -s $BACKEND_URL/whatsapp/active-users | jq .

echo ""
echo "✅ Testes concluídos!"
```

**Salvar como `test_integration.sh` e executar:**

```bash
chmod +x test_integration.sh
./test_integration.sh
```

---

## 🐛 Debug de Problemas

### 1. Ver Logs do Backend

```bash
# Se configurou logging em arquivo
tail -f logs/server.log

# Ou executar com debug
LOGLEVEL=DEBUG python server.py
```

### 2. Ver Logs da Evolution API

```bash
docker logs -f evolution-api

# Ou com filtro
docker logs evolution-api 2>&1 | grep ERROR
```

### 3. Testar Conectividade

```bash
# Testar se ngrok está acessível
curl https://sua-url.ngrok.io/health

# Testar webhook endpoint
curl -X POST https://sua-url.ngrok.io/whatsapp/webhook \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 4. Limpar Estado Corrompido

```bash
# Resetar usuário via API
curl -X POST "$BACKEND_URL/whatsapp/reset-user/5511999999999"

# Ou deletar arquivo manualmente
rm .whatsapp_states/5511999999999.json
```

---

## 📝 Variáveis de Ambiente para Testes

Crie um arquivo `.env.test` para testes:

```bash
# .env.test
export BACKEND_URL="http://localhost:8001"
export EVOLUTION_URL="http://localhost:8080"
export API_KEY="B6D711FCDE4D4FD5936544120E713976"
export INSTANCE="quiz-instance"
export TEST_NUMBER="5511999999999"  # Seu número de teste
```

**Usar:**
```bash
source .env.test
```

---

**Dica:** Use [jq](https://stedolan.github.io/jq/) para formatar JSON:

```bash
curl ... | jq .
```
