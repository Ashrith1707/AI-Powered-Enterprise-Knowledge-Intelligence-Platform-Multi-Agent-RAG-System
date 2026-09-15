"""Lightweight in-memory BM25 (Okapi) keyword index.

Implemented directly (no external ranking dependency) so keyword retrieval is
deterministic, fast and testable. The index is rebuilt lazily from the DB
whenever documents are added/removed.
"""
from __future__ import annotations

import math
import threading
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from app.services.embeddings import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunk_ids: List[int] = []
        self._doc_freqs: Dict[str, int] = {}
        self._term_freqs: List[Counter] = []
        self._doc_lens: List[int] = []
        self._avg_len: float = 0.0
        self._positions: Dict[int, int] = {}
        self._lock = threading.RLock()
        self._generation: int = 0

    # ------------------------------------------------------------------ build
    def build(self, corpus: Sequence[Tuple[int, str]]) -> None:
        """corpus: sequence of (chunk_id, text)."""
        with self._lock:
            self._chunk_ids = []
            self._term_freqs = []
            self._doc_lens = []
            self._positions = {}
            df: Counter = Counter()
            for cid, text in corpus:
                tokens = tokenize(text)
                tf = Counter(tokens)
                self._chunk_ids.append(cid)
                self._term_freqs.append(tf)
                self._doc_lens.append(len(tokens))
                self._positions[cid] = len(self._chunk_ids) - 1
                df.update(tf.keys())
            self._doc_freqs = dict(df)
            self._avg_len = (sum(self._doc_lens) / len(self._doc_lens)) if self._doc_lens else 0.0
            self._generation += 1

    def upsert(self, chunk_id: int, text: str) -> None:
        """Add/replace a single chunk (used after each document ingestion)."""
        with self._lock:
            if chunk_id in self._positions:
                self.remove([chunk_id])
            tokens = tokenize(text)
            tf = Counter(tokens)
            self._chunk_ids.append(chunk_id)
            self._term_freqs.append(tf)
            self._doc_lens.append(len(tokens))
            self._positions[chunk_id] = len(self._chunk_ids) - 1
            for term in tf:
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1
            total = sum(self._doc_lens)
            self._avg_len = total / len(self._doc_lens) if self._doc_lens else 0.0
            self._generation += 1

    def remove(self, chunk_ids: Sequence[int]) -> None:
        with self._lock:
            rows = sorted((self._positions[c] for c in chunk_ids if c in self._positions), reverse=True)
            for row in rows:
                tf = self._term_freqs.pop(row)
                for term in tf:
                    self._doc_freqs[term] = max(0, self._doc_freqs.get(term, 1) - 1)
                    if self._doc_freqs[term] == 0:
                        del self._doc_freqs[term]
                self._chunk_ids.pop(row)
                self._doc_lens.pop(row)
            self._positions = {cid: i for i, cid in enumerate(self._chunk_ids)}
            self._avg_len = (sum(self._doc_lens) / len(self._doc_lens)) if self._doc_lens else 0.0
            self._generation += 1

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def size(self) -> int:
        return len(self._chunk_ids)

    # ----------------------------------------------------------------- search
    def search(
        self,
        query: str,
        top_k: int,
        allowed_chunk_ids: Optional[set[int]] = None,
    ) -> List[Tuple[int, float]]:
        with self._lock:
            if not self._chunk_ids or top_k <= 0:
                return []
            query_tokens = tokenize(query)
            if not query_tokens:
                return []
            n = len(self._chunk_ids)
            scores: Dict[int, float] = {}
            for term in set(query_tokens):
                df = self._doc_freqs.get(term, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                for pos, tf_map in enumerate(self._term_freqs):
                    tf = tf_map.get(term, 0)
                    if tf == 0:
                        continue
                    cid = self._chunk_ids[pos]
                    if allowed_chunk_ids is not None and cid not in allowed_chunk_ids:
                        continue
                    dl = self._doc_lens[pos]
                    denom = tf + self.k1 * (1 - self.b + self.b * (dl / (self._avg_len or 1.0)))
                    scores[cid] = scores.get(cid, 0.0) + idf * (tf * (self.k1 + 1)) / denom
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            return ranked[:top_k]


# ---------------------------------------------------------------------------
# Singleton + DB sync
# ---------------------------------------------------------------------------
_index: Optional[BM25Index] = None
_index_lock = threading.Lock()
_index_generation_source: int = -1


def get_bm25_index() -> BM25Index:
    global _index
    with _index_lock:
        if _index is None:
            _index = BM25Index()
        return _index


def ensure_bm25_loaded(session) -> BM25Index:
    """Rebuild the BM25 corpus from the DB if it has never been loaded."""
    global _index_generation_source
    index = get_bm25_index()
    with _index_lock:
        if _index_generation_source != index.generation or index.size == 0:
            from app.models import DocumentChunk

            rows = session.query(DocumentChunk.id, DocumentChunk.content).yield_per(500).all()
            if rows or index.size == 0:
                index.build([(cid, content) for cid, content in rows])
                _index_generation_source = index.generation
    return index


def reset_bm25_for_tests() -> None:
    global _index, _index_generation_source
    with _index_lock:
        _index = None
        _index_generation_source = -1
