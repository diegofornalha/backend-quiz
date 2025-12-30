# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Backend API for a RAG-powered chat system with quiz generation. Built with FastAPI, integrates with Claude Agent SDK and AgentFS for session management and persistence.

## Tech Stack

- **Framework**: FastAPI with Uvicorn
- **AI Integration**: Claude Agent SDK, AgentFS SDK
- **Database**: SQLite with sqlite-vec for vector search
- **Embeddings**: FastEmbed (BAAI/bge-small-en-v1.5)
- **Rate Limiting**: SlowAPI
- **MCP**: FastMCP for Model Context Protocol servers

## Commands

### Run Server
```bash
python server.py                    # Start on port 8001
uvicorn server:app --reload --port 8001  # Development with auto-reload
```

### Document Ingestion
```bash
python scripts/ingest.py <file>            # Ingest single file
python scripts/ingest.py --dir ./docs      # Ingest directory
python scripts/ingest.py --clear           # Clear RAG database first
python scripts/ingest.py --chunk-size 300 --strategy paragraph doc.pdf
```

### RAG Evaluation
```bash
python scripts/evaluate_rag.py
python scripts/evaluate_rag.py --csv path/to/questions.csv
```

### Testing
```bash
pytest                              # Run all tests
pytest tests/test_file.py -v       # Single test file
pytest -k "test_name"              # Run specific test
```

### Linting
```bash
ruff check .                        # Check linting
ruff check . --fix                  # Auto-fix issues
ruff format .                       # Format code
```

## Architecture

### Core Components

- **server.py**: FastAPI app with CORS, rate limiting, exception handlers
- **app_state.py**: Global state management (ClaudeSDKClient, AgentFS, session handling)

### Routers (`routers/`)

| Router | Purpose |
|--------|---------|
| `chat.py` | Chat endpoints with streaming SSE, RAG context injection |
| `rag.py` | Document search and ingestion endpoints |
| `sessions.py` | Session CRUD, favorites, history |
| `quiz.py` | Legacy quiz endpoints (proxies to `quiz/router.py`) |
| `audit.py` | Tool call logs and debugging |
| `artifacts.py` | File artifacts per session |
| `fs.py` | AgentFS filesystem operations |
| `mcp_ingest.py` | MCP-based document ingestion |

### Quiz Module (`quiz/`)

Modular quiz generation system:
- `router.py` - FastAPI endpoints with lazy generation
- `engine/quiz_engine.py` - Main generation orchestrator
- `engine/scoring_engine.py` - Answer evaluation and ranking
- `engine/dedup_engine.py` - Topic deduplication
- `llm/factory.py` - LLM client factory
- `storage/quiz_store.py` - AgentFS persistence
- `models/` - Pydantic schemas and enums
- `prompts/` - Prompt templates

### Agents (`agents/`)

Abstraction layer for AI operations:
- `chat_agent.py` - High-level chat processing with session commands
- `title_generator.py` - Auto-generate session titles
- `evaluator.py` - RAG evaluation agent
- `metrics.py` - Token estimation and cost tracking

### Key Patterns

**Session Flow**:
1. `get_client()` in app_state creates/reuses ClaudeSDKClient
2. AgentFS stores session data (KV store, conversation history)
3. JSONL files persist to `~/.claude/projects/...` for Claude Code compatibility

**RAG Integration**:
- Chat endpoints inject RAG context via `search_rag_context()`
- Context wrapped in `<base_conhecimento>` tags (hidden from user)
- ClaudeRAG uses fixed ID "rag-knowledge-base" for persistence

**Streaming**:
- `/chat/stream` returns SSE with text chunks, session_id, metrics
- StreamChunk dataclass handles serialization

## Configuration

Environment variables in `.env`:
- `ANTHROPIC_API_KEY` - Required for Claude API
- `ENVIRONMENT` - development/production
- `API_KEYS` - Comma-separated valid API keys

MCP servers configured in `~/.mcp.json` are auto-loaded.

## Data Paths

- `.agentfs/` - Session databases (SQLite)
- `artifacts/{session_id}/` - Session file artifacts
- `data/rag_knowledge.db` - RAG vector database
- `~/.claude/projects/.../` - JSONL session transcripts
