"""Chat routes — the multi-agent RAG entrypoint.

* ``POST /api/chat/ask``         → JSON FinalResponse (full agent pipeline)
* ``POST /api/chat/ask/stream``  → SSE stream (trace steps, tokens, final)
* ``GET  /api/chat/mode``        → active AI providers (gemini vs offline mock)

SSE event types: ``trace`` | ``plan`` | ``token`` | ``final`` | ``error``.
Only safe execution summaries are streamed — never hidden chain-of-thought.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.base import UserInfo
from app.agents.orchestrator import get_orchestrator
from app.core.deps import get_current_user_info
from app.core.logging_conf import request_id_var
from app.database import get_db
from app.schemas.chat import AskRequest
from app.services.embeddings import embedding_provider_status
from app.services.llm import get_llm_provider
from app.services.ocr import get_ocr_capability

router = APIRouter(prefix="/chat", tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/mode")
def ai_mode():
    """Report which AI providers are active — honest mode reporting, no silent downgrade."""
    llm = get_llm_provider()
    embeddings = embedding_provider_status()
    ocr = get_ocr_capability()
    return {
        "llm": {"provider": llm.name, "model": getattr(llm, "model", "mock-extractive-v1")},
        "embeddings": embeddings,
        "ocr": {
            "tesseract_available": ocr.tesseract_available,
            "pdf_rendering_available": ocr.pdf_rendering_available,
            "languages": ocr.languages,
        },
        "note": (
            "Set GEMINI_API_KEY to enable full generative answers and semantic embeddings."
            if llm.name == "mock" else None
        ),
    }


@router.post("/ask")
async def ask(
    payload: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: UserInfo = Depends(get_current_user_info),
):
    orchestrator = get_orchestrator()
    response = await orchestrator.run(
        session=db,
        user=user,
        query=payload.question,
        conversation_id=payload.conversation_id,
        request_id=request_id_var.get(),
    )
    return response.model_dump(mode="json")


@router.post("/ask/stream")
async def ask_stream(
    payload: AskRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: UserInfo = Depends(get_current_user_info),
):
    orchestrator = get_orchestrator()
    rid = request_id_var.get()

    async def event_source() -> AsyncIterator[str]:
        try:
            async for event in orchestrator.run_stream(
                session=db,
                user=user,
                query=payload.question,
                conversation_id=payload.conversation_id,
                request_id=rid,
            ):
                if await request.is_disconnected():
                    break
                yield _sse(event["event"], event)
        except Exception as exc:  # noqa: BLE001 — surface structured error then stop
            from app.core.errors import classify_ai_error

            classified = classify_ai_error(exc)
            yield _sse("error", {
                "event": "error",
                "code": classified.error_code.value,
                "message": classified.message,
                "details": classified.details,
            })
        yield _sse("done", {"event": "done"})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
