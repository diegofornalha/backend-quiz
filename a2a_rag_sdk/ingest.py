"""Ingest Engine for RAG - Document ingestion with chunking and embedding"""
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

from .core.config import get_config


class ChunkingStrategy(str, Enum):
    """Estratégias de chunking"""
    FIXED = "fixed"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


@dataclass
class IngestResult:
    """Resultado de ingestão"""
    doc_id: int
    source: str
    chunks: int
    success: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "chunks": self.chunks,
            "success": self.success,
            "error": self.error,
        }


class IngestEngine:
    """Engine de ingestão de documentos"""

    def __init__(
        self,
        db_path: str = None,
        embedding_model: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        """Inicializa ingest engine.

        Args:
            db_path: Caminho do banco SQLite
            embedding_model: Nome do modelo de embedding
            chunk_size: Tamanho do chunk em caracteres
            chunk_overlap: Overlap entre chunks
        """
        config = get_config()
        self.db_path = Path(db_path) if db_path else config.rag_db_path
        self.embedding_model_name = embedding_model or config.embedding_model_string
        self.chunk_size = chunk_size or config.chunk_size
        self.chunk_overlap = chunk_overlap or config.chunk_overlap
        self._embedding_model = None

        # Garantir que diretório existe
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Inicializar banco
        self._init_db()

    def _init_db(self):
        """Inicializa banco de dados com sqlite-vec"""
        try:
            import apsw
            import sqlite_vec

            conn = apsw.Connection(str(self.db_path))
            conn.enableloadextension(True)
            conn.loadextension(sqlite_vec.loadable_path())
            conn.enableloadextension(False)

            cursor = conn.cursor()

            # Tabela de documentos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documentos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    tipo TEXT,
                    conteudo TEXT,
                    caminho TEXT,
                    hash TEXT UNIQUE,
                    metadata TEXT,
                    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabela de embeddings (sqlite-vec)
            # Determinar dimensão do modelo
            dim = self._get_embedding_dimension()
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_documentos USING vec0(
                    doc_id INTEGER PRIMARY KEY,
                    embedding float[{dim}]
                )
            """)

            conn.close()

        except Exception as e:
            print(f"[ERROR] Failed to init DB: {e}")

    def _get_embedding_dimension(self) -> int:
        """Retorna dimensão do modelo de embedding"""
        from .core.config import EmbeddingModel

        for model in EmbeddingModel:
            if model.value == self.embedding_model_name:
                return model.dimensions

        return 768  # Default

    def _get_embedding_model(self):
        """Lazy load embedding model"""
        if self._embedding_model is None:
            from fastembed import TextEmbedding
            self._embedding_model = TextEmbedding(model_name=self.embedding_model_name)
        return self._embedding_model

    def _embed(self, text: str) -> List[float]:
        """Gera embedding para texto"""
        model = self._get_embedding_model()
        embeddings = list(model.embed([text]))
        return embeddings[0].tolist()

    def _chunk_text(self, text: str) -> List[str]:
        """Divide texto em chunks"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Tentar quebrar em espaço
            if end < len(text):
                space_idx = text.rfind(" ", start, end)
                if space_idx > start:
                    end = space_idx

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.chunk_overlap
            if start < 0:
                start = 0

        return chunks

    def _hash_content(self, content: str) -> str:
        """Gera hash do conteúdo"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def ingest_text(
        self,
        content: str,
        source: str,
        doc_type: str = "text",
        metadata: dict = None,
    ) -> IngestResult:
        """Ingere texto no RAG.

        Args:
            content: Conteúdo do documento
            source: Nome/fonte do documento
            doc_type: Tipo do documento
            metadata: Metadados adicionais

        Returns:
            IngestResult com status
        """
        try:
            import apsw
            import sqlite_vec

            content_hash = self._hash_content(content)

            conn = apsw.Connection(str(self.db_path))
            conn.enableloadextension(True)
            conn.loadextension(sqlite_vec.loadable_path())
            conn.enableloadextension(False)

            cursor = conn.cursor()

            # Verificar se já existe
            cursor.execute("SELECT id FROM documentos WHERE hash = ?", [content_hash])
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return IngestResult(
                    doc_id=existing[0],
                    source=source,
                    chunks=0,
                    success=True,
                    error="Document already exists",
                )

            # Inserir documento
            metadata_json = json.dumps(metadata) if metadata else None
            cursor.execute("""
                INSERT INTO documentos (nome, tipo, conteudo, hash, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, [source, doc_type, content, content_hash, metadata_json])

            doc_id = conn.last_insert_rowid()

            # Gerar embedding do conteúdo completo (ou chunked)
            embedding = self._embed(content[:8000])  # Limitar para embedding
            embedding_blob = sqlite_vec.serialize_float32(embedding)

            cursor.execute("""
                INSERT INTO vec_documentos (doc_id, embedding)
                VALUES (?, ?)
            """, [doc_id, embedding_blob])

            conn.close()

            return IngestResult(
                doc_id=doc_id,
                source=source,
                chunks=1,
                success=True,
            )

        except Exception as e:
            return IngestResult(
                doc_id=0,
                source=source,
                chunks=0,
                success=False,
                error=str(e),
            )

    async def ingest_file(
        self,
        file_path: str,
        metadata: dict = None,
    ) -> IngestResult:
        """Ingere arquivo no RAG."""
        path = Path(file_path)

        if not path.exists():
            return IngestResult(
                doc_id=0,
                source=str(path),
                chunks=0,
                success=False,
                error="File not found",
            )

        # Ler conteúdo baseado no tipo
        content = ""
        doc_type = path.suffix.lower().lstrip(".")

        try:
            if doc_type in ["txt", "md", "py", "js", "json", "yaml", "yml"]:
                content = path.read_text(encoding="utf-8")
            elif doc_type == "pdf":
                content = self._extract_pdf(path)
            else:
                content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return IngestResult(
                doc_id=0,
                source=str(path),
                chunks=0,
                success=False,
                error=f"Failed to read file: {e}",
            )

        return await self.ingest_text(
            content=content,
            source=path.name,
            doc_type=doc_type,
            metadata=metadata,
        )

    def _extract_pdf(self, path: Path) -> str:
        """Extrai texto de PDF"""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(path))
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        except ImportError:
            # PyMuPDF não instalado, tentar pdfplumber
            try:
                import pdfplumber

                with pdfplumber.open(str(path)) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() or ""
                return text
            except ImportError:
                raise ImportError("PDF extraction requires PyMuPDF or pdfplumber")

    @property
    def stats(self) -> dict:
        """Retorna estatísticas do banco"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM documentos")
            total_docs = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(LENGTH(conteudo)) FROM documentos")
            total_size = cursor.fetchone()[0] or 0

            conn.close()

            return {
                "total_documents": total_docs,
                "total_embeddings": total_docs,
                "total_size_bytes": total_size,
                "status": "ready" if total_docs > 0 else "empty",
            }
        except Exception as e:
            return {
                "total_documents": 0,
                "total_embeddings": 0,
                "total_size_bytes": 0,
                "status": "error",
                "error": str(e),
            }

    def clear(self):
        """Limpa todo o banco de dados"""
        try:
            import apsw
            import sqlite_vec

            conn = apsw.Connection(str(self.db_path))
            conn.enableloadextension(True)
            conn.loadextension(sqlite_vec.loadable_path())
            conn.enableloadextension(False)

            cursor = conn.cursor()
            cursor.execute("DELETE FROM vec_documentos")
            cursor.execute("DELETE FROM documentos")
            conn.close()

        except Exception as e:
            print(f"[ERROR] Failed to clear DB: {e}")
