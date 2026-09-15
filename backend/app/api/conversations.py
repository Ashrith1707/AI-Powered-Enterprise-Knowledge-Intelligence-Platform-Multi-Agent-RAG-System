"""Conversation history routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, write_audit
from app.core.errors import NotFoundError
from app.database import get_db
from app.models import Conversation, Message, User
from app.schemas.chat import ConversationDetailOut, ConversationOut, MessageOut

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_owned(db: Session, conversation_id: int, user: User) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or (conversation.user_id != user.id and not user.is_admin):
        raise NotFoundError(f"Conversation {conversation_id} not found.")
    return conversation


def _to_out(conversation: Conversation, message_count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        summary=conversation.summary or "",
        created_at=conversation.created_at.isoformat() if conversation.created_at else None,
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        message_count=message_count,
    )


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    rows = db.execute(
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    ).all()
    return [_to_out(conv, count) for conv, count in rows]


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = _get_owned(db, conversation_id, user)
    messages = list(conversation.messages)
    return ConversationDetailOut(
        conversation=_to_out(conversation, len(messages)),
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=m.citations_json or [],
                agent_trace=m.agent_trace_json or {},
                metrics=m.metrics_json or {},
                created_at=m.created_at.isoformat() if m.created_at else None,
            )
            for m in messages
        ],
    )


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conversation = _get_owned(db, conversation_id, user)
    db.delete(conversation)
    db.commit()
    write_audit(db, user_id=user.id, action="delete_conversation", resource_type="conversation",
                resource_id=conversation_id)
    return None
