from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[int] = None
    stream: bool = False


class ConversationOut(BaseModel):
    id: int
    title: str
    summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    citations: list = []
    agent_trace: dict = {}
    metrics: dict = {}
    created_at: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
