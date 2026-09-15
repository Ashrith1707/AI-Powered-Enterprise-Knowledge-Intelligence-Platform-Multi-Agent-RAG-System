"""Evaluation framework tests — metric correctness + a real end-to-end run."""
from __future__ import annotations

import math

import pytest

from app.evaluation.metrics import (
    answer_relevance,
    citation_accuracy,
    faithfulness,
    groundedness,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


# ---------------------------------------------------------------------------
# Metric math (hand-checked values)
# ---------------------------------------------------------------------------
def test_precision_and_recall_at_k():
    retrieved = [1, 2, 3, 4, 5]
    relevant = [2, 4, 6]
    assert precision_at_k(retrieved, relevant, 5) == pytest.approx(2 / 5, abs=1e-3)
    assert recall_at_k(retrieved, relevant, 5) == pytest.approx(2 / 3, abs=1e-3)
    assert precision_at_k(retrieved, relevant, 2) == pytest.approx(1 / 2, abs=1e-3)


def test_reciprocal_rank_and_mrr():
    assert reciprocal_rank([5, 3, 1], [1]) == pytest.approx(1 / 3, abs=1e-3)
    assert reciprocal_rank([5, 6], [1]) == 0.0
    assert mrr([[1, 2], [5, 2]], [[1], [2]]) == pytest.approx((1.0 + 0.5) / 2, abs=1e-3)


def test_ndcg_known_value():
    # perfect ranking of graded relevance → nDCG = 1.0
    grades = {1: 3.0, 2: 2.0, 3: 1.0}
    assert ndcg_at_k([1, 2, 3], grades, 3) == pytest.approx(1.0, abs=1e-3)
    # worst ordering < 1
    assert ndcg_at_k([3, 2, 1], grades, 3) < 1.0
    # empty grades → 0
    assert ndcg_at_k([1], {}, 3) == 0.0


def test_ndcg_manual_calculation():
    grades = {10: 2.0, 20: 1.0}
    retrieved = [20, 10]
    dcg = 1.0 / math.log2(2) + 2.0 / math.log2(3)
    idcg = 2.0 / math.log2(2) + 1.0 / math.log2(3)
    assert ndcg_at_k(retrieved, grades, 2) == pytest.approx(dcg / idcg, abs=1e-3)


def test_faithfulness_and_relevance():
    evidence = ["Employees receive 24 days of paid annual leave each year."]
    grounded = "Employees receive 24 days of paid annual leave."
    invented = "The company operates a fleet of helicopters and submarines."
    assert faithfulness(grounded, evidence) > 0.7
    assert faithfulness(invented, evidence) < 0.3
    assert answer_relevance(grounded, "How many days of annual leave do employees receive?") > 0.3
    # boilerplate lines do not dilute faithfulness
    grounded_with_boilerplate = (
        "Based on the retrieved enterprise documents, here is what they say:\n"
        "- Employees receive 24 days of paid annual leave.\n"
        "(Answer produced in offline mock mode.)"
    )
    assert faithfulness(grounded_with_boilerplate, evidence) > 0.7


def test_citation_accuracy():
    citations = [{"chunk_id": 1}, {"chunk_id": 2}, {"chunk_id": 99}]
    assert citation_accuracy(citations, [1, 2, 3]) == pytest.approx(2 / 3, abs=1e-3)
    assert citation_accuracy([], [1]) == 0.0


def test_groundedness():
    from app.agents.schemas import Evidence

    ev = Evidence(evidence_id="E1", chunk_id=1, document_id=1, document_title="t", filename="f",
                  page_start=1, page_end=1, score=0.9,
                  text="Hearing protection is required above 85 decibels.",
                  original_chars=10, compressed_chars=10)
    assert groundedness("Hearing protection is required above 85 decibels [E1].", [ev]) == 1.0
    assert groundedness("The office has an Olympic swimming pool [E1].", [ev]) == 0.0


# ---------------------------------------------------------------------------
# End-to-end evaluation run (real pipeline, real corpus, no fabricated numbers)
# ---------------------------------------------------------------------------
def test_full_evaluation_run(env):
    import asyncio

    from app.evaluation.run import run_evaluation

    results = asyncio.run(run_evaluation(keep_corpus=False))

    assert results["num_queries"] == 8
    r = results["retrieval_metrics"]
    g = results["generation_metrics"]

    # Retrieval over the labeled corpus must actually work with the offline stack
    assert r["recall@5"] >= 0.6, f"recall@5 too low: {r}"
    assert r["mrr"] >= 0.6, f"mrr too low: {r}"
    assert r["precision@5"] > 0

    # Generation from extractive mock answers is grounded by construction
    assert g["faithfulness"] >= 0.5
    assert g["citation_accuracy"] >= 0.8
    assert g["groundedness"] >= 0.5

    # The unanswerable question must be refused honestly
    assert results["refusal_handling"]["expected"] == 1
    assert results["refusal_handling"]["correct"] == 1

    # Results persisted (DB row + JSON file)
    from app.database import session_scope
    from app.models import EvaluationResult
    from sqlalchemy import select

    with session_scope() as session:
        row = session.execute(
            select(EvaluationResult).where(EvaluationResult.run_id == results["run_id"])
        ).scalar_one()
        assert row.num_queries == 8
        assert row.retrieval_metrics_json["mrr"] == r["mrr"]

    from pathlib import Path

    assert Path(results["output_path"]).exists()

    # Corpus cleanup happened
    with session_scope() as session:
        from app.models import User

        eval_user = session.execute(select(User).where(User.email == "evaluation@knowledgeiq.internal")).scalar_one_or_none()
        if eval_user:
            from app.models import Document

            docs = session.execute(select(Document).where(Document.user_id == eval_user.id)).all()
            assert docs == []


def test_evaluation_results_api(client, user_client):
    client, headers, _ = user_client
    r = client.get("/api/evaluation/results", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"items": []}
