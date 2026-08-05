from app.rag.chunker import Chunker
from app.rag.citation_engine import CitationEngine
from app.rag.retriever import RetrievedChunk
from app.services.classification_service import ClassificationService
from app.services.metadata_service import MetadataService
from app.services.text_cleaning import clean_text


def test_clean_text_collapses_whitespace():
    assert clean_text("hello    world\n\n\n\nagain") == "hello world\n\nagain"


def test_metadata_extracts_entities():
    pages = [{"page_number": 1,
              "text": "Invoice dated 2024-03-15. Pay $4,500 to billing@acme.com."}]
    meta = MetadataService().extract("invoice_march.pdf", pages)
    assert "2024-03-15" in meta["entities"]["dates"]
    assert "billing@acme.com" in meta["entities"]["emails"]
    assert any("4,500" in a for a in meta["entities"]["amounts"])


def test_classifier_detects_finance():
    pages = [{"page_number": 1,
              "text": "invoice payment revenue expense budget tax audit invoice payment"}]
    assert ClassificationService().classify(pages, []) == "finance"


def test_chunker_preserves_page_numbers():
    pages = [{"page_number": 3, "text": "word " * 600}]
    chunks = Chunker().chunk_pages(pages)
    assert len(chunks) > 1
    assert all(c["page_number"] == 3 for c in chunks)


def test_citation_engine_maps_markers():
    chunks = [RetrievedChunk(1, 10, "doc.pdf", 2, "alpha text", 0.9),
              RetrievedChunk(2, 10, "doc.pdf", 5, "beta text", 0.8)]
    citations = CitationEngine().extract("Fact one [1]. Fact two [2]. Again [1].", chunks)
    assert [c["marker"] for c in citations] == ["[1]", "[2]"]
    assert citations[1]["page_number"] == 5
