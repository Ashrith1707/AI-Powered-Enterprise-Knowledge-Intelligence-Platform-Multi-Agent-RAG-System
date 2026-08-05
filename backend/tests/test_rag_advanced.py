"""Unit tests for the Module 5 RAG intelligence layer."""
from types import SimpleNamespace

from app.rag.bm25 import BM25Index
from app.rag.evaluation import mrr, ndcg_at_k, precision_at_k, recall_at_k
from app.rag.fusion import (adaptive_select, compress_chunk, deduplicate,
                            evidence_sufficient, reciprocal_rank_fusion,
                            retrieval_quality)
from app.rag.query_processing import analyze, history_aware_query
from app.rag.verifier import calibrated_confidence, verify_answer


def chunk(id, text, score=1.0):
    return SimpleNamespace(chunk_id=id, text=text, score=score)


# ---------------- BM25 ----------------
def test_bm25_ranks_rare_term_document_first():
    idx = BM25Index()
    idx.build([
        (1, "general company policy about office hours and leave"),
        (2, "the quarterly zeppelin audit revealed budget variance"),
        (3, "another general note about office matters"),
    ])
    results = idx.search("zeppelin audit", top_k=3)
    assert results[0][0] == 2


def test_bm25_empty_index():
    assert BM25Index().search("anything") == []


# ---------------- RRF ----------------
def test_rrf_rewards_agreement():
    fused = reciprocal_rank_fusion([[1, 2, 3], [1, 3, 2]])
    ranked = sorted(fused, key=fused.get, reverse=True)
    assert ranked[0] == 1                    # top of both lists wins
    assert set(ranked) == {1, 2, 3}


def test_rrf_single_list_preserves_order():
    fused = reciprocal_rank_fusion([[5, 9, 7]])
    assert sorted(fused, key=fused.get, reverse=True) == [5, 9, 7]


# ---------------- dedup / selection / compression ----------------
def test_deduplicate_drops_near_copy():
    a = chunk(1, "the revenue grew twelve percent in the third quarter of the year")
    b = chunk(2, "the revenue grew twelve percent in the third quarter of the year overall")
    c = chunk(3, "employee onboarding requires a signed policy acknowledgement form")
    kept = deduplicate([a, b, c])
    assert [k.chunk_id for k in kept] == [1, 3]


def test_adaptive_select_stops_at_score_cliff():
    chunks = [chunk(1, "a" * 100, 1.0), chunk(2, "b" * 100, 0.9),
              chunk(3, "c" * 100, 0.05), chunk(4, "d" * 100, 0.04)]
    selected = adaptive_select(chunks)
    assert [c.chunk_id for c in selected] == [1, 2]


def test_compress_keeps_query_sentences():
    text = ("The zeppelin budget was approved. " * 3
            + "Unrelated catering details follow here today. " * 30)
    out = compress_chunk(text, "zeppelin budget")
    assert "zeppelin" in out and len(out) < len(text)


# ---------------- sufficiency gate ----------------
def test_evidence_gate_refuses_on_nothing():
    assert evidence_sufficient({"chunks": 0, "term_coverage": 0, "top_score": 0}) is False


def test_evidence_gate_accepts_covered_query():
    q = retrieval_quality("zeppelin audit", [chunk(1, "the zeppelin audit report", 0.8)])
    assert evidence_sufficient(q) is True


# ---------------- query processing ----------------
def test_analyze_detects_list_and_summary():
    assert analyze("List all the payment deadlines")["type"] == "list"
    assert analyze("Summarize the contract")["type"] == "summary"


def test_history_aware_query_borrows_subject():
    out = history_aware_query("What about its revenue?",
                              ["Tell me about the Infosys company profile"])
    assert "infosys" in out.lower()


def test_history_rewrite_skipped_for_standalone_question():
    q = "What were the Infosys quarterly results announced in March?"
    assert history_aware_query(q, ["something earlier"]) == q


# ---------------- verifier ----------------
def test_verifier_flags_unsupported_sentence():
    chunks = [chunk(1, "The company revenue grew twelve percent in fiscal 2025.")]
    good = verify_answer("Revenue grew twelve percent in fiscal 2025 [1].", chunks)
    assert good["faithfulness"] == 1.0
    bad = verify_answer("The company acquired a submarine fleet yesterday [1].", chunks)
    assert bad["faithfulness"] == 0.0 and bad["flagged"]


def test_confidence_zero_on_refusal():
    v = {"refused": True, "faithfulness": 1.0, "uncited_claims": 0}
    assert calibrated_confidence({"term_coverage": 1, "top_score": 1}, v, 3) == 0.0


# ---------------- evaluation metrics (known values) ----------------
def test_precision_recall_known_values():
    retrieved, relevant = [1, 2, 3, 4], {2, 4, 9}
    assert precision_at_k(retrieved, relevant, 4) == 0.5
    assert round(recall_at_k(retrieved, relevant, 4), 4) == round(2 / 3, 4)


def test_mrr_first_relevant_at_rank_three():
    assert mrr([7, 8, 2], {2}) == 1 / 3
    assert mrr([7, 8], {2}) == 0.0


def test_ndcg_perfect_and_partial():
    assert ndcg_at_k([1, 2], {1, 2}, 2) == 1.0
    # relevant at ranks 1 and 3 of 3, two relevant total:
    # DCG = 1/log2(2) + 1/log2(4) = 1 + 0.5 ; IDCG = 1 + 1/log2(3)
    import math
    expected = (1 + 0.5) / (1 + 1 / math.log2(3))
    assert abs(ndcg_at_k([1, 9, 2], {1, 2}, 3) - expected) < 1e-9
