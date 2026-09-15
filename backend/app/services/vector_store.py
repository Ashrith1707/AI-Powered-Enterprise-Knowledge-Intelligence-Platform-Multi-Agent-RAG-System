"""FAISS vector store with persistence + numpy fallback.

* Index: ``IndexFlatIP`` over L2-normalized vectors ⇒ cosine similarity.
* Persistence: ``faiss.write_index`` + a JSON id-map (faiss row → chunk id).
* Thread-safe: a lock guards add/search/remove (FAISS flat indexes are not
  safe for concurrent mutation).
* Filtered search: over-fetch then filter by allowed chunk ids (metadata /
  authorization filtering happens in SQL; the vector layer stays simple).
* If the ``faiss-cpu`` wheel cannot be imported on some platform, a pure
  numpy brute-force index with the same interface is used instead (reported
  via /api/health, never silent).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from app.config import get_settings
from app.core.logging_conf import get_logger

logger = get_logger("vector_store")

try:
    import faiss  # type: ignore

    FAISS_AVAILABLE = True
except Exception:  # pragma: no cover
    faiss = None  # type: ignore
    FAISS_AVAILABLE = False


class VectorSearchResult(Tuple[int, float]):
    pass


class BaseVectorIndex:
    backend = "base"

    def __init__(self, dimensions: int):
        self.dimensions = dimensions
        self._chunk_ids: List[int] = []          # faiss row -> db chunk id
        self._positions: Dict[int, int] = {}     # db chunk id -> row
        self._lock = threading.RLock()

    # -- persistence helpers ------------------------------------------------
    def _meta_path(self, directory: Path) -> Path:
        return directory / "index_meta.json"

    def _save_meta(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "backend": self.backend,
            "dimensions": self.dimensions,
            "chunk_ids": self._chunk_ids,
        }
        self._meta_path(directory).write_text(json.dumps(payload))

    def _load_meta(self, directory: Path) -> bool:
        meta_path = self._meta_path(directory)
        if not meta_path.exists():
            return False
        try:
            payload = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            return False
        if payload.get("dimensions") != self.dimensions or payload.get("backend") != self.backend:
            logger.warning(
                "Vector index meta mismatch (stored: %s/%s, current: %s/%s) — starting fresh index.",
                payload.get("backend"), payload.get("dimensions"), self.backend, self.dimensions,
            )
            return False
        self._chunk_ids = list(payload.get("chunk_ids", []))
        self._positions = {cid: i for i, cid in enumerate(self._chunk_ids)}
        return True

    # -- public API ----------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self._chunk_ids)

    def contains(self, chunk_id: int) -> bool:
        return chunk_id in self._positions

    def search(self, query_vector: np.ndarray, top_k: int,
               allowed_chunk_ids: Optional[Iterable[int]] = None) -> List[Tuple[int, float]]:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class FaissIndex(BaseVectorIndex):
    backend = "faiss"

    def __init__(self, dimensions: int, directory: Optional[Path] = None):
        super().__init__(dimensions)
        self._directory = directory or (get_settings().vector_dir)
        self._index = faiss.IndexFlatIP(dimensions)
        if self._load_meta(self._directory):
            index_path = self._directory / "knowledgeiq.index"
            if index_path.exists():
                try:
                    loaded = faiss.read_index(str(index_path))
                    if loaded.d == dimensions and loaded.ntotal == len(self._chunk_ids):
                        self._index = loaded
                    else:
                        logger.warning("Stored FAISS index shape mismatch — rebuilding empty index.")
                        self._chunk_ids, self._positions = [], {}
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not load FAISS index (%s) — starting fresh.", exc)
                    self._chunk_ids, self._positions = [], {}

    # -- mutation -------------------------------------------------------------
    def add(self, chunk_ids: Sequence[int], vectors: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if vectors.shape[1] != self.dimensions:
            raise ValueError(f"Vector dim {vectors.shape[1]} != index dim {self.dimensions}")
        with self._lock:
            for cid in chunk_ids:
                if cid in self._positions:
                    self._remove_rows([cid], rebuild=False)
            start = self._index.ntotal
            self._index.add(vectors)
            for offset, cid in enumerate(chunk_ids):
                self._chunk_ids.append(cid)
                self._positions[cid] = start + offset
            self._persist()

    def remove(self, chunk_ids: Sequence[int]) -> int:
        with self._lock:
            removed = self._remove_rows(list(chunk_ids), rebuild=True)
            if removed:
                self._persist()
            return removed

    def _remove_rows(self, chunk_ids: List[int], rebuild: bool) -> int:
        rows = sorted(self._positions[c] for c in chunk_ids if c in self._positions)
        if not rows:
            return 0
        keep = np.array([i for i in range(self._index.ntotal) if i not in set(rows)], dtype=np.int64)
        if keep.size:
            vectors = faiss.rev_swig_ptr(self._index.get_xb(), self._index.ntotal * self.dimensions)
            vectors = vectors.reshape(self._index.ntotal, self.dimensions)[keep]
            new_index = faiss.IndexFlatIP(self.dimensions)
            new_index.add(np.ascontiguousarray(vectors, dtype=np.float32))
            self._index = new_index
        else:
            self._index = faiss.IndexFlatIP(self.dimensions)
        new_chunk_ids = [cid for i, cid in enumerate(self._chunk_ids) if i not in set(rows)]
        removed = len(self._chunk_ids) - len(new_chunk_ids)
        self._chunk_ids = new_chunk_ids
        self._positions = {cid: i for i, cid in enumerate(self._chunk_ids)}
        return removed

    def clear(self) -> None:
        with self._lock:
            self._index = faiss.IndexFlatIP(self.dimensions)
            self._chunk_ids, self._positions = [], {}
            self._persist()

    def _persist(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self._directory / "knowledgeiq.index"))
        self._save_meta(self._directory)

    # -- search ----------------------------------------------------------------
    def search(self, query_vector: np.ndarray, top_k: int,
               allowed_chunk_ids: Optional[Iterable[int]] = None) -> List[Tuple[int, float]]:
        with self._lock:
            if self._index.ntotal == 0 or top_k <= 0:
                return []
            allowed = set(allowed_chunk_ids) if allowed_chunk_ids is not None else None
            fetch_k = min(self._index.ntotal, max(top_k * 4, top_k + 16) if allowed else top_k)
            q = np.ascontiguousarray(query_vector.reshape(1, -1), dtype=np.float32)
            scores, idxs = self._index.search(q, fetch_k)
            results: List[Tuple[int, float]] = []
            for score, row in zip(scores[0], idxs[0]):
                if row < 0 or row >= len(self._chunk_ids):
                    continue
                cid = self._chunk_ids[row]
                if allowed is not None and cid not in allowed:
                    continue
                results.append((cid, float(score)))
                if len(results) >= top_k:
                    break
            return results


class NumpyIndex(BaseVectorIndex):
    """Brute-force fallback with identical semantics (cosine via dot product)."""

    backend = "numpy"

    def __init__(self, dimensions: int, directory: Optional[Path] = None):
        super().__init__(dimensions)
        self._directory = directory or (get_settings().vector_dir)
        self._vectors = np.zeros((0, dimensions), dtype=np.float32)
        if self._load_meta(self._directory):
            vec_path = self._directory / "vectors.npy"
            if vec_path.exists():
                try:
                    loaded = np.load(vec_path)
                    if loaded.shape == (len(self._chunk_ids), dimensions):
                        self._vectors = loaded
                    else:
                        self._chunk_ids, self._positions = [], {}
                except Exception:  # noqa: BLE001
                    self._chunk_ids, self._positions = [], {}

    def add(self, chunk_ids: Sequence[int], vectors: np.ndarray) -> None:
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        with self._lock:
            for cid in chunk_ids:
                if cid in self._positions:
                    self.remove([cid])
            start = len(self._chunk_ids)
            self._vectors = np.vstack([self._vectors, vectors]) if self._vectors.size else vectors
            self._chunk_ids.extend(chunk_ids)
            for offset, cid in enumerate(chunk_ids):
                self._positions[cid] = start + offset
            self._persist()

    def remove(self, chunk_ids: Sequence[int]) -> int:
        with self._lock:
            rows = sorted(self._positions[c] for c in chunk_ids if c in self._positions)
            if not rows:
                return 0
            keep = [i for i in range(len(self._chunk_ids)) if i not in set(rows)]
            self._chunk_ids = [self._chunk_ids[i] for i in keep]
            self._positions = {cid: i for i, cid in enumerate(self._chunk_ids)}
            self._vectors = self._vectors[keep] if keep else np.zeros((0, self.dimensions), dtype=np.float32)
            self._persist()
            return len(rows)

    def clear(self) -> None:
        with self._lock:
            self._vectors = np.zeros((0, self.dimensions), dtype=np.float32)
            self._chunk_ids, self._positions = [], {}
            self._persist()

    def _persist(self) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        np.save(self._directory / "vectors.npy", self._vectors)
        self._save_meta(self._directory)

    def search(self, query_vector: np.ndarray, top_k: int,
               allowed_chunk_ids: Optional[Iterable[int]] = None) -> List[Tuple[int, float]]:
        with self._lock:
            if not self._chunk_ids or top_k <= 0:
                return []
            scores = self._vectors @ query_vector.astype(np.float32)
            allowed = set(allowed_chunk_ids) if allowed_chunk_ids is not None else None
            order = np.argsort(-scores)
            results: List[Tuple[int, float]] = []
            for row in order:
                cid = self._chunk_ids[int(row)]
                if allowed is not None and cid not in allowed:
                    continue
                results.append((cid, float(scores[row])))
                if len(results) >= top_k:
                    break
            return results


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------
_store: Optional[BaseVectorIndex] = None
_store_lock = threading.Lock()


def get_vector_store(dimensions: Optional[int] = None) -> BaseVectorIndex:
    global _store
    with _store_lock:
        if _store is None:
            from app.services.embeddings import get_embedding_provider

            dims = dimensions or get_embedding_provider().dimensions
            if FAISS_AVAILABLE:
                _store = FaissIndex(dims)
                logger.info("Vector store ready backend=faiss dims=%d count=%d", dims, _store.count)
            else:  # pragma: no cover
                _store = NumpyIndex(dims)
                logger.warning("FAISS unavailable — using numpy brute-force vector index.")
        return _store


def reset_vector_store() -> None:
    """Test hook — drop the in-memory singleton."""
    global _store
    with _store_lock:
        _store = None


def vector_store_status() -> dict:
    store = get_vector_store()
    return {
        "backend": store.backend,
        "dimensions": store.dimensions,
        "vector_count": store.count,
    }
