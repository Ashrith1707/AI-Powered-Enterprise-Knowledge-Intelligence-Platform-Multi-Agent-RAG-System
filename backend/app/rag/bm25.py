"""Pure-Python BM25 (Okapi) lexical index over all chunks.

Complements dense FAISS retrieval: BM25 wins on exact terms, ids, names and
rare tokens that embeddings blur. The two rankings are fused with RRF in
fusion.py. The index lives in memory, is rebuilt lazily from the DB and is
invalidated whenever chunks change (index/delete/reprocess).
"""
import math
import re
import threading
from collections import Counter

from app.core.logging_config import get_logger

logger = get_logger("bm25")
TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_ids: list[int] = []
        self.doc_tokens: list[list[str]] = []
        self.doc_freq: Counter = Counter()
        self.avg_len = 0.0

    def build(self, docs: list[tuple[int, str]]) -> None:
        """docs: [(chunk_id, text)]"""
        self.doc_ids = [d[0] for d in docs]
        self.doc_tokens = [tokenize(d[1]) for d in docs]
        self.doc_freq = Counter()
        for tokens in self.doc_tokens:
            for term in set(tokens):
                self.doc_freq[term] += 1
        total = sum(len(t) for t in self.doc_tokens)
        self.avg_len = total / len(self.doc_tokens) if self.doc_tokens else 0.0

    def _idf(self, term: str) -> float:
        n = len(self.doc_ids)
        df = self.doc_freq.get(term, 0)
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        if not self.doc_ids:
            return []
        q_terms = tokenize(query)
        scores = [0.0] * len(self.doc_ids)
        for term in q_terms:
            idf = self._idf(term)
            if idf <= 0:
                continue
            for i, tokens in enumerate(self.doc_tokens):
                tf = tokens.count(term)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * len(tokens) / (self.avg_len or 1))
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        ranked = sorted(zip(self.doc_ids, scores), key=lambda x: x[1], reverse=True)
        return [(cid, s) for cid, s in ranked[:top_k] if s > 0]


class ChunkLexicalIndex:
    """App-wide BM25 singleton with lazy rebuild on invalidation."""

    def __init__(self):
        self._index = BM25Index()
        self._dirty = True
        self._lock = threading.Lock()

    def mark_dirty(self) -> None:
        self._dirty = True

    def search(self, db, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        with self._lock:
            if self._dirty:
                from sqlalchemy import select
                from app.models import Chunk
                rows = db.execute(select(Chunk.id, Chunk.text)).all()
                self._index.build([(r[0], r[1]) for r in rows])
                self._dirty = False
                logger.info("BM25 index rebuilt over %d chunks.", len(rows))
            return self._index.search(query, top_k)


lexical_index = ChunkLexicalIndex()
