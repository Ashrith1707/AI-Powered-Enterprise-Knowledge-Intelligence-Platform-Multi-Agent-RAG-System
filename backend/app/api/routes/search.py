"""Semantic search + RAG question answering (coordinator + SSE streaming)."""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.coordinator import CoordinatorAgent
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import LLMNotConfiguredError, ProcessingError
from app.rag.rag_service import RAGService
from app.repositories.activity_repository import ActivityRepository
from app.schemas.query import (AskRequest, AskResponse, SearchHit,
                               SearchRequest, SearchResponse)

router = APIRouter(prefix="/api", tags=["search"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/search", response_model=SearchResponse)
def semantic_search(body: SearchRequest, db: Session = Depends(get_db)):
    hits, latency = RAGService(db).semantic_search(body.query, body.top_k)
    ActivityRepository(db).log_search(query=body.query, mode="semantic",
                                      result_count=len(hits), latency_ms=latency)
    return SearchResponse(
        query=body.query, latency_ms=latency,
        hits=[SearchHit(chunk_id=h.chunk_id, document_id=h.document_id,
                        document_name=h.document_name, page_number=h.page_number,
                        score=round(h.score, 4), snippet=h.text[:300]) for h in hits])


@router.post("/ask/stream")
def ask_stream(body: AskRequest, db: Session = Depends(get_db),
               user=Depends(get_current_user)):
    """Server-Sent Events: real pipeline stages, real Gemini tokens, final
    payload with citations. The client may abort at any time — generation
    stops when the connection closes."""
    rag = RAGService(db)

    # Conversation-aware retrieval: prior user turns resolve follow-ups.
    prior_user_messages: list[str] = []
    if body.conversation_id:
        from app.models import Conversation
        convo = db.get(Conversation, body.conversation_id)
        if convo and convo.user_id == user.id:
            prior_user_messages = [m.content for m in convo.messages
                                   if m.role == "user"][-3:]

    def event_source():
        final = None
        try:
            for event in rag.answer_stream(body.question, prior_user_messages):
                kind = event.pop("type")
                if kind == "done":
                    final = event
                yield _sse(kind, event)
        except LLMNotConfiguredError as exc:
            yield _sse("error", {"message": exc.message})
        except Exception as exc:  # surface, never hang the stream
            yield _sse("error", {"message": str(exc)})
        finally:
            if final is not None:
                ActivityRepository(db).log_search(
                    query=body.question, mode="rag",
                    result_count=len(final["citations"]),
                    latency_ms=final["latency_ms"])

    return StreamingResponse(event_source(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, db: Session = Depends(get_db)):
    result = CoordinatorAgent(db).handle("ask", {"question": body.question})
    if not result["success"]:
        raise ProcessingError(result["error"] or "Agent workflow failed.")

    answer_data = result["output"]
    evaluation = result.get("evaluation") or {}
    ActivityRepository(db).log_search(
        query=body.question, mode="rag",
        result_count=len(answer_data["citations"]),
        latency_ms=answer_data["latency_ms"],
        evaluation_score=evaluation.get("score"))
    return AskResponse(question=body.question,
                       answer=answer_data["answer"],
                       citations=answer_data["citations"],
                       confidence=answer_data["confidence"],
                       latency_ms=answer_data["latency_ms"],
                       agent_trace=result["trace"])
