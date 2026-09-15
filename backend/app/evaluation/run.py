"""Repeatable RAG evaluation (Module 7).

Usage:
    python -m app.evaluation.run                 # run the golden dataset
    python -m app.evaluation.run --keep-corpus   # keep eval documents ingested
    python -m app.evaluation.run --output out.json

What it does — for real, with no fabricated numbers:
1. Ingests the labeled corpus (data/evaluation/corpus) under a dedicated
   internal evaluation user.
2. Runs every golden query through the FULL agent pipeline (orchestrator).
3. Computes retrieval metrics (Precision@K, Recall@K, MRR, nDCG) against
   derived chunk-level ground truth, generation metrics (faithfulness,
   answer relevance, citation accuracy, groundedness) from actual outputs,
   and system metrics (latencies, tokens, chunks, verification failures).
4. Persists results (EvaluationResult table + machine-readable JSON) and
   prints a summary table.
5. Cleans up the ingested evaluation corpus unless --keep-corpus.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select

from app.agents.base import UserInfo
from app.agents.orchestrator import get_orchestrator
from app.core.security import hash_password
from app.database import init_db, session_scope
from app.evaluation.dataset import EvalDataset, derive_chunk_ground_truth, load_dataset
from app.evaluation.metrics import generation_metrics, retrieval_metrics, system_metrics
from app.models import Document, DocumentChunk, DocumentStatus, EvaluationResult, User

EVAL_USER_EMAIL = "evaluation@knowledgeiq.internal"
EVAL_TAG = "evaluation-corpus"


def _ensure_eval_user() -> int:
    with session_scope() as session:
        user = session.execute(select(User).where(User.email == EVAL_USER_EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(
                email=EVAL_USER_EMAIL,
                hashed_password=hash_password(uuid.uuid4().hex),
                full_name="Evaluation Runner",
                role="user",
                is_active=True,
            )
            session.add(user)
            session.flush()
        return user.id


def _cleanup_previous_eval_documents() -> None:
    """Remove documents from previous evaluation runs (vectors included)."""
    with session_scope() as session:
        user = session.execute(select(User).where(User.email == EVAL_USER_EMAIL)).scalar_one_or_none()
        if user is None:
            return
        docs = session.execute(select(Document).where(Document.user_id == user.id)).scalars().all()
        for doc in docs:
            _delete_document_fully(session, doc)


def _delete_document_fully(session, document: Document) -> None:
    from app.rag.bm25 import get_bm25_index
    from app.services.vector_store import get_vector_store

    chunk_ids = [
        row[0] for row in session.execute(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document.id)
        ).all()
    ]
    if chunk_ids:
        get_vector_store().remove(chunk_ids)
        get_bm25_index().remove(chunk_ids)
    from app.config import get_settings

    path = Path(get_settings().upload_dir) / document.stored_filename
    path.unlink(missing_ok=True)
    session.delete(document)


def _ingest_corpus(dataset: EvalDataset, user_id: int) -> Dict[str, int]:
    """Ingest each corpus file; returns filename → document_id."""
    from app.services.file_validation import validate_upload
    from app.services.ingestion import process_document_sync
    from app.core.security import generate_stored_name, sanitize_filename
    from app.config import get_settings

    settings = get_settings()
    filename_to_doc: Dict[str, int] = {}
    for filename in dataset.corpus_files:
        source = dataset.corpus_path(filename)
        content = source.read_bytes()
        validated = validate_upload(filename, content)
        stored_name = generate_stored_name(sanitize_filename(filename))
        (Path(settings.upload_dir) / stored_name).write_bytes(content)

        with session_scope() as session:
            document = Document(
                user_id=user_id,
                filename=sanitize_filename(filename),
                stored_filename=stored_name,
                file_type=validated.extension,
                file_size=validated.size_bytes,
                status=DocumentStatus.pending,
                metadata_json={"tags": [EVAL_TAG]},
            )
            session.add(document)
            session.flush()
            doc_id = document.id
        process_document_sync(doc_id)
        filename_to_doc[filename] = doc_id
        print(f"  ingested {filename} → document {doc_id}")
    return filename_to_doc


async def _run_query(orchestrator, user_info: UserInfo, question: str):
    with session_scope() as session:
        return await orchestrator.run(
            session=session,
            user=user_info,
            query=question,
            conversation_id=None,
            request_id=f"eval-{uuid.uuid4().hex[:8]}",
            return_context=True,
        )


def _aggregate(values: List[float]) -> Optional[float]:
    return round(statistics.fmean(values), 4) if values else None


async def run_evaluation(dataset_path: Optional[str] = None, output: Optional[str] = None,
                         keep_corpus: bool = False) -> dict:
    started = time.perf_counter()
    init_db()
    dataset = load_dataset(dataset_path)
    print(f"Evaluating dataset '{dataset.name}' ({len(dataset.queries)} queries, {len(dataset.corpus_files)} docs)")

    _cleanup_previous_eval_documents()
    user_id = _ensure_eval_user()
    print("Ingesting evaluation corpus…")
    filename_to_doc = _ingest_corpus(dataset, user_id)

    with session_scope() as session:
        ground_truth = derive_chunk_ground_truth(session, dataset, filename_to_doc)

    orchestrator = get_orchestrator()
    user_info = UserInfo(id=user_id, email=EVAL_USER_EMAIL, role="user")

    per_query: List[dict] = []
    retrieval_acc: Dict[str, List[float]] = {}
    generation_acc: Dict[str, List[float]] = {}
    system_acc: Dict[str, List[float]] = {}
    refusal_checks = {"expected": 0, "correct": 0}

    for query in dataset.queries:
        response, ctx = await _run_query(orchestrator, user_info, query.question)

        retrieved_ids = [c.chunk_id for c in ctx.candidates]
        grades = ground_truth.get(query.id, {})
        relevant_ids = list(grades.keys())

        if relevant_ids:
            r_metrics = retrieval_metrics(retrieved_ids, relevant_ids, grades)
            for key, value in r_metrics.items():
                retrieval_acc.setdefault(key, []).append(value)
        else:
            r_metrics = {}

        evidences = ctx.compressed.evidences if ctx.compressed else []
        citations = [c.model_dump(mode="json") for c in response.citations]
        g_metrics = generation_metrics(
            answer=response.answer, question=query.question, evidences=evidences,
            citations=citations, retrieved_chunk_ids=retrieved_ids,
        )
        s_metrics = system_metrics(response.metrics)

        refusal_ok = None
        if query.expect_insufficient_evidence:
            refusal_checks["expected"] += 1
            refusal_ok = bool(response.insufficient_evidence)
            refusal_checks["correct"] += int(refusal_ok)

        # Expected refusals are graded by refusal_handling, not by generation
        # metrics (an honest no-answer legitimately has no citations).
        expected_refusal_hit = query.expect_insufficient_evidence and bool(response.insufficient_evidence)
        if not expected_refusal_hit:
            for key, value in g_metrics.items():
                generation_acc.setdefault(key, []).append(value)
        for key, value in s_metrics.items():
            system_acc.setdefault(key, []).append(value)

        per_query.append({
            "id": query.id,
            "question": query.question,
            "retrieval": r_metrics,
            "generation": g_metrics,
            "system": s_metrics,
            "insufficient_evidence": response.insufficient_evidence,
            "refusal_check_passed": refusal_ok,
            "verified": response.verification.verified,
            "verification_confidence": response.verification.confidence,
            "citations": len(response.citations),
            "retrieved_chunk_ids": retrieved_ids,
            "relevant_chunk_ids": relevant_ids,
            "answer_preview": response.answer[:300],
        })
        print(
            f"  [{query.id}] retrieval={r_metrics.get('mrr', 'n/a')} "
            f"faithfulness={g_metrics['faithfulness']} citations={len(response.citations)} "
            f"verified={response.verification.verified}"
        )

    results = {
        "run_id": f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
        "dataset": dataset.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider_mode": _provider_mode(),
        "num_queries": len(dataset.queries),
        "retrieval_metrics": {k: _aggregate(v) for k, v in sorted(retrieval_acc.items())},
        "generation_metrics": {k: _aggregate(v) for k, v in sorted(generation_acc.items())},
        "system_metrics": {k: _aggregate(v) for k, v in sorted(system_acc.items())},
        "refusal_handling": refusal_checks,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "per_query": per_query,
    }

    overall = _overall_score(results)
    results["overall_score"] = overall

    # Persist to DB
    with session_scope() as session:
        session.add(
            EvaluationResult(
                run_id=results["run_id"],
                dataset_name=dataset.name,
                num_queries=len(dataset.queries),
                provider_mode=results["provider_mode"],
                retrieval_metrics_json=results["retrieval_metrics"],
                generation_metrics_json=results["generation_metrics"],
                system_metrics_json=results["system_metrics"],
                per_query_json=per_query,
                overall_score=overall,
            )
        )

    # Persist JSON artifact
    from app.config import BASE_DIR

    out_dir = BASE_DIR / "data" / "evaluation" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(output) if output else out_dir / f"{results['run_id']}.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    results["output_path"] = str(out_path)

    if not keep_corpus:
        with session_scope() as session:
            user = session.execute(select(User).where(User.email == EVAL_USER_EMAIL)).scalar_one_or_none()
            if user:
                docs = session.execute(select(Document).where(Document.user_id == user.id)).scalars().all()
                for doc in docs:
                    _delete_document_fully(session, doc)
        print("Evaluation corpus cleaned up (use --keep-corpus to retain).")

    _print_summary(results)
    return results


def _provider_mode() -> str:
    from app.services.embeddings import get_embedding_provider
    from app.services.llm import get_llm_provider

    return f"llm={get_llm_provider().name},embeddings={get_embedding_provider().name}"


def _overall_score(results: dict) -> Optional[float]:
    """Composite score: mean of the headline retrieval + generation metrics."""
    values: List[float] = []
    r = results["retrieval_metrics"]
    g = results["generation_metrics"]
    for key in ("recall@5", "mrr", "ndcg@5"):
        if r.get(key) is not None:
            values.append(r[key])
    for key in ("faithfulness", "citation_accuracy", "groundedness"):
        if g.get(key) is not None:
            values.append(g[key])
    refusal = results["refusal_handling"]
    if refusal["expected"]:
        values.append(refusal["correct"] / refusal["expected"])
    return round(statistics.fmean(values), 4) if values else None


def _print_summary(results: dict) -> None:
    print("\n" + "=" * 62)
    print(f"EVALUATION SUMMARY — {results['dataset']} ({results['num_queries']} queries)")
    print(f"provider_mode: {results['provider_mode']}")
    print("-" * 62)
    print("RETRIEVAL")
    for key, value in results["retrieval_metrics"].items():
        print(f"  {key:<16} {value}")
    print("GENERATION")
    for key, value in results["generation_metrics"].items():
        print(f"  {key:<16} {value}")
    print("SYSTEM (averages)")
    for key, value in results["system_metrics"].items():
        print(f"  {key:<28} {value}")
    refusal = results["refusal_handling"]
    print(f"REFUSAL HANDLING        {refusal['correct']}/{refusal['expected']} correct")
    print(f"OVERALL SCORE           {results['overall_score']}")
    print(f"Duration: {results['duration_seconds']}s → {results.get('output_path', '')}")
    print("=" * 62)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the KnowledgeIQ RAG evaluation.")
    parser.add_argument("--dataset", default=None, help="Path to a golden dataset JSON")
    parser.add_argument("--output", default=None, help="Where to write the JSON results")
    parser.add_argument("--keep-corpus", action="store_true", help="Keep the ingested evaluation corpus")
    args = parser.parse_args()
    asyncio.run(run_evaluation(args.dataset, args.output, args.keep_corpus))


if __name__ == "__main__":
    main()
