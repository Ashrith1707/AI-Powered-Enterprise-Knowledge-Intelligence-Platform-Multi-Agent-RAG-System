from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import SearchLog
from app.schemas.analytics import DashboardStats
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)):
    return AnalyticsService(db).dashboard_stats()


@router.get("/searches")
def search_analytics(days: int = 30, db: Session = Depends(get_db)):
    """Timestamped search history aggregates for trend charts."""
    days = max(1, min(days, 90))
    since = datetime.utcnow() - timedelta(days=days)

    rows = db.execute(
        select(func.date(SearchLog.created_at), func.count(), func.avg(SearchLog.latency_ms))
        .where(SearchLog.created_at >= since)
        .group_by(func.date(SearchLog.created_at))
    ).all()
    by_day = {str(d): {"count": c, "avg_latency_ms": round(float(a or 0), 1)}
              for d, c, a in rows}

    daily = []
    for i in range(days - 1, -1, -1):
        key = str((datetime.utcnow() - timedelta(days=i)).date())
        entry = by_day.get(key, {"count": 0, "avg_latency_ms": 0})
        daily.append({"date": key, **entry})

    top = db.execute(
        select(SearchLog.query, func.count().label("n"))
        .where(SearchLog.created_at >= since)
        .group_by(SearchLog.query)
        .order_by(func.count().desc())
        .limit(8)
    ).all()

    total = db.scalar(select(func.count(SearchLog.id))
                      .where(SearchLog.created_at >= since)) or 0
    return {"days": days, "total": total, "daily": daily,
            "top_queries": [{"query": q, "count": n} for q, n in top]}
