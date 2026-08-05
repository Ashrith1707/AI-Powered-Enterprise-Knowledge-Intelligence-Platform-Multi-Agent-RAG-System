from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_documents: int
    indexed_documents: int
    failed_documents: int
    total_pages: int
    total_chunks: int
    total_searches: int
    avg_latency_ms: float
    documents_by_category: dict[str, int]
    documents_by_type: dict[str, int]
    recent_queries: list[str]
