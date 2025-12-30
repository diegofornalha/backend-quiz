"""Configuration module for A2A RAG SDK"""
import os
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class EmbeddingModel(str, Enum):
    """Modelos de embedding disponíveis"""
    BGE_SMALL = "BAAI/bge-small-en-v1.5"
    BGE_BASE = "BAAI/bge-base-en-v1.5"
    BGE_LARGE = "BAAI/bge-large-en-v1.5"
    MULTI_E5_LARGE = "intfloat/multilingual-e5-large"
    BERTIMBAU_BASE = "neuralmind/bert-base-portuguese-cased"
    BERTIMBAU_LARGE = "neuralmind/bert-large-portuguese-cased"

    @property
    def short_name(self) -> str:
        """Nome curto para o modelo"""
        mapping = {
            "BAAI/bge-small-en-v1.5": "bge-small",
            "BAAI/bge-base-en-v1.5": "bge-base",
            "BAAI/bge-large-en-v1.5": "bge-large",
            "intfloat/multilingual-e5-large": "multi-e5-large",
            "neuralmind/bert-base-portuguese-cased": "bertimbau-base",
            "neuralmind/bert-large-portuguese-cased": "bertimbau-large",
        }
        return mapping.get(self.value, self.value)

    @property
    def display_name(self) -> str:
        """Nome para exibição"""
        mapping = {
            "BAAI/bge-small-en-v1.5": "BGE Small (EN)",
            "BAAI/bge-base-en-v1.5": "BGE Base (EN)",
            "BAAI/bge-large-en-v1.5": "BGE Large (EN)",
            "intfloat/multilingual-e5-large": "E5 Large Multilingual",
            "neuralmind/bert-base-portuguese-cased": "BERTimbau Base (PT)",
            "neuralmind/bert-large-portuguese-cased": "BERTimbau Large (PT)",
        }
        return mapping.get(self.value, self.value)

    @property
    def language(self) -> str:
        """Idioma principal do modelo"""
        if "multilingual" in self.value or "portuguese" in self.value:
            return "multilingual" if "multilingual" in self.value else "pt-br"
        return "en"

    @property
    def dimensions(self) -> int:
        """Dimensões do embedding"""
        mapping = {
            "BAAI/bge-small-en-v1.5": 384,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-large-en-v1.5": 1024,
            "intfloat/multilingual-e5-large": 1024,
            "neuralmind/bert-base-portuguese-cased": 768,
            "neuralmind/bert-large-portuguese-cased": 1024,
        }
        return mapping.get(self.value, 768)


class RAGConfig(BaseModel):
    """Configuração do RAG"""
    # Paths
    rag_db_path: Path = Path(".agentfs/rag.db")

    # Embedding
    embedding_model: EmbeddingModel = EmbeddingModel.BGE_SMALL

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Search
    top_k: int = 5
    enable_reranking: bool = False

    @property
    def embedding_model_string(self) -> str:
        """Retorna o nome do modelo como string"""
        return self.embedding_model.value


# Singleton config
_config: Optional[RAGConfig] = None


def get_config() -> RAGConfig:
    """Get or create RAG configuration from environment"""
    global _config

    if _config is None:
        _config = _load_config_from_env()

    return _config


def reload_config() -> RAGConfig:
    """Reload configuration from environment"""
    global _config
    _config = _load_config_from_env()
    return _config


def _load_config_from_env() -> RAGConfig:
    """Load configuration from environment variables"""
    # DB Path
    db_path = os.getenv("RAG_DB_PATH", ".agentfs/rag.db")

    # Embedding model
    embedding_model_str = os.getenv("EMBEDDING_MODEL", "bge-small")
    embedding_model = _parse_embedding_model(embedding_model_str)

    # Chunking
    chunk_size = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))

    return RAGConfig(
        rag_db_path=Path(db_path),
        embedding_model=embedding_model,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def _parse_embedding_model(model_str: str) -> EmbeddingModel:
    """Parse embedding model from string"""
    model_str = model_str.lower().strip().strip("'\"")

    mapping = {
        "bge-small": EmbeddingModel.BGE_SMALL,
        "bge-base": EmbeddingModel.BGE_BASE,
        "bge-large": EmbeddingModel.BGE_LARGE,
        "multi-e5-large": EmbeddingModel.MULTI_E5_LARGE,
        "bertimbau-base": EmbeddingModel.BERTIMBAU_BASE,
        "bertimbau-large": EmbeddingModel.BERTIMBAU_LARGE,
    }

    return mapping.get(model_str, EmbeddingModel.BGE_SMALL)
