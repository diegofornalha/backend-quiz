# 🎮 Quiz em Grupo - WhatsApp

Modo grupo transforma o quiz em uma experiência **competitiva e colaborativa** onde todos os membros do grupo jogam juntos!

## 🎯 Como Funciona

### 1. Bot Só Funciona em Grupos Autorizados

- ✅ **Grupos na whitelist**: Bot responde e funciona normalmente
- ❌ **Mensagens individuais**: Bot envia aviso e não processa
- ❌ **Grupos não autorizados**: Bot envia mensagem de bloqueio

### 2. Dinâmica do Quiz em Grupo

1. **Um quiz por grupo** (todos veem a mesma pergunta)
2. **Cada pessoa responde individualmente** (A/B/C/D)
3. **Ranking em tempo real** (quem fez mais pontos)
4. **10 perguntas** com pontuação ponderada
5. **Pódio final** com top 3 vencedores

---

## 🚀 Setup Rápido

### 1. Configurar Backend

Mesma configuração do modo individual (ver `WHATSAPP_QUICKSTART.md`):

```bash
# .env
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=quiz-instance
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Adicionar Grupo à Whitelist

**Via API:**

```bash
# Obter ID do grupo (veja logs quando alguém manda mensagem)
# Formato: 123456789@g.us

curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/123456789@g.us
```

**Via Script Python:**

```python
import httpx

group_id = "123456789@g.us"  # ID do seu grupo
response = httpx.post(f"http://localhost:8001/whatsapp/group/whitelist/add/{group_id}")
print(response.json())
```

### 3. Configurar Webhook

```bash
curl -X POST "http://localhost:8080/webhook/set/quiz-instance" \
  -H "Content-Type: application/json" \
  -H "apikey: $EVOLUTION_API_KEY" \
  -d '{
    "url": "https://sua-url.ngrok.io/whatsapp/group/webhook",
    "enabled": true,
    "events": ["MESSAGES_UPSERT"]
  }'
```

**⚠️ IMPORTANTE:** Note o `/group/webhook` no final da URL!

---

## 💬 Comandos do Grupo

### Comandos Principais

| Comando | Função | Disponível em |
|---------|--------|---------------|
| **INICIAR** | Começar novo quiz | Qualquer momento |
| **A / B / C / D** | Responder pergunta | Durante quiz |
| **PROXIMA** | Avançar para próxima pergunta | Após respostas |
| **RANKING** | Ver placar atual | Qualquer momento |
| **STATUS** | Ver progresso do quiz | Durante quiz |
| **PARAR** | Cancelar quiz | Durante quiz |
| **REGULAMENTO** | Link do regulamento | Qualquer momento |
| **AJUDA** | Mostrar comandos | Qualquer momento |

---

## 🎮 Fluxo de Jogo

### 1. Iniciar Quiz

Qualquer membro do grupo pode iniciar:

```
User1: INICIAR

Bot: 🎮 Quiz Iniciado!
User1 iniciou o quiz!
🔥 Preparem-se...
A primeira pergunta vem aí!
```

### 2. Pergunta Aparece

```
❓ Pergunta 1/10
💎 Vale 10 pontos

Como funciona o programa Renda Extra Ton?

A) Opção 1
B) Opção 2
C) Opção 3
D) Opção 4

📱 Responda com: A, B, C ou D
```

### 3. Participantes Respondem

```
User1: A
Bot: ✅ User1 acertou! (+10 pontos)
     📊 1/3 participantes responderam

User2: B
Bot: ❌ User2 errou! (0 pontos)
     📊 2/3 participantes responderam

User3: A
Bot: ✅ User3 acertou! (+10 pontos)
     📊 3/3 participantes responderam
```

### 4. Resultado da Pergunta

```
Qualquer um: PROXIMA

Bot: 📊 Resultado da Pergunta

✔️ Resposta correta: A) Texto da opção

💡 Explicação detalhada...

🎯 2/3 acertaram

✅ Acertaram: User1, User3

⏭️ Digite PROXIMA para continuar
```

### 5. Ranking Atualizado

```
Qualquer um: RANKING

Bot: 🏆 Ranking Atual
Pergunta 1/10

🥇 User1
    🎯 10 pts | ✅ 1/1 (100%)

🥈 User3
    🎯 10 pts | ✅ 1/1 (100%)

🥉 User2
    🎯 0 pts | ✅ 0/1 (0%)
```

### 6. Resultado Final (após 10 perguntas)

```
Bot: 🎊 Quiz Finalizado!

🏆 PÓDIO FINAL

🥇 User1
    🎯 85 pontos
    ✅ 8/10 corretas (80%)

🥈 User3
    🎯 75 pontos
    ✅ 7/10 corretas (70%)

🥉 User2
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

## 🔒 Sistema de Whitelist

### Como Funciona

1. **Grupo autorizado**: Bot funciona normalmente
2. **Grupo não autorizado**: Recebe mensagem de bloqueio
3. **Mensagem individual**: Recebe aviso que bot é só para grupos

### Gerenciar Whitelist

#### Adicionar Grupo

```bash
POST /whatsapp/group/whitelist/add/{group_id}
```

```bash
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/123456789@g.us
```

#### Remover Grupo

```bash
DELETE /whatsapp/group/whitelist/remove/{group_id}
```

```bash
curl -X DELETE http://localhost:8001/whatsapp/group/whitelist/remove/123456789@g.us
```

#### Listar Grupos Autorizados

```bash
GET /whatsapp/group/whitelist
```

```bash
curl http://localhost:8001/whatsapp/group/whitelist
```

**Resposta:**
```json
{
  "total": 2,
  "groups": [
    "123456789@g.us",
    "987654321@g.us"
  ]
}
```

#### Ver Grupos Ativos

```bash
GET /whatsapp/group/active
```

```bash
curl http://localhost:8001/whatsapp/group/active
```

**Resposta:**
```json
{
  "total": 1,
  "groups": [
    {
      "group_id": "123456789@g.us",
      "group_name": "Quiz Group",
      "quiz_id": "abc-123",
      "current_question": 5,
      "participants": 8,
      "state": "active"
    }
  ]
}
```

---

## 🎯 Como Obter o ID do Grupo

### Método 1: Verificar Logs

Quando alguém envia uma mensagem no grupo, o ID aparece nos logs:

```bash
tail -f logs/server.log | grep "Mensagem em"
```

Saída:
```
Mensagem em 123456789@g.us de User1: 'oi' (state: idle)
```

### Método 2: API da Evolution

```bash
curl -X GET "$EVOLUTION_URL/group/fetchAllGroups/$INSTANCE" \
  -H "apikey: $API_KEY"
```

### Método 3: Via Interface Web da Evolution

1. Acesse `http://localhost:8080`
2. Navegue para sua instância
3. Vá em "Grupos"
4. Copie o ID do grupo desejado

---

## 📊 Persistência de Dados

### Estrutura de Arquivos

```
.whatsapp_groups/
├── whitelist.json                 # Lista de grupos autorizados
├── 123456789_at_g.us.json        # Sessão do grupo 1
├── 987654321_at_g.us.json        # Sessão do grupo 2
└── ...
```

### Formato da Sessão de Grupo

```json
{
  "group_id": "123456789@g.us",
  "group_name": "Meu Grupo Quiz",
  "state": "active",
  "quiz_id": "abc-123-def",
  "current_question": 3,
  "questions_history": [
    {
      "question_id": 1,
      "answers": [
        {
          "user_id": "5511999999999",
          "user_name": "João",
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
      "user_name": "João",
      "total_score": 30,
      "correct_answers": 3,
      "total_answers": 3
    }
  }
}
```

---

## 🎨 Personalização

### Modificar Mensagens

Edite `whatsapp/group_formatter.py`:

```python
@staticmethod
def format_welcome() -> str:
    return """🎯 Sua mensagem personalizada aqui!"""
```

### Adicionar Comandos Personalizados

Edite `whatsapp/group_router.py` → função `process_group_message()`:

```python
if text_upper == "MEU_COMANDO":
    await evolution.send_text(group_id, "Resposta do comando!")
    return
```

### Modificar Sistema de Pontuação

Edite `quiz/engine/scoring_engine.py` para mudar pontos por dificuldade.

---

## 🔧 Troubleshooting

### Problema: Bot não responde no grupo

**Verificar:**
1. Grupo está na whitelist?
   ```bash
   curl http://localhost:8001/whatsapp/group/whitelist
   ```

2. Webhook está configurado corretamente?
   ```bash
   curl "$EVOLUTION_URL/webhook/find/$INSTANCE" -H "apikey: $API_KEY"
   ```

3. Backend está rodando?
   ```bash
   curl http://localhost:8001/health
   ```

### Problema: Grupo recebe mensagem de bloqueio

**Causa:** Grupo não está na whitelist.

**Solução:**
```bash
# Obter ID do grupo dos logs
tail -f logs/server.log | grep "não autorizado"

# Adicionar à whitelist
curl -X POST http://localhost:8001/whatsapp/group/whitelist/add/{group_id}
```

### Problema: Mensagem individual é bloqueada

**Comportamento esperado!** Bot funciona apenas em grupos autorizados.

Para habilitar modo individual, use o outro webhook:
```bash
# Webhook modo individual
https://sua-url.ngrok.io/whatsapp/webhook

# Webhook modo grupo
https://sua-url.ngrok.io/whatsapp/group/webhook
```

### Problema: Estado do grupo corrompido

**Reset manual:**
```bash
curl -X POST http://localhost:8001/whatsapp/group/reset/123456789@g.us
```

Ou deletar arquivo:
```bash
rm .whatsapp_groups/123456789_at_g.us.json
```

---

## 🚀 Melhorias Futuras

### 1. Timeout Automático
- Avançar pergunta automaticamente após X segundos
- Evitar quiz travado esperando respostas

### 2. Modo Competição
- Timer por pergunta
- Pontuação extra para respostas rápidas
- Eliminação de participantes

### 3. Estatísticas Avançadas
- Histórico de quizzes por grupo
- Ranking geral de todos os grupos
- Perguntas mais difíceis/fáceis

### 4. Integração com Dashboard
- Interface web para gerenciar grupos
- Visualização de rankings
- Analytics em tempo real

---

## 📋 Resumo de Endpoints

```bash
# Whitelist
POST   /whatsapp/group/whitelist/add/{group_id}
DELETE /whatsapp/group/whitelist/remove/{group_id}
GET    /whatsapp/group/whitelist

# Gestão
GET    /whatsapp/group/active
POST   /whatsapp/group/reset/{group_id}

# Webhook
POST   /whatsapp/group/webhook
```

---

**Diversão garantida! 🎉 O modo grupo transforma o quiz em uma experiência social e competitiva!**
