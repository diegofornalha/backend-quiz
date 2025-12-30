#!/bin/bash

# ============================================================================
# SETUP AUTOMÁTICO - QUIZ EM GRUPO
# ============================================================================

set -e  # Parar em caso de erro

echo "============================================================"
echo "🚀 SETUP AUTOMÁTICO - QUIZ EM GRUPO"
echo "============================================================"
echo ""

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# 1. VERIFICAR DEPENDÊNCIAS
# ============================================================================

echo "📋 Verificando dependências..."

# Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 não encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3 OK${NC}"

# Pip
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ pip3 não encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✅ pip3 OK${NC}"

# Curl
if ! command -v curl &> /dev/null; then
    echo -e "${RED}❌ curl não encontrado${NC}"
    exit 1
fi
echo -e "${GREEN}✅ curl OK${NC}"

echo ""

# ============================================================================
# 2. CONFIGURAR VARIÁVEIS
# ============================================================================

echo "⚙️  Configuração do Ambiente"
echo "----------------------------"

# Seu grupo
GROUP_ID="120363422852368877@g.us"
echo "👥 Grupo: $GROUP_ID"

# URLs
BACKEND_URL="http://localhost:8001"
BRIDGE_PORT="4000"

# Evolution API (suas credenciais)
EVOLUTION_URL="http://zp.agentesintegrados.com"
EVOLUTION_KEY="2392A322B4FF-47D3-B87F-B0B081EDB8C7"
EVOLUTION_INSTANCE="Diego"

echo ""

# ============================================================================
# 3. INSTALAR DEPENDÊNCIAS DO BACKEND
# ============================================================================

echo "📦 Instalando dependências do backend..."

cd "$(dirname "$0")/.."  # Vai para backend-quiz/

if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}❌ pyproject.toml não encontrado. Execute do diretório correto.${NC}"
    exit 1
fi

pip3 install -e . -q
echo -e "${GREEN}✅ Dependências do backend instaladas${NC}"

echo ""

# ============================================================================
# 4. INICIAR BACKEND
# ============================================================================

echo "🚀 Iniciando backend do quiz..."

# Verificar se já está rodando
if curl -s "$BACKEND_URL/health" &> /dev/null; then
    echo -e "${YELLOW}⚠️  Backend já está rodando em $BACKEND_URL${NC}"
else
    # Iniciar em background
    nohup python3 server.py > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   PID: $BACKEND_PID"

    # Aguardar inicialização
    echo "   Aguardando backend inicializar..."
    sleep 3

    # Verificar se iniciou
    if curl -s "$BACKEND_URL/health" &> /dev/null; then
        echo -e "${GREEN}✅ Backend iniciado com sucesso${NC}"
    else
        echo -e "${RED}❌ Erro ao iniciar backend. Verifique logs/backend.log${NC}"
        exit 1
    fi
fi

echo ""

# ============================================================================
# 5. ADICIONAR GRUPO À WHITELIST
# ============================================================================

echo "🔐 Adicionando grupo à whitelist..."

RESPONSE=$(curl -s -X POST "$BACKEND_URL/whatsapp/group/whitelist/add/$GROUP_ID")
echo "   Resposta: $RESPONSE"

# Verificar se foi adicionado
if curl -s "$BACKEND_URL/whatsapp/group/whitelist" | grep -q "$GROUP_ID"; then
    echo -e "${GREEN}✅ Grupo adicionado à whitelist${NC}"
else
    echo -e "${RED}❌ Erro ao adicionar grupo${NC}"
    exit 1
fi

echo ""

# ============================================================================
# 6. VERIFICAR RAG
# ============================================================================

echo "📚 Verificando base de conhecimento (RAG)..."

RAG_STATS=$(curl -s "$BACKEND_URL/rag/stats")
TOTAL_CHUNKS=$(echo "$RAG_STATS" | grep -o '"total_chunks":[0-9]*' | grep -o '[0-9]*')

if [ "$TOTAL_CHUNKS" -gt 0 ]; then
    echo -e "${GREEN}✅ RAG configurado: $TOTAL_CHUNKS chunks${NC}"
else
    echo -e "${YELLOW}⚠️  RAG vazio. Você precisa ingerir documentos:${NC}"
    echo "   python scripts/ingest.py ./docs/regulamento.pdf"
    echo ""
    read -p "Deseja continuar mesmo assim? (s/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        exit 1
    fi
fi

echo ""

# ============================================================================
# 7. CONFIGURAR WEBHOOK
# ============================================================================

echo "🔗 Configurando webhook na Evolution API..."

# Perguntar URL pública
echo ""
echo "Você tem uma URL pública para o webhook?"
echo "1) Sim, tenho um domínio/IP público"
echo "2) Não, vou usar ngrok"
echo "3) Pular (configurar manualmente depois)"
echo ""
read -p "Escolha (1/2/3): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[1]$ ]]; then
    # URL pública fornecida
    read -p "Digite a URL pública (ex: http://meuip.com): " PUBLIC_URL
    WEBHOOK_URL="$PUBLIC_URL/webhook"

    echo "   Configurando webhook: $WEBHOOK_URL"

    WEBHOOK_RESPONSE=$(curl -s -X POST "$EVOLUTION_URL/webhook/set/$EVOLUTION_INSTANCE" \
      -H "Content-Type: application/json" \
      -H "apikey: $EVOLUTION_KEY" \
      -d "{
        \"url\": \"$WEBHOOK_URL\",
        \"enabled\": true,
        \"events\": [\"MESSAGES_UPSERT\"]
      }")

    echo "   Resposta: $WEBHOOK_RESPONSE"
    echo -e "${GREEN}✅ Webhook configurado${NC}"

elif [[ $REPLY =~ ^[2]$ ]]; then
    # Usar ngrok
    if ! command -v ngrok &> /dev/null; then
        echo -e "${YELLOW}⚠️  ngrok não encontrado. Instale: https://ngrok.com/download${NC}"
        echo ""
        echo "Após instalar, execute manualmente:"
        echo "   ngrok http $BRIDGE_PORT"
        echo ""
        echo "E configure o webhook com a URL gerada"
    else
        echo "   Iniciando ngrok..."
        nohup ngrok http $BRIDGE_PORT > logs/ngrok.log 2>&1 &
        sleep 2

        # Tentar obter URL do ngrok
        NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"[^"]*' | grep -o 'http[^"]*' | head -1)

        if [ -n "$NGROK_URL" ]; then
            echo -e "${GREEN}✅ Ngrok iniciado: $NGROK_URL${NC}"

            WEBHOOK_URL="$NGROK_URL/webhook"

            echo "   Configurando webhook: $WEBHOOK_URL"

            WEBHOOK_RESPONSE=$(curl -s -X POST "$EVOLUTION_URL/webhook/set/$EVOLUTION_INSTANCE" \
              -H "Content-Type: application/json" \
              -H "apikey: $EVOLUTION_KEY" \
              -d "{
                \"url\": \"$WEBHOOK_URL\",
                \"enabled\": true,
                \"events\": [\"MESSAGES_UPSERT\"]
              }")

            echo "   Resposta: $WEBHOOK_RESPONSE"
            echo -e "${GREEN}✅ Webhook configurado com ngrok${NC}"
        else
            echo -e "${RED}❌ Erro ao obter URL do ngrok${NC}"
        fi
    fi

else
    echo -e "${YELLOW}⚠️  Webhook não configurado. Configure manualmente:${NC}"
    echo ""
    echo "curl -X POST \"$EVOLUTION_URL/webhook/set/$EVOLUTION_INSTANCE\" \\"
    echo "  -H \"Content-Type: application/json\" \\"
    echo "  -H \"apikey: $EVOLUTION_KEY\" \\"
    echo "  -d '{"
    echo "    \"url\": \"http://SUA_URL:$BRIDGE_PORT/webhook\","
    echo "    \"enabled\": true,"
    echo "    \"events\": [\"MESSAGES_UPSERT\"]"
    echo "  }'"
    echo ""
fi

echo ""

# ============================================================================
# 8. RESUMO
# ============================================================================

echo "============================================================"
echo "✅ SETUP CONCLUÍDO!"
echo "============================================================"
echo ""
echo "📊 Status:"
echo "   Backend:  http://localhost:8001"
echo "   Grupo:    $GROUP_ID"
echo ""
echo "🎮 Para testar, envie no grupo WhatsApp:"
echo "   INICIAR"
echo ""
echo "📝 Comandos disponíveis:"
echo "   INICIAR    - Começar quiz"
echo "   A/B/C/D    - Responder"
echo "   RANKING    - Ver placar"
echo "   STATUS     - Ver progresso"
echo "   AJUDA      - Mostrar comandos"
echo ""
echo "🐛 Logs:"
echo "   Backend:   tail -f logs/backend.log"
echo ""
echo "🛑 Para parar:"
echo "   pkill -f \"python3 server.py\""
echo ""
echo "============================================================"
