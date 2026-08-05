"""Advanced retrieval pipeline (Module 5):

  query analysis -> (history rewrite) -> (LLM multi-query / HyDE, gated)
  -> dense FAISS + BM25 -> Reciprocal Rank Fusion -> metadata filter
  -> dedup -> adaptive selection -> neighbor stitching -> compression

Returns the selected chunks plus a full report of what each stage did, so
the streaming endpoint can emit REAL stage events.
"""
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.rag import query_processing as qp
from app.rag.bm25 import lexical_index
from app.rag.embeddings import get_embedder
from app.rag.fusion import (adaptive_select, channel_weights, compress_chunk,
                            deduplicate, evidence_sufficient,
                            reciprocal_rank_fusion, retrieval_quality)
from app.rag.retriever import RetrievedChunk
from app.rag.vector_store import get_vector_store
from app.repositories.chunk_repository import ChunkRepository


@dataclass
class RetrievalReport:
    query_used: str = ""
    query_type: str = "factual"
    expansions: list = field(default_factory=list)
    hyde_used: bool = False
    dense_candidates: int = 0
    bm25_candidates: int = 0
    fused: int = 0
    after_dedup: int = 0
    selected: int = 0
    compressed_chars_saved: int = 0
    quality: dict = field(default_factory=dict)
    sufficient: bool = True
    timings_ms: dict = field(default_factory=dict)


class AdvancedRetriever:
    def __init__(self, db: Session):
        self.db = db
        self.chunks = ChunkRepository(db)

    def _dense_ranking(self, queries: list[str], top_k: int) -> list[int]:
        """Multi-query dense retrieval: RRF-merge the per-query rankings."""
        embedder = get_embedder()
        store = get_vector_store()
        per_query = []
        for q in queries:
            vec = embedder.embed([q])[0]
            hits = store.search(vec, top_k)
            per_query.append([cid for cid, _ in hits])
        if len(per_query) == 1:
            return per_query[0]
        fused = reciprocal_rank_fusion(per_query)
        return [cid for cid, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]

    def retrieve(self, question: str, prior_user_messages: list[str] | None = None,
                 category: str | None = None,
                 top_k: int | None = None) -> tuple[list[RetrievedChunk], RetrievalReport]:
        report = RetrievalReport()
        top_k = top_k or settings.retriever_top_k
        t0 = time.perf_counter()

        # ---- 1. query understanding ----
        analysis = qp.analyze(question)
        report.query_type = analysis["type"]
        query = qp.history_aware_query(question, prior_user_messages or [])
        report.query_used = query

        dense_queries = [query]
        expansions = qp.llm_expansions(question)
        if expansions:
            report.expansions = expansions
            dense_queries += expansions
        hyde = qp.hyde_document(question)
        if hyde:
            report.hyde_used = True
            dense_queries.append(hyde)
        report.timings_ms["planner"] = round((time.perf_counter() - t0) * 1000, 1)

        # ---- 2. dense + lexical retrieval ----
        t1 = time.perf_counter()
        dense_ids = self._dense_ranking(dense_queries, top_k)
        report.dense_candidates = len(dense_ids)
        bm25_hits = lexical_index.search(self.db, query, top_k)
        bm25_ids = [cid for cid, _ in bm25_hits]
        report.bm25_candidates = len(bm25_ids)
        report.timings_ms["retrieval"] = round((time.perf_counter() - t1) * 1000, 1)

        # ---- 3. weighted reciprocal rank fusion ----
        t2 = time.perf_counter()
        dense_w, lex_w = channel_weights(get_embedder())
        fused = reciprocal_rank_fusion(
            [dense_ids, bm25_ids] if bm25_ids else [dense_ids],
            weights=[dense_w, lex_w] if bm25_ids else [dense_w])
        ranked_ids = [cid for cid, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)]
        report.fused = len(ranked_ids)

        rows = self.chunks.get_many(ranked_ids)
        chunk_list = [
            RetrievedChunk(
                chunk_id=c.id, document_id=c.document_id,
                document_name=c.document.filename, page_number=c.page_number,
                text=c.text, score=round(fused[c.id] * 30, 4),  # scaled fused score
            )
            for c in rows
        ]

        # ---- 4. metadata-aware filtering ----
        if category:
            by_id = {c.id: c for c in rows}
            chunk_list = [ch for ch in chunk_list
                          if by_id[ch.chunk_id].document.category == category]

        # ---- 5. dedup + adaptive selection ----
        chunk_list = deduplicate(chunk_list)
        report.after_dedup = len(chunk_list)
        selected = adaptive_select(chunk_list)
        report.selected = len(selected)

        # ---- 6. parent-child: stitch neighbouring chunks onto the top hits ----
        for chunk in selected[:2]:
            anchor = next((r for r in rows if r.id == chunk.chunk_id), None)
            if anchor is None:
                continue
            for offset in (-1, 1):
                neighbor = self.chunks.get_by_index(anchor.document_id,
                                                    anchor.chunk_index + offset)
                if neighbor and neighbor.id not in {c.chunk_id for c in selected}:
                    if offset < 0:
                        chunk.text = neighbor.text[-400:] + "\n…\n" + chunk.text
                    else:
                        chunk.text = chunk.text + "\n…\n" + neighbor.text[:400]

        # ---- 7. context compression ----
        saved = 0
        for chunk in selected:
            before = len(chunk.text)
            chunk.text = compress_chunk(chunk.text, query)
            saved += before - len(chunk.text)
        report.compressed_chars_saved = saved
        report.timings_ms["fusion_selection"] = round((time.perf_counter() - t2) * 1000, 1)

        # ---- 8. quality + sufficiency ----
        report.quality = retrieval_quality(query, selected)
        report.sufficient = evidence_sufficient(report.quality)
        return selected, report
