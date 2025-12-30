"""Options and enums for A2A RAG SDK - Migrado para LiteLLM/Gemini"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AgentModel(str, Enum):
    """LLM model options - Mapeados para Gemini via LiteLLM"""
    # Gemini models (primários)
    FLASH = "gemini/gemini-2.0-flash"
    PRO = "gemini/gemini-1.5-pro"
    FLASH_LITE = "gemini/gemini-1.5-flash"

    # Aliases para compatibilidade com código antigo
    HAIKU = "gemini/gemini-2.0-flash"      # Rápido -> Flash
    SONNET = "gemini/gemini-1.5-pro"       # Balanceado -> Pro
    OPUS = "gemini/gemini-1.5-pro"         # Capaz -> Pro


class ClaudeRAGOptions(BaseModel):
    """Options for RAG agent"""
    id: str
    agent_model: AgentModel = AgentModel.FLASH
    system_prompt: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 1.0
