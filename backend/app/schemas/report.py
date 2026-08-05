from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ReportRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    report_type: str = Field(default="analytics", pattern="^(summary|analytics|qa)$")
    file_format: str = Field(default="pdf", pattern="^(pdf|docx)$")
    document_ids: list[int] = []
    question: str | None = None   # only for report_type == "qa"


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    report_type: str
    file_format: str
    status: str
    created_at: datetime
