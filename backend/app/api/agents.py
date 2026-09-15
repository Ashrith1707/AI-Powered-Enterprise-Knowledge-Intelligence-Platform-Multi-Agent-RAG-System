"""Agent introspection routes — registry + persisted execution traces."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENT_REGISTRY
from app.core.deps import get_current_user
from app.core.errors import NotFoundError
from app.database import get_db
from app.models import Conversation, Message, User

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents():
    """The eight-agent pipeline, in execution order."""
    return {
        "architecture": "multi-agent-rag",
        "pipeline": [
            "planner", "retriever", "metadata", "reranker",
            "compressor", "answer_generator", "verifier", "citation_validator",
        ],
        "agents": AGENT_REGISTRY,
    }


@router.get("/traces/{message_id}")
def get_trace(message_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return the persisted agent trace for one assistant message (owner/admin only)."""
    message = db.get(Message, message_id)
    if message is None:
        raise NotFoundError("Message not found.")
    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None or (conversation.user_id != user.id and not user.is_admin):
        raise NotFoundError("Message not found.")
    return {
        "message_id": message.id,
        "conversation_id": message.conversation_id,
        "agent_trace": message.agent_trace_json or {},
        "metrics": message.metrics_json or {},
        "citations": message.citations_json or [],
    }


@router.get("/traces")
def latest_traces(db: Session = Depends(get_db), user: User = Depends(get_current_user), limit: int = 10):
    """Most recent traces for the current user (for the Agent Trace UI)."""
    conv_ids = select(Conversation.id).where(Conversation.user_id == user.id)
    rows = db.execute(
        select(Message)
        .where(Message.conversation_id.in_(conv_ids), Message.role == "assistant")
        .order_by(Message.id.desc())
        .limit(max(1, min(limit, 50)))
    ).scalars().all()
    return [
        {
            "message_id": m.id,
            "conversation_id": m.conversation_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "agent_trace": m.agent_trace_json or {},
            "metrics": m.metrics_json or {},
        }
        for m in rows
    ]
