"""Search Engine for RAG using fastembed + sqlite-vec"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .core.config import get_config


@dataclass
class SearchResult:
    """Resultado de busca"""
    doc_id: int
    source: str
    content: str
    similarity: float
    metadata: dict = None

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "content": self.content,
            "similarity": self.similarity,
            "metadata": self.metadata or {},
        }


class SearchEngine:
    """Engine de busca vetorial usando fastembed + sqlite-vec"""

    def __init__(
        self,
        db_path: str = None,
        embedding_model: str = None,
        enable_reranking: bool = False,
    ):
        """Inicializa search engine.

        Args:
            db_path: Caminho do banco SQLite com sqlite-vec
            embedding_model: Nome do modelo de embedding
            enable_reranking: Habilitar reranking (requer sentence-transformers)
        """
        config = get_config()
        self.db_path = Path(db_path) if db_path else config.rag_db_path
        self.embedding_model_name = embedding_model or config.embedding_model_string
        self.enable_reranking = enable_reranking
        self._embedding_model = None

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

    async def search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> List[SearchResult]:
        """Busca documentos similares.

        Args:
            query: Texto de busca
            top_k: Número de resultados
            min_similarity: Similaridade mínima

        Returns:
            Lista de SearchResult ordenados por similaridade
        """
        if not self.db_path.exists():
            return []

        try:
            import apsw
            import sqlite_vec

            # Gerar embedding da query
            query_embedding = self._embed(query)

            # Conectar ao banco
            conn = apsw.Connection(str(self.db_path))
            conn.enableloadextension(True)
            conn.loadextension(sqlite_vec.loadable_path())
            conn.enableloadextension(False)

            cursor = conn.cursor()

            # Buscar usando sqlite-vec
            # Formato: vec_distance_cosine(embedding, query_vec)
            embedding_blob = sqlite_vec.serialize_float32(query_embedding)

            cursor.execute("""
                SELECT
                    d.id,
                    d.nome as source,
                    d.conteudo as content,
                    d.metadata,
                    vec_distance_cosine(v.embedding, ?) as distance
                FROM vec_documentos v
                JOIN documentos d ON v.doc_id = d.id
                ORDER BY distance ASC
                LIMIT ?
            """, [embedding_blob, top_k])

            results = []
            for row in cursor.fetchall():
                doc_id, source, content, metadata_str, distance = row

                # Converter distância para similaridade (1 - distance para cosine)
                similarity = 1.0 - distance

                if similarity < min_similarity:
                    continue

                # Parse metadata
                metadata = {}
                if metadata_str:
                    try:
                        import json
                        metadata = json.loads(metadata_str)
                    except:
                        pass

                results.append(SearchResult(
                    doc_id=doc_id,
                    source=source,
                    content=content,
                    similarity=similarity,
                    metadata=metadata,
                ))

            conn.close()

            # Reranking opcional
            if self.enable_reranking and results:
                results = self._rerank(query, results)

            return results

        except Exception as e:
            print(f"[ERROR] Search failed: {e}")
            return []

    def _rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Rerank results usando cross-encoder"""
        try:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

            pairs = [(query, r.content) for r in results]
            scores = model.predict(pairs)

            for i, score in enumerate(scores):
                results[i].similarity = float(score)

            results.sort(key=lambda x: x.similarity, reverse=True)
            return results

        except ImportError:
            # sentence-transformers não instalado
            return results
        except Exception as e:
            print(f"[WARN] Reranking failed: {e}")
            return results
