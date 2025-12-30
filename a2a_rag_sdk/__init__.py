"""A2A RAG SDK - RAG with A2A protocol and LiteLLM"""

__version__ = "0.1.0"

# Core exports
from .rag import ClaudeRAG
from .options import ClaudeRAGOptions, AgentModel
from .agent import AgentEngine

# Search & Ingest
from .search import SearchEngine, SearchResult
from .ingest import IngestEngine, IngestResult, ChunkingStrategy

# Core utilities
from .core import (
    get_config,
    reload_config,
    get_guest_limit_manager,
    get_hooks_manager,
    get_audit_database,
    AuditEventType,
)

__all__ = [
    # Main classes
    "ClaudeRAG",
    "ClaudeRAGOptions",
    "AgentModel",
    "AgentEngine",
    # Search
    "SearchEngine",
    "SearchResult",
    # Ingest
    "IngestEngine",
    "IngestResult",
    "ChunkingStrategy",
    # Core utilities
    "get_config",
    "reload_config",
    "get_guest_limit_manager",
    "get_hooks_manager",
    "get_audit_database",
    "AuditEventType",
]
