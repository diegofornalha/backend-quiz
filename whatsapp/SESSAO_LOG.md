# 📝 LOG DA SESSÃO - Implementação Quiz WhatsApp em Grupo

**Data:** 2025-12-30
**Objetivo:** Criar sistema de quiz interativo para grupo do WhatsApp usando Evolution API

---

## 🎯 Requisitos Iniciais do Usuário

### 1. Solicitação Original
> "eu quero colocar uma interface whatsapp pra eu colocar no evolution api"

- Usuário tinha um quiz HTML funcionando (com interface web)
- Queria adaptar para WhatsApp via Evolution API
- Backend FastAPI já existente com sistema de quiz

### 2. Mudança de Escopo - Modo Grupo
> "eu queria que meu numero só funcionasse em um grupo de whatsapp por exemplo meu numero é o agente ele ele funcionaria no quiz para as pessoas do grupo interagir e responder juntos o que acha dessa ideia acho que assim pode ser divertido"

**Decisão:** Transformar em quiz colaborativo/competitivo para grupos!

**Características desejadas:**
- Bot funciona APENAS em grupos autorizados (whitelist)
- Mensagens individuais são bloqueadas
- Todos veem mesma pergunta
- Cada pessoa responde individualmente
- Ranking em tempo real
- Pódio final com top 3

### 3. Informações Fornecidas

**Dados do Grupo:**
- Nome: "Quiz - Ton"
- ID: `120363422852368877@g.us`

**Evolution API (configuração existente):**
```
URL: http://zp.agentesintegrados.com
API Key: 2392A322B4FF-47D3-B87F-B0B081EDB8C7
Instância: Diego
```

**Bridge A2A Existente:**
- Usuário já tinha um bridge A2A funcionando
- Porta: 4000
- Integrado com LiteLLM
- Rate limiting e cache implementados

---

## 🏗️ Arquitetura Implementada

### Componente 1: Sistema Individual (Original)

**Arquivo:** `whatsapp/router.py`

Funcionalidades:
- Quiz individual por usuário
- Chat de dúvidas contextual
- Estado persistente por usuário
- Comandos: INICIAR, A/B/C/D, DUVIDA, STATUS, PARAR

**Arquivos criados:**
- `whatsapp/__init__.py`
- `whatsapp/models.py` - Schemas Pydantic
- `whatsapp/user_state.py` - Gerenciamento de estado individual
- `whatsapp/evolution_client.py` - Cliente HTTP para Evolution API
- `whatsapp/message_formatter.py` - Formatadores de mensagem
- `whatsapp/router.py` - Endpoints FastAPI

### Componente 2: Sistema de Grupo (Principal)

**Arquivo:** `whatsapp/group_router.py`

Funcionalidades:
- Quiz por grupo com múltiplos participantes
- Whitelist de grupos autorizados
- Ranking em tempo real
- Bloqueio de mensagens individuais
- Persistência de estado do grupo e participantes

**Arquivos criados:**
- `whatsapp/group_models.py` - Modelos para grupo e participantes
- `whatsapp/group_manager.py` - Gerenciador com whitelist
- `whatsapp/group_formatter.py` - Formatadores para grupo
- `whatsapp/group_router.py` - Endpoints FastAPI para grupo

### Componente 3: Bridge A2A Adaptado

**Arquivo:** `whatsapp/a2a_quiz_bridge.py`

Integração com bridge A2A existente:
- Mantém compatibilidade com sistema atual
- Adiciona suporte a grupos
- Encaminha mensagens para backend do quiz
- Sincroniza whitelist automaticamente
- Bloqueia mensagens individuais

---

## 📦 Estrutura de Arquivos Criada

```
backend-quiz/
├── whatsapp/                          # Módulo WhatsApp
│   ├── __init__.py                    # Exports
│   ├── models.py                      # Schemas individual
│   ├── user_state.py                  # Estado individual
│   ├── evolution_client.py            # Cliente Evolution API
│   ├── message_formatter.py           # Formatadores individual
│   ├── router.py                      # Router individual
│   │
│   ├── group_models.py                # Modelos de grupo ⭐
│   ├── group_manager.py               # Gerenciador + whitelist ⭐
│   ├── group_formatter.py             # Formatadores de grupo ⭐
│   ├── group_router.py                # Router de grupo ⭐
│   │
│   ├── a2a_quiz_bridge.py            # Bridge A2A adaptado ⭐
│   │
│   ├── test_whatsapp.py              # Script de testes
│   ├── README.md                      # Documentação individual
│   ├── GROUP_MODE.md                  # Documentação modo grupo ⭐
│   ├── FLOW_DIAGRAM.md                # Diagramas de fluxo
│   ├── TEST_CURL.md                   # Exemplos cURL
│   ├── SETUP_COM_BRIDGE_A2A.md       # Setup com bridge ⭐
│   ├── .env.bridge.example            # Configuração bridge ⭐
│   └── setup_quiz_rapido.sh          # Setup automático ⭐
│
├── .whatsapp_states/                  # Estados individuais
│   └── {user_id}.json
│
├── .whatsapp_groups/                  # Estados de grupos ⭐
│   ├── whitelist.json                 # Grupos autorizados
│   └── {group_id}.json                # Sessão do grupo
│
├── .env.example                       # Configurações gerais
├── WHATSAPP_QUICKSTART.md            # Guia rápido
└── server.py                          # ✅ Atualizado com routers
```

⭐ = Arquivos específicos do modo grupo

---

## 🔧 Modificações no Backend Existente

### server.py

**Antes:**
```python
from whatsapp import router as whatsapp_router
app.include_router(whatsapp_router)
```

**Depois:**
```python
from whatsapp import router as whatsapp_router
from whatsapp.group_router import router as whatsapp_group_router

app.include_router(whatsapp_router)      # Modo individual
app.include_router(whatsapp_group_router) # Modo grupo ⭐
```

---

## ⚙️ Configuração Necessária

### 1. Variáveis de Ambiente (.env)

**Para Backend:**
```bash
# Claude API
ANTHROPIC_API_KEY=sk-ant-sua-chave

# Backend Auth
API_KEYS=dev-key-123
ENVIRONMENT=development

# Evolution API (se usar direto)
EVOLUTION_API_URL=http://zp.agentesintegrados.com
EVOLUTION_API_KEY=2392A322B4FF-47D3-B87F-B0B081EDB8C7
EVOLUTION_INSTANCE=Diego
```

**Para Bridge A2A:**
```bash
# Bridge
BRIDGE_PORT=4000

# Evolution API
EVOLUTION_API_URL=http://zp.agentesintegrados.com
EVOLUTION_API_KEY=2392A322B4FF-47D3-B87F-B0B081EDB8C7
EVOLUTION_INSTANCE_NAME=Diego

# Backend Quiz
QUIZ_BACKEND_URL=http://localhost:8001
QUIZ_GROUP_ID=120363422852368877@g.us
QUIZ_MODE=group

# LiteLLM
LITELLM_MODEL=gemini/gemini-2.0-flash-001
GOOGLE_API_KEY=sua-chave-google

# Rate Limiting
RATE_LIMIT_SECONDS=2
BRIDGE_CACHE_TTL=60
```

### 2. Whitelist de Grupos

**Adicionar grupo autorizado:**
```bash
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/120363422852368877@g.us
```

**Verificar:**
```bash
curl http://localhost:8001/whatsapp/group/whitelist
```

### 3. Ingestão de Documentos (RAG)

```bash
cd /Users/2a/.claude/backend-quiz
python scripts/ingest.py ./docs/regulamento_renda_extra.pdf
```

### 4. Configurar Webhook

**Opção A: Backend Direto**
```bash
curl -X POST "http://zp.agentesintegrados.com/webhook/set/Diego" \
  -H "Content-Type: application/json" \
  -H "apikey: 2392A322B4FF-47D3-B87F-B0B081EDB8C7" \
  -d '{
    "url": "http://SEU_IP:8001/whatsapp/group/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

**Opção B: Via Bridge A2A**
```bash
curl -X POST "http://zp.agentesintegrados.com/webhook/set/Diego" \
  -H "Content-Type: application/json" \
  -H "apikey: 2392A322B4FF-47D3-B87F-B0B081EDB8C7" \
  -d '{
    "url": "http://SEU_IP:4000/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

---

## 🎮 Fluxo do Quiz em Grupo

### 1. Iniciar Quiz

```
Usuário no grupo: INICIAR

Bot responde:
🎮 Quiz Iniciado!
João iniciou o quiz!
🔥 Preparem-se...
A primeira pergunta vem aí!
```

### 2. Pergunta

```
Bot:
❓ Pergunta 1/10
💎 Vale 10 pontos

Como funciona o programa Renda Extra Ton?

A) Opção 1
B) Opção 2
C) Opção 3
D) Opção 4

📱 Responda com: A, B, C ou D
```

### 3. Respostas dos Participantes

```
Maria: A
Bot: ✅ Maria acertou! (+10 pontos)
     📊 1/3 participantes responderam

Pedro: B
Bot: ❌ Pedro errou! (0 pontos)
     📊 2/3 participantes responderam

João: A
Bot: ✅ João acertou! (+10 pontos)
     📊 3/3 participantes responderam
```

### 4. Avançar Pergunta

```
Qualquer um: PROXIMA

Bot:
📊 Resultado da Pergunta

✔️ Resposta correta: A) Texto da opção
💡 Explicação detalhada...
🎯 2/3 acertaram
✅ Acertaram: Maria, João

⏭️ Digite PROXIMA para continuar
```

### 5. Ver Ranking

```
Qualquer um: RANKING

Bot:
🏆 Ranking Atual
Pergunta 1/10

🥇 Maria
    🎯 10 pts | ✅ 1/1 (100%)

🥈 João
    🎯 10 pts | ✅ 1/1 (100%)

🥉 Pedro
    🎯 0 pts | ✅ 0/1 (0%)
```

### 6. Resultado Final (após 10 perguntas)

```
Bot:
🎊 Quiz Finalizado!

🏆 PÓDIO FINAL

🥇 Maria
    🎯 85 pontos
    ✅ 8/10 corretas (80%)

🥈 João
    🎯 75 pontos
    ✅ 7/10 corretas (70%)

🥉 Pedro
    🎯 50 pontos
    ✅ 5/10 corretas (50%)

📊 Estatísticas:
👥 3 participantes
📈 Média: 70 pontos
🏆 Melhor: 85 pontos

🎯 Quer jogar novamente?
Digite INICIAR para um novo quiz!
```

---

## 📝 Comandos Disponíveis no Grupo

| Comando | Função | Exemplo |
|---------|--------|---------|
| `INICIAR` | Começar novo quiz | João: INICIAR |
| `A` / `B` / `C` / `D` | Responder pergunta | Maria: A |
| `RANKING` | Ver placar atual | Pedro: RANKING |
| `STATUS` | Ver progresso do quiz | João: STATUS |
| `PROXIMA` | Avançar para próxima pergunta | Maria: PROXIMA |
| `PARAR` | Cancelar quiz | Pedro: PARAR |
| `REGULAMENTO` | Link do regulamento | João: REGULAMENTO |
| `AJUDA` | Mostrar comandos | Maria: AJUDA |

---

## 🔒 Sistema de Segurança

### Whitelist de Grupos

**Comportamento:**
- ✅ **Grupo autorizado:** Bot funciona normalmente
- ❌ **Grupo não autorizado:** Recebe mensagem de bloqueio
- ❌ **Mensagem individual:** Recebe aviso que bot é só para grupos

**Gerenciamento:**

```bash
# Adicionar grupo
POST /whatsapp/group/whitelist/add/{group_id}

# Remover grupo
DELETE /whatsapp/group/whitelist/remove/{group_id}

# Listar grupos autorizados
GET /whatsapp/group/whitelist

# Ver grupos com quiz ativo
GET /whatsapp/group/active

# Resetar sessão de grupo
POST /whatsapp/group/reset/{group_id}
```

---

## 📊 Persistência de Dados

### Estrutura de Arquivos

```
.whatsapp_groups/
├── whitelist.json                    # Lista de grupos autorizados
├── 120363422852368877_at_g.us.json  # Sessão do grupo
└── ...
```

### Formato da Sessão

```json
{
  "group_id": "120363422852368877@g.us",
  "group_name": "Quiz - Ton",
  "state": "active",
  "quiz_id": "abc-123-def",
  "current_question": 3,
  "questions_history": [
    {
      "question_id": 1,
      "answers": [
        {
          "user_id": "5511999999999",
          "user_name": "Maria",
          "answer_index": 0,
          "is_correct": true,
          "points_earned": 10
        }
      ]
    }
  ],
  "participants": {
    "5511999999999": {
      "user_id": "5511999999999",
      "user_name": "Maria",
      "total_score": 30,
      "correct_answers": 3,
      "total_answers": 3
    }
  }
}
```

---

## 🚀 Setup - Opções de Implementação

### Opção 1: Usar Bridge A2A (Recomendado)

**Vantagens:**
- ✅ Mantém compatibilidade com sistema atual
- ✅ Preserva rate limiting e cache
- ✅ Não quebra funcionalidades existentes

**Passos:**
1. Copiar `a2a_quiz_bridge.py` para diretório do bridge atual
2. Atualizar `.env` com variáveis do quiz
3. Iniciar bridge adaptado
4. Backend processa em background

**Webhook:** `http://SEU_IP:4000/webhook`

### Opção 2: Backend Direto

**Vantagens:**
- ✅ Mais simples
- ✅ Menos componentes
- ✅ Mais fácil debugar

**Passos:**
1. Configurar webhook direto para backend
2. Backend recebe e processa diretamente

**Webhook:** `http://SEU_IP:8001/whatsapp/group/webhook`

### Opção 3: Setup Automático

**Script:** `setup_quiz_rapido.sh`

```bash
cd /Users/2a/.claude/backend-quiz/whatsapp
./setup_quiz_rapido.sh
```

Faz tudo automaticamente:
- Verifica dependências
- Inicia backend
- Adiciona grupo à whitelist
- Oferece configurar webhook

---

## 🧪 Testes Realizados

### Testes Criados

1. **test_whatsapp.py** - Script de teste interativo
   - Teste de conexão Evolution API
   - Teste de envio de mensagem
   - Teste de formatadores
   - Teste de webhook

2. **TEST_CURL.md** - Exemplos de comandos cURL
   - Todos os endpoints documentados
   - Scripts de teste automatizado
   - Debug de problemas comuns

3. **test_grupo.sh** - Teste automático do grupo
   - Verifica backend
   - Verifica whitelist
   - Simula webhook local
   - Valida configuração

---

## 📚 Documentação Criada

### Guias Principais

1. **WHATSAPP_QUICKSTART.md**
   - Setup em 5 minutos
   - Para modo individual

2. **GROUP_MODE.md** ⭐
   - Documentação completa modo grupo
   - Como funciona whitelist
   - Comandos e fluxo
   - Troubleshooting

3. **SETUP_COM_BRIDGE_A2A.md** ⭐
   - Integração com bridge existente
   - Passo a passo detalhado
   - Comandos úteis

4. **FLOW_DIAGRAM.md**
   - Diagramas de arquitetura
   - Fluxo de estados
   - Fluxo de mensagens

5. **README.md**
   - Visão geral do sistema
   - Arquitetura
   - Desenvolvimento

---

## ✅ Status Atual

### Implementado

- ✅ Sistema individual completo
- ✅ Sistema de grupo completo
- ✅ Whitelist de grupos
- ✅ Bridge A2A adaptado
- ✅ Formatadores de mensagem
- ✅ Persistência de dados
- ✅ Sistema de ranking
- ✅ Documentação completa
- ✅ Scripts de teste
- ✅ Setup automático

### Testado Localmente

- ✅ Modelos e schemas
- ✅ Formatadores de mensagem
- ✅ Estrutura de arquivos
- ⏳ Integração com Evolution API (aguardando teste real)
- ⏳ Funcionamento em grupo real (aguardando teste)

### Pendente

- ⏳ Ingerir documentos no RAG
- ⏳ Configurar webhook na Evolution API
- ⏳ Testar no grupo real "Quiz - Ton"
- ⏳ Ajustes finais baseados em feedback real

---

## 🎯 Próximos Passos

### Imediato (Antes de Testar)

1. **Iniciar backend:**
   ```bash
   cd /Users/2a/.claude/backend-quiz
   python server.py
   ```

2. **Adicionar grupo à whitelist:**
   ```bash
   curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/120363422852368877@g.us
   ```

3. **Ingerir documentos:**
   ```bash
   python scripts/ingest.py ./docs/regulamento.pdf
   ```

4. **Configurar webhook** (escolher opção A ou B)

5. **Testar no grupo:**
   - Enviar "oi" no grupo
   - Se funcionar, enviar "INICIAR"

### Após Primeiro Teste

1. **Coletar feedback:**
   - Mensagens estão claras?
   - Comandos intuitivos?
   - Performance adequada?

2. **Ajustes de UX:**
   - Modificar formatadores se necessário
   - Ajustar timing de respostas
   - Melhorar mensagens

3. **Otimizações:**
   - Implementar timeout automático para perguntas
   - Adicionar mais comandos se necessário
   - Melhorar sistema de ranking

---

## 💡 Melhorias Futuras Sugeridas

### Curto Prazo

1. **Timeout Automático**
   - Avançar pergunta após X segundos
   - Evitar quiz travado

2. **Notificações**
   - Lembrar participantes de responder
   - Avisar quando pergunta vai avançar

3. **Estatísticas**
   - Histórico de quizzes por grupo
   - Perguntas mais difíceis/fáceis
   - Tempo médio de resposta

### Médio Prazo

1. **Modo Competição**
   - Timer por pergunta
   - Pontuação extra para velocidade
   - Eliminação de participantes

2. **Dashboard Web**
   - Interface para gerenciar grupos
   - Visualizar rankings
   - Analytics em tempo real

3. **Múltiplos Quizzes**
   - Diferentes temas
   - Dificuldades variadas
   - Quiz personalizado

### Longo Prazo

1. **Sistema de Conquistas**
   - Badges para participantes
   - Ranking global
   - Níveis de experiência

2. **Integração com APIs**
   - Google Sheets para rankings
   - Certificados automáticos
   - Relatórios por email

3. **IA Avançada**
   - Geração de perguntas automática
   - Adaptação de dificuldade
   - Explicações personalizadas

---

## 🐛 Problemas Conhecidos e Soluções

### 1. Webhook não recebe mensagens

**Sintomas:**
- Mensagens no grupo não chegam no backend
- Logs não mostram atividade

**Debug:**
```bash
# Verificar webhook configurado
curl -X GET "http://zp.agentesintegrados.com/webhook/find/Diego" \
  -H "apikey: 2392A322B4FF-47D3-B87F-B0B081EDB8C7"

# Testar endpoint local
curl -X POST http://localhost:8001/whatsapp/group/webhook \
  -H "Content-Type: application/json" \
  -d '{...}'  # Payload de teste
```

**Soluções:**
- Verificar URL pública acessível
- Usar ngrok se necessário
- Reconfigurar webhook

### 2. Grupo recebe mensagem de bloqueio

**Sintomas:**
- "Grupo Não Autorizado"

**Solução:**
```bash
# Verificar whitelist
curl http://localhost:8001/whatsapp/group/whitelist

# Adicionar grupo
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/120363422852368877@g.us
```

### 3. RAG vazio

**Sintomas:**
- "Nenhum documento encontrado no RAG"

**Solução:**
```bash
# Ingerir documentos
python scripts/ingest.py ./docs/regulamento.pdf

# Verificar
curl http://localhost:8001/rag/stats
```

### 4. Estado corrompido

**Sintomas:**
- Quiz travado
- Respostas não processam

**Solução:**
```bash
# Reset do grupo
curl -X POST http://localhost:8001/whatsapp/group/reset/120363422852368877@g.us

# Ou deletar arquivo
rm .whatsapp_groups/120363422852368877_at_g.us.json
```

---

## 📞 Informações de Contato/Suporte

### Arquivos de Log

```bash
# Backend
tail -f logs/backend.log

# Bridge (se usar)
tail -f logs/a2a_quiz_bridge.log

# Evolution API
docker logs -f evolution-api  # Se usar Docker
```

### Endpoints de Debug

```bash
# Health checks
curl http://localhost:8001/health
curl http://localhost:4000/health  # Se usar bridge

# Status do sistema
curl http://localhost:8001/whatsapp/group/active
curl http://localhost:8001/whatsapp/group/whitelist
```

### Comandos Úteis

```bash
# Ver processos
ps aux | grep python

# Matar processos
pkill -f "python server.py"
pkill -f "python bridge"

# Limpar estados
rm -rf .whatsapp_groups/*.json
rm -rf .whatsapp_states/*.json
```

---

## 🎓 Lições Aprendidas

### Decisões de Design

1. **Separar modo individual e grupo**
   - Permite usar ambos simultaneamente
   - Mantém código organizado
   - Facilita manutenção

2. **Whitelist de grupos**
   - Controle total sobre onde bot funciona
   - Segurança e privacidade
   - Evita uso indevido

3. **Persistência em disco**
   - Sobrevive a reinicializações
   - Não depende de banco de dados
   - Fácil backup e recuperação

4. **Bridge A2A opcional**
   - Flexibilidade de implementação
   - Compatibilidade com sistema existente
   - Não força mudanças drásticas

### Desafios Superados

1. **Gerenciamento de estado por grupo**
   - Múltiplos participantes
   - Sincronização de respostas
   - Ranking em tempo real

2. **Evitar loops de mensagens**
   - Cache de mensagens enviadas
   - Verificação de fromMe
   - Deduplicação

3. **Rate limiting em grupo**
   - Lock por grupo
   - Cooldown entre mensagens
   - Prevenção de spam

---

## 📊 Métricas e KPIs (Para Futuro)

### Métricas Sugeridas

1. **Engajamento**
   - Número de quizzes iniciados
   - Taxa de conclusão (10/10 perguntas)
   - Participantes por quiz

2. **Performance**
   - Tempo de resposta do bot
   - Taxa de erro
   - Uptime do sistema

3. **Qualidade**
   - Percentual de acerto médio
   - Perguntas mais difíceis
   - Feedback dos usuários

4. **Uso**
   - Grupos ativos
   - Quizzes por dia
   - Horários de pico

---

## 🎉 Conclusão

### Resumo do Trabalho

**Implementado:**
- Sistema completo de quiz para grupos WhatsApp
- Integração com Evolution API
- Whitelist de segurança
- Bridge A2A adaptado
- Documentação extensiva
- Scripts de automação

**Pronto para:**
- Testes reais no grupo "Quiz - Ton"
- Ajustes baseados em feedback
- Expansão para outros grupos

**Próximo Marco:**
- Primeiro teste real no grupo
- Validação da experiência do usuário
- Iteração e melhorias

---

**🚀 Sistema pronto para ser testado!**

**Status:** Aguardando teste real no grupo do WhatsApp

**Última atualização:** 2025-12-30

---

## 📝 Notas Finais

Este log documenta toda a sessão de desenvolvimento e pode ser usado como:
- Referência para retomar o trabalho
- Documentação do que foi feito
- Guia para troubleshooting
- Base para futuras melhorias

**Mantenha este arquivo atualizado conforme o projeto evolui!**
