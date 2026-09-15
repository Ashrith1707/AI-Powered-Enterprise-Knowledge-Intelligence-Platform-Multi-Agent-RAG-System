"""Golden dataset loading + chunk-level ground-truth derivation.

Ground truth is *derived from human labels*: each query lists relevant source
files and evidence keywords. After the corpus is ingested, a chunk is graded
relevant when it belongs to a relevant file AND contains labeled evidence
keywords (grade = number of distinct keyword hits, capped at 3).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk


@dataclass
class EvalQuery:
    id: str
    question: str
    relevant_files: List[str]
    evidence_keywords: List[str]
    expect_insufficient_evidence: bool = False
    ideal_points: List[str] = field(default_factory=list)


@dataclass
class EvalDataset:
    name: str
    description: str
    corpus_dir: Path
    corpus_files: List[str]
    queries: List[EvalQuery]

    def corpus_path(self, filename: str) -> Path:
        return self.corpus_dir / filename


def load_dataset(path: Optional[str] = None) -> EvalDataset:
    from app.config import BASE_DIR

    dataset_path = Path(path) if path else (BASE_DIR / "data" / "evaluation" / "golden_dataset.json")
    data = json.loads(dataset_path.read_text())
    corpus_dir = (BASE_DIR / data.get("corpus_dir", "data/evaluation/corpus")).resolve()
    return EvalDataset(
        name=data["name"],
        description=data.get("description", ""),
        corpus_dir=corpus_dir,
        corpus_files=list(data["corpus"]),
        queries=[
            EvalQuery(
                id=q["id"],
                question=q["question"],
                relevant_files=q.get("relevant_files", []),
                evidence_keywords=q.get("evidence_keywords", []),
                expect_insufficient_evidence=q.get("expect_insufficient_evidence", False),
                ideal_points=q.get("ideal_points", []),
            )
            for q in data["queries"]
        ],
    )


def derive_chunk_ground_truth(
    session: Session,
    dataset: EvalDataset,
    filename_to_document_id: Dict[str, int],
) -> Dict[str, Dict[int, float]]:
    """query_id → {chunk_id: grade}."""
    ground_truth: Dict[str, Dict[int, float]] = {}

    for query in dataset.queries:
        grades: Dict[int, float] = {}
        relevant_doc_ids = [filename_to_document_id[f] for f in query.relevant_files if f in filename_to_document_id]
        if relevant_doc_ids:
            chunks = session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id.in_(relevant_doc_ids))
            ).scalars().all()
            keywords = [k.lower() for k in query.evidence_keywords]
            for chunk in chunks:
                content = chunk.content.lower()
                hits = sum(1 for kw in keywords if kw in content)
                if hits:
                    grades[chunk.id] = float(min(hits, 3))
        ground_truth[query.id] = grades
    return ground_truth
