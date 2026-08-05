from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class MessageIn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = ""
    question: str = ""
    meta: dict = {}


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    question: str
    meta: dict
    created_at: datetime


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    pinned: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []
