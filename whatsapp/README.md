# 🎯 Quiz WhatsApp - Integração com Evolution API

Integração completa do sistema de quiz via WhatsApp usando Evolution API v2.

## 📋 Índice

- [Arquitetura](#arquitetura)
- [Instalação](#instalação)
- [Configuração](#configuração)
- [Fluxo do Usuário](#fluxo-do-usuário)
- [Comandos Disponíveis](#comandos-disponíveis)
- [Desenvolvimento](#desenvolvimento)
- [Troubleshooting](#troubleshooting)

---

## 🏗️ Arquitetura

### Componentes

```
┌─────────────────┐
│   WhatsApp      │  Usuários enviam mensagens
│     User        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Evolution API  │  Recebe/envia mensagens
│   (Webhook)     │
└────────┬────────┘
         │ POST /whatsapp/webhook
         ▼
┌─────────────────┐
│  Backend Quiz   │  FastAPI + Router WhatsApp
│  (router.py)    │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────┐ ┌──────────────┐
│ Quiz    │ │ User State   │
│ Engine  │ │ Manager      │
└─────────┘ └──────────────┘
```

### Módulos

- **`router.py`** - Endpoints FastAPI e lógica de negócio
- **`evolution_client.py`** - Cliente HTTP para Evolution API
- **`user_state.py`** - Gerenciamento de estado por usuário
- **`message_formatter.py`** - Formatação de mensagens para WhatsApp
- **`models.py`** - Schemas Pydantic e enums

---

## 📦 Instalação

### 1. Instalar Evolution API

A Evolution API pode ser instalada via Docker:

```bash
# Clonar repositório oficial
git clone https://github.com/EvolutionAPI/evolution-api.git
cd evolution-api

# Configurar e iniciar
docker compose up -d
```

**Documentação oficial:** https://doc.evolution-api.com/

### 2. Instalar dependências do backend

```bash
cd /Users/2a/.claude/backend-quiz
pip install -e .
```

As dependências já incluem `httpx` necessário para o cliente Evolution API.

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente

Adicione ao `.env` do backend:

```bash
# Evolution API Configuration
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=sua-api-key-global-aqui
EVOLUTION_INSTANCE=quiz-instance

# Backend existente
ANTHROPIC_API_KEY=sua-chave-claude
API_KEYS=dev-key-123
```

**Como obter as credenciais:**

1. **API Key Global**: Definida na instalação da Evolution API
2. **Instance Name**: Nome da instância WhatsApp que você criar

### 2. Criar Instância WhatsApp

Use a interface web da Evolution API ou API REST:

```bash
POST http://localhost:8080/instance/create
Content-Type: application/json
apikey: sua-api-key-global

{
  "instanceName": "quiz-instance",
  "qrcode": true,
  "integration": "WHATSAPP-BAILEYS"
}
```

**Escanear QR Code:**

1. Acesse: `http://localhost:8080/instance/connect/quiz-instance`
2. Escaneie o QR Code com seu WhatsApp
3. Aguarde confirmação de conexão

### 3. Configurar Webhook

**Opção A: Manualmente via API**

```bash
POST http://localhost:8080/webhook/set/quiz-instance
Content-Type: application/json
apikey: sua-api-key-global

{
  "url": "https://seu-dominio.com/whatsapp/webhook",
  "enabled": true,
  "events": ["MESSAGES_UPSERT"]
}
```

**Opção B: Via endpoint do backend**

```bash
POST http://localhost:8001/whatsapp/configure-webhook?webhook_url=https://seu-dominio.com/whatsapp/webhook
```

**⚠️ Importante:**

- Para testes locais, use **ngrok** ou **localtunnel**:
  ```bash
  ngrok http 8001
  # Use a URL pública gerada (ex: https://abc123.ngrok.io/whatsapp/webhook)
  ```

### 4. Ingerir Documentos no RAG

O quiz precisa de documentos no RAG para funcionar:

```bash
cd /Users/2a/.claude/backend-quiz
python scripts/ingest.py ./docs/regulamento_renda_extra.pdf
```

### 5. Iniciar Backend

```bash
python server.py
# Ou com auto-reload:
uvicorn server:app --reload --port 8001
```

---

## 👤 Fluxo do Usuário

### 1. Início da Conversa

Usuário envia qualquer mensagem → Recebe boas-vindas:

```
🎯 Bem-vindo ao Quiz Renda Extra Ton!

Teste seus conhecimentos sobre o programa...

📝 10 perguntas de múltipla escolha
💬 Tire dúvidas durante o quiz
🏆 Ranking baseado no seu desempenho

Para começar, digite: INICIAR
```

### 2. Durante o Quiz

```
📝 Pergunta 1/10

❓ Como funciona o programa Renda Extra Ton?

A) Opção 1
B) Opção 2
C) Opção 3
D) Opção 4

💬 Responda com: A, B, C ou D
ℹ️ Tem dúvida? Digite: DUVIDA + sua pergunta
```

**Modo Chat de Dúvidas:**

```
Usuário: DUVIDA como funciona o programa?

💬 Assistente:
O programa funciona através de...

Digite sua resposta (A/B/C/D) quando estiver pronto
```

### 3. Feedback de Resposta

**Resposta Correta:**
```
✅ Resposta Correta!

💡 Explicação detalhada...

Digite PROXIMA para continuar
```

**Resposta Incorreta:**
```
❌ Resposta Incorreta

✔️ Resposta correta: B) Texto da opção

💡 Explicação detalhada...

Digite PROXIMA para continuar
```

### 4. Resultado Final

```
🏆 Embaixador

📊 Resultado: 10/10 corretas
🎯 Pontos: 200/200
📈 Aproveitamento: 100.0%

💬 Domínio total! Você está pronto...

🎉 Parabéns!
Você dominou completamente o regulamento!

Digite INICIAR para fazer novamente
```

---

## 📝 Comandos Disponíveis

| Comando | Descrição | Disponível em |
|---------|-----------|---------------|
| **INICIAR** | Começar novo quiz | Qualquer momento |
| **A / B / C / D** | Responder pergunta | Durante quiz |
| **DUVIDA** + texto | Tirar dúvida sobre questão atual | Durante quiz |
| **PROXIMA** | Avançar para próxima pergunta | Após responder |
| **STATUS** | Ver progresso atual | Durante quiz |
| **PARAR** | Cancelar quiz | Durante quiz |
| **REGULAMENTO** | Link para regulamento oficial | Qualquer momento |
| **AJUDA** | Mostrar comandos | Qualquer momento |

---

## 🛠️ Desenvolvimento

### Estrutura de Arquivos

```
whatsapp/
├── __init__.py              # Exporta router
├── router.py                # Endpoints FastAPI e lógica principal
├── evolution_client.py      # Cliente HTTP para Evolution API
├── user_state.py            # Gerenciamento de estado persistente
├── message_formatter.py     # Formatadores de mensagem
├── models.py                # Schemas Pydantic
└── README.md                # Esta documentação
```

### Estado do Usuário

Cada usuário tem um estado persistido em disco (`.whatsapp_states/{user_id}.json`):

```python
{
  "user_id": "5511999999999",
  "flow_state": "in_quiz",      # idle | in_quiz | in_chat | finished
  "quiz_id": "uuid-do-quiz",
  "current_question": 3,
  "answers": [0, 2, 1],          # Índices das respostas (A=0, B=1, ...)
  "score": 30,
  "chat_session_id": "whatsapp_5511999999999"
}
```

### Adicionar Novos Comandos

Edite `router.py` → função `process_message()`:

```python
# Comandos globais
if text_upper == "MEU_COMANDO":
    await evolution.send_text(user_number, "Resposta do comando")
    return
```

### Customizar Mensagens

Edite `message_formatter.py` → classe `WhatsAppFormatter`:

```python
@staticmethod
def format_nova_mensagem(parametros) -> str:
    return f"Texto formatado: {parametros}"
```

---

## 🐛 Troubleshooting

### 1. Webhook não está recebendo mensagens

**Verificar:**
```bash
# Status da instância
curl http://localhost:8080/instance/connectionState/quiz-instance \
  -H "apikey: sua-api-key"

# Configuração do webhook
curl http://localhost:8080/webhook/find/quiz-instance \
  -H "apikey: sua-api-key"
```

**Soluções:**
- Verificar se URL pública do webhook está acessível
- Usar ngrok para expor porta local
- Verificar logs da Evolution API

### 2. Erro ao iniciar quiz

**Erro:** `Nenhum documento encontrado no RAG`

**Solução:**
```bash
# Verificar documentos ingeridos
curl http://localhost:8001/rag/stats

# Ingerir documentos
python scripts/ingest.py ./docs/seu-documento.pdf
```

### 3. Estado do usuário corrompido

**Reset manual:**
```bash
# Via API
POST http://localhost:8001/whatsapp/reset-user/5511999999999

# Ou deletar arquivo
rm .whatsapp_states/5511999999999.json
```

### 4. Evolution API desconectou

**Reconectar:**
1. Acesse: `http://localhost:8080/instance/connect/quiz-instance`
2. Escaneie novo QR Code

### 5. Logs de Debug

**Backend:**
```bash
# Verificar logs do servidor
tail -f logs/server.log

# Ou executar com verbose
LOGLEVEL=DEBUG python server.py
```

**Evolution API:**
```bash
# Logs do container Docker
docker logs -f evolution-api
```

---

## 🔒 Segurança

### Validar API Key no Webhook

O código atual não valida o webhook. Para produção, adicione validação:

```python
@router.post("/webhook")
async def evolution_webhook(request: Request, ...):
    # Validar API key ou assinatura do webhook
    api_key = request.headers.get("apikey")
    if api_key != os.getenv("EVOLUTION_API_KEY"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # ...
```

### Rate Limiting

Para evitar spam, adicione rate limiting por usuário:

```python
from collections import defaultdict
from datetime import datetime, timedelta

_last_message = defaultdict(lambda: datetime.min)
COOLDOWN = timedelta(seconds=2)

async def process_message(user_number: str, ...):
    # Verificar cooldown
    if datetime.now() - _last_message[user_number] < COOLDOWN:
        await evolution.send_text(user_number, "Aguarde alguns segundos...")
        return
    _last_message[user_number] = datetime.now()
    # ...
```

---

## 📊 Monitoramento

### Endpoints de Gestão

```bash
# Status da instância WhatsApp
GET /whatsapp/status

# Usuários com quiz ativo
GET /whatsapp/active-users

# Resetar usuário
POST /whatsapp/reset-user/{user_number}

# Configurar webhook
POST /whatsapp/configure-webhook?webhook_url=...
```

### Métricas

Monitore:
- Número de quizzes iniciados por dia
- Taxa de conclusão de quizzes
- Perguntas com mais dúvidas
- Distribuição de rankings

---

## 🚀 Próximos Passos

1. **Integração com Analytics**
   - Enviar eventos para Google Analytics
   - Dashboard de métricas em tempo real

2. **Múltiplos Quizzes**
   - Permitir usuário escolher tema do quiz
   - Quiz personalizado por nível

3. **Gamificação**
   - Ranking global de usuários
   - Badges e conquistas

4. **Notificações Proativas**
   - Lembrar usuário de finalizar quiz
   - Novos quizzes disponíveis

---

## 📞 Suporte

- **Evolution API:** https://doc.evolution-api.com/
- **Claude API:** https://docs.anthropic.com/
- **Issues:** https://github.com/seu-repo/issues

---

**Desenvolvido com ❤️ usando Claude Sonnet 4.5 e Evolution API**
