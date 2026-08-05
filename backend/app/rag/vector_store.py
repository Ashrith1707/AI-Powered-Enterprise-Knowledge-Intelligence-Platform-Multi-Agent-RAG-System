"""FAISS index wrapper persisted to disk.

Stores normalized vectors in an IndexIDMap over IndexFlatIP so inner
product == cosine similarity, and FAISS ids == chunk DB ids, which makes
mapping hits back to citations trivial.
"""
import json
import threading
from pathlib import Path

import faiss
import numpy as np

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger("vector_store")
_lock = threading.Lock()


class VectorStore:
    def __init__(self, dimension: int):
        self.dimension = dimension
        self.index_path = settings.vector_index_dir / "chunks.faiss"
        self.meta_path = settings.vector_index_dir / "meta.json"
        self.index = self._load_or_create()

    def _load_or_create(self) -> faiss.IndexIDMap:
        if self.index_path.exists() and self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text())
            if meta.get("dimension") == self.dimension:
                index = faiss.read_index(str(self.index_path))
                logger.info("Loaded FAISS index with %d vectors.", index.ntotal)
                return index
            logger.warning("Embedding dimension changed — rebuilding empty index.")
        return faiss.IndexIDMap(faiss.IndexFlatIP(self.dimension))

    def add(self, chunk_ids: list[int], vectors: np.ndarray) -> None:
        with _lock:
            self.index.add_with_ids(vectors, np.array(chunk_ids, dtype="int64"))
            self._persist()

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        if self.index.ntotal == 0:
            return []
        scores, ids = self.index.search(query_vector.reshape(1, -1), min(top_k, self.index.ntotal))
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]

    def remove(self, chunk_ids: list[int]) -> None:
        with _lock:
            self.index.remove_ids(np.array(chunk_ids, dtype="int64"))
            self._persist()

    def _persist(self) -> None:
        faiss.write_index(self.index, str(self.index_path))
        self.meta_path.write_text(json.dumps({"dimension": self.dimension}))

    @property
    def size(self) -> int:
        return self.index.ntotal


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        from app.rag.embeddings import get_embedder
        _store = VectorStore(dimension=get_embedder().dimension)
    return _store
