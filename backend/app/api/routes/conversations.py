"""Server-side chat history — scoped to the authenticated user."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.models import Conversation, Message, User
from app.schemas.chat import (ConversationOut, ConversationPatch, MessageIn, MessageOut)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _own(db: Session, user: User, conversation_id: int) -> Conversation:
    convo = db.get(Conversation, conversation_id)
    if convo is None or convo.user_id != user.id:
        raise NotFoundError("Conversation not found.")
    return convo


@router.get("", response_model=list[ConversationOut])
def list_conversations(limit: int = 50, offset: int = 0, archived: bool = False,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    stmt = (select(Conversation)
            .where(Conversation.user_id == user.id, Conversation.archived == archived)
            .order_by(Conversation.updated_at.desc())
            .limit(limit).offset(offset))
    return list(db.scalars(stmt))


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    convo = Conversation(user_id=user.id)
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


@router.patch("/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: int, body: ConversationPatch,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    convo = _own(db, user, conversation_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(convo, field, value)
    db.commit()
    db.refresh(convo)
    return convo


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    db.delete(_own(db, user, conversation_id))
    db.commit()


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
def add_message(conversation_id: int, body: MessageIn,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    convo = _own(db, user, conversation_id)
    message = Message(conversation_id=convo.id, role=body.role,
                      content=body.content, question=body.question, meta=body.meta)
    # First user message names the conversation.
    if body.role == "user" and convo.title == "New conversation":
        convo.title = body.content[:48]
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
