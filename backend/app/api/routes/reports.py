from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.repositories.activity_repository import ActivityRepository
from app.schemas.report import ReportOut, ReportRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=201)
def create_report(body: ReportRequest, db: Session = Depends(get_db)):
    return ReportService(db).generate(
        title=body.title, report_type=body.report_type,
        file_format=body.file_format, document_ids=body.document_ids,
        question=body.question)


@router.get("", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    return ActivityRepository(db).list_reports()


@router.get("/{report_id}/download")
def download_report(report_id: int, db: Session = Depends(get_db)):
    report = ActivityRepository(db).get_report(report_id)
    if report is None or not Path(report.file_path).exists():
        raise NotFoundError(f"Report {report_id} not found.")
    return FileResponse(report.file_path, filename=Path(report.file_path).name)
