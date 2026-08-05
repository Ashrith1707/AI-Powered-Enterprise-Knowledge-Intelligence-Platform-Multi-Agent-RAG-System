"""DB access for reports, search logs and audit logs."""
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Report, SearchLog, AuditLog


class ActivityRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- reports ----
    def create_report(self, **fields) -> Report:
        report = Report(**fields)
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def get_report(self, report_id: int) -> Report | None:
        return self.db.get(Report, report_id)

    def list_reports(self, limit: int = 50) -> list[Report]:
        stmt = select(Report).order_by(Report.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    # ---- search logs ----
    def log_search(self, **fields) -> SearchLog:
        log = SearchLog(**fields)
        self.db.add(log)
        self.db.commit()
        return log

    def search_stats(self) -> tuple[int, float]:
        total = self.db.scalar(select(func.count(SearchLog.id))) or 0
        avg = self.db.scalar(select(func.avg(SearchLog.latency_ms))) or 0.0
        return total, round(float(avg), 1)

    def recent_queries(self, limit: int = 8) -> list[str]:
        stmt = select(SearchLog.query).order_by(SearchLog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt))

    # ---- audit ----
    def audit(self, actor: str, action: str, entity_type: str,
              entity_id: int | None = None, detail: dict | None = None) -> None:
        self.db.add(AuditLog(actor=actor, action=action, entity_type=entity_type,
                             entity_id=entity_id, detail=detail or {}))
        self.db.commit()
