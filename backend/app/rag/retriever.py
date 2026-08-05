"""Dense retriever: embeds the query and returns scored chunks from FAISS + DB."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag.embeddings import get_embedder
from app.rag.vector_store import get_vector_store
from app.repositories.chunk_repository import ChunkRepository


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    document_name: str
    page_number: int
    text: str
    score: float


class Retriever:
    def __init__(self, db: Session):
        self.db = db
        self.chunks = ChunkRepository(db)

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or settings.retriever_top_k
        query_vec = get_embedder().embed([query])[0]
        hits = get_vector_store().search(query_vec, top_k)
        if not hits:
            return []
        score_by_id = dict(hits)
        chunk_rows = self.chunks.get_many(list(score_by_id.keys()))
        return [
            RetrievedChunk(
                chunk_id=c.id,
                document_id=c.document_id,
                document_name=c.document.filename,
                page_number=c.page_number,
                text=c.text,
                score=score_by_id[c.id],
            )
            for c in chunk_rows
        ]
