"""Claude RAG - Minimal stub for document retrieval"""
from typing import Optional, List, Dict, Any
from .options import ClaudeRAGOptions


class ClaudeRAG:
    """Minimal RAG implementation stub"""

    def __init__(self, options: ClaudeRAGOptions):
        self.options = options
        self.documents = []

    @classmethod
    async def open(cls, options: ClaudeRAGOptions) -> "ClaudeRAG":
        """Open a RAG instance"""
        return cls(options)

    async def search(
        self,
        query: str,
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search documents - stub returns empty"""
        return []

    async def ingest_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Ingest text - stub does nothing"""
        pass

    async def ingest_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Ingest file - stub does nothing"""
        pass

    async def get_stats(self) -> Dict[str, Any]:
        """Get RAG stats"""
        return {
            "total_documents": len(self.documents),
            "total_chunks": 0
        }
