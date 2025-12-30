# 🚀 Guia Rápido - Quiz WhatsApp

Guia para colocar o quiz funcionando no WhatsApp em **5 minutos**.

## ✅ Pré-requisitos

- Docker instalado
- Python 3.9+
- Conta WhatsApp para vincular

## 📦 Passo 1: Instalar Evolution API

```bash
# Clonar repositório
git clone https://github.com/EvolutionAPI/evolution-api.git
cd evolution-api

# Iniciar com Docker
docker compose up -d

# Verificar se está rodando
curl http://localhost:8080
```

**Resultado esperado:** `{"status": "ok"}`

## ⚙️ Passo 2: Configurar Variáveis de Ambiente

```bash
cd /Users/2a/.claude/backend-quiz

# Copiar exemplo
cp .env.example .env

# Editar .env e adicionar:
nano .env
```

**Variáveis obrigatórias:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
EVOLUTION_API_KEY=B6D711FCDE4D4FD5936544120E713976  # Ver instalação Evolution
EVOLUTION_INSTANCE=quiz-instance
```

## 📱 Passo 3: Criar Instância WhatsApp

```bash
# Criar instância
curl -X POST http://localhost:8080/instance/create \
  -H "Content-Type: application/json" \
  -H "apikey: B6D711FCDE4D4FD5936544120E713976" \
  -d '{
    "instanceName": "quiz-instance",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS"
  }'
```

**Escanear QR Code:**

1. Abra no navegador: `http://localhost:8080/instance/connect/quiz-instance`
2. Escaneie com WhatsApp → Dispositivos Vinculados → Vincular Dispositivo
3. Aguarde "Conectado!"

## 🌐 Passo 4: Expor Backend (ngrok)

```bash
# Instalar ngrok (se não tiver)
# https://ngrok.com/download

# Expor porta 8001
ngrok http 8001

# Copiar URL pública gerada
# Exemplo: https://abc123.ngrok.io
```

## 🔗 Passo 5: Configurar Webhook

```bash
# Substitua URL_PUBLICA pela URL do ngrok
curl -X POST "http://localhost:8080/webhook/set/quiz-instance" \
  -H "Content-Type: application/json" \
  -H "apikey: B6D711FCDE4D4FD5936544120E713976" \
  -d '{
    "url": "https://abc123.ngrok.io/whatsapp/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

**Confirmar configuração:**
```bash
curl http://localhost:8080/webhook/find/quiz-instance \
  -H "apikey: B6D711FCDE4D4FD5936544120E713976"
```

## 📚 Passo 6: Ingerir Documentos no RAG

```bash
cd /Users/2a/.claude/backend-quiz

# Ingerir regulamento (substitua pelo seu arquivo)
python scripts/ingest.py ./docs/regulamento.pdf

# Verificar ingestão
curl http://localhost:8001/rag/stats
```

## 🚀 Passo 7: Iniciar Backend

```bash
python server.py

# Ou com auto-reload (desenvolvimento)
uvicorn server:app --reload --port 8001
```

**Verificar endpoints:**
```bash
# Health check
curl http://localhost:8001/health

# Status WhatsApp
curl http://localhost:8001/whatsapp/status
```

## 💬 Passo 8: Testar no WhatsApp!

1. Envie mensagem para o número conectado:
   ```
   INICIAR
   ```

2. Responda ao quiz normalmente:
   ```
   A
   ```

3. Tire dúvidas:
   ```
   DUVIDA como funciona o programa?
   ```

4. Comandos úteis:
   ```
   AJUDA
   STATUS
   REGULAMENTO
   PARAR
   ```

---

## 🐛 Resolução de Problemas

### Webhook não recebe mensagens

```bash
# 1. Verificar se Evolution está conectado
curl http://localhost:8080/instance/connectionState/quiz-instance \
  -H "apikey: B6D711FCDE4D4FD5936544120E713976"

# 2. Verificar webhook configurado
curl http://localhost:8080/webhook/find/quiz-instance \
  -H "apikey: B6D711FCDE4D4FD5936544120E713976"

# 3. Testar URL ngrok acessível
curl https://abc123.ngrok.io/health
```

### Erro "Nenhum documento encontrado no RAG"

```bash
# Ingerir documentos primeiro
python scripts/ingest.py ./docs/seu-arquivo.pdf

# Verificar
curl http://localhost:8001/rag/stats
```

### Evolution API desconectou

```bash
# Reconectar
# Abra no navegador e escaneie novo QR Code
http://localhost:8080/instance/connect/quiz-instance
```

### Backend não inicia

```bash
# Verificar dependências
pip install -e .

# Verificar .env
cat .env | grep EVOLUTION

# Logs detalhados
LOGLEVEL=DEBUG python server.py
```

---

## 📝 Comandos Úteis

### Evolution API

```bash
# Listar instâncias
curl http://localhost:8080/instance/fetchInstances \
  -H "apikey: $EVOLUTION_API_KEY"

# Status da instância
curl http://localhost:8080/instance/connectionState/quiz-instance \
  -H "apikey: $EVOLUTION_API_KEY"

# Deletar instância
curl -X DELETE http://localhost:8080/instance/delete/quiz-instance \
  -H "apikey: $EVOLUTION_API_KEY"
```

### Backend Quiz

```bash
# Usuários ativos
curl http://localhost:8001/whatsapp/active-users

# Resetar usuário
curl -X POST http://localhost:8001/whatsapp/reset-user/5511999999999

# Status quiz
curl http://localhost:8001/whatsapp/status
```

---

## 🎯 Próximos Passos

1. **Produção:**
   - Usar domínio próprio (sem ngrok)
   - Configurar SSL/HTTPS
   - Implementar autenticação no webhook

2. **Personalização:**
   - Editar mensagens em `whatsapp/message_formatter.py`
   - Adicionar comandos em `whatsapp/router.py`
   - Customizar fluxo do quiz

3. **Monitoramento:**
   - Configurar logging persistente
   - Dashboard de métricas
   - Alertas de erro

---

## 📚 Documentação Completa

Consulte `whatsapp/README.md` para documentação detalhada.

---

**Dúvidas?** Verifique logs:
- Backend: `tail -f logs/server.log` (se configurado)
- Evolution: `docker logs -f evolution-api`
