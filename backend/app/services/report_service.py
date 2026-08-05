"""Generates PDF (ReportLab) and DOCX (python-docx) reports.

Report types:
  analytics — platform metrics snapshot
  summary   — per-document metadata summaries
  qa        — a RAG answer with its citations, archived as a document
"""
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.repositories.activity_repository import ActivityRepository
from app.repositories.document_repository import DocumentRepository
from app.services.analytics_service import AnalyticsService


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.docs = DocumentRepository(db)
        self.activity = ActivityRepository(db)

    def generate(self, title: str, report_type: str, file_format: str,
                 document_ids: list[int], question: str | None = None):
        sections = self._build_sections(report_type, document_ids, question)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{report_type}_{stamp}.{file_format}"
        path = settings.reports_dir / filename

        if file_format == "pdf":
            self._write_pdf(path, title, sections)
        else:
            self._write_docx(path, title, sections)

        report = self.activity.create_report(
            title=title, report_type=report_type,
            file_format=file_format, file_path=str(path))
        self.activity.audit("report_service", "report.generated", "report", report.id,
                            {"type": report_type, "format": file_format})
        return report

    # ---------- content ----------
    def _build_sections(self, report_type, document_ids, question) -> list[tuple[str, str]]:
        if report_type == "analytics":
            stats = AnalyticsService(self.db).dashboard_stats()
            categories = "\n".join(f"  - {k}: {v}" for k, v in
                                   stats["documents_by_category"].items()) or "  (none)"
            return [
                ("Platform Overview",
                 f"Total documents: {stats['total_documents']}\n"
                 f"Indexed: {stats['indexed_documents']}   Failed: {stats['failed_documents']}\n"
                 f"Pages extracted: {stats['total_pages']}\n"
                 f"Knowledge chunks: {stats['total_chunks']}"),
                ("Search Activity",
                 f"Total searches: {stats['total_searches']}\n"
                 f"Average latency: {stats['avg_latency_ms']} ms"),
                ("Documents by Category", categories),
            ]

        if report_type == "summary":
            if not document_ids:
                raise ValidationError("summary report requires document_ids.")
            sections = []
            for doc_id in document_ids:
                doc = self.docs.get(doc_id)
                if doc is None:
                    continue
                meta = doc.doc_metadata
                body = (f"File: {doc.filename}\nCategory: {doc.category}\n"
                        f"Pages: {doc.page_count}   OCR used: {doc.used_ocr}\n")
                if meta:
                    body += (f"Keywords: {', '.join(meta.keywords)}\n"
                             f"Summary: {meta.summary}")
                sections.append((f"Document #{doc.id}: {doc.filename}", body))
            if not sections:
                raise ValidationError("None of the given document_ids exist.")
            return sections

        if report_type == "qa":
            if not question:
                raise ValidationError("qa report requires a question.")
            from app.rag.rag_service import RAGService
            result = RAGService(self.db).answer(question)
            cite_text = "\n".join(
                f"{c['marker']} {c['document_name']}, page {c['page_number']}"
                for c in result["citations"]) or "(no citations)"
            return [("Question", question),
                    ("AI Answer", result["answer"]),
                    ("Citations", cite_text),
                    ("Confidence", str(result["confidence"]))]

        raise ValidationError(f"Unknown report type '{report_type}'.")

    # ---------- writers ----------
    def _write_pdf(self, path: Path, title: str, sections) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles["Title"]),
                 Paragraph(f"Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC",
                           styles["Normal"]),
                 Spacer(1, 0.5 * cm)]
        for heading, body in sections:
            story.append(Paragraph(heading, styles["Heading2"]))
            for line in body.split("\n"):
                story.append(Paragraph(line or "&nbsp;", styles["Normal"]))
            story.append(Spacer(1, 0.4 * cm))
        SimpleDocTemplate(str(path), pagesize=A4).build(story)

    def _write_docx(self, path: Path, title: str, sections) -> None:
        import docx
        document = docx.Document()
        document.add_heading(title, level=0)
        document.add_paragraph(f"Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC")
        for heading, body in sections:
            document.add_heading(heading, level=2)
            document.add_paragraph(body)
        document.save(str(path))
