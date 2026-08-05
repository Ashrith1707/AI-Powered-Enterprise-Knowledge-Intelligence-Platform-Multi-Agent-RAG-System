"""DB access for chunks and embedding bookkeeping rows."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Chunk, EmbeddingRecord


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def bulk_create(self, document_id: int, chunks: list[dict]) -> list[Chunk]:
        rows = [Chunk(document_id=document_id, **c) for c in chunks]
        self.db.add_all(rows)
        self.db.commit()
        for r in rows:
            self.db.refresh(r)
        return rows

    def get(self, chunk_id: int) -> Chunk | None:
        return self.db.get(Chunk, chunk_id)

    def get_many(self, chunk_ids: list[int]) -> list[Chunk]:
        stmt = select(Chunk).where(Chunk.id.in_(chunk_ids))
        found = {c.id: c for c in self.db.scalars(stmt)}
        return [found[i] for i in chunk_ids if i in found]

    def record_embedding(self, chunk_id: int, faiss_id: str,
                         model_name: str, dimension: int) -> None:
        self.db.add(EmbeddingRecord(chunk_id=chunk_id, faiss_id=faiss_id,
                                    model_name=model_name, dimension=dimension))
        self.db.commit()

    def get_by_index(self, document_id: int, chunk_index: int) -> Chunk | None:
        stmt = select(Chunk).where(Chunk.document_id == document_id,
                                   Chunk.chunk_index == chunk_index)
        return self.db.scalar(stmt)

    def count(self) -> int:
        return self.db.scalar(select(func.count(Chunk.id))) or 0

    def delete_for_document(self, document_id: int) -> None:
        for chunk in self.db.scalars(select(Chunk).where(Chunk.document_id == document_id)):
            self.db.delete(chunk)
        self.db.commit()
