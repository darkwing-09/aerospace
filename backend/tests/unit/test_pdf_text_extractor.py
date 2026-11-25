"""
Unit tests for PDF Text Extractor (Task 1.2 / PLAN §7.5, §11.4).
"""

from pathlib import Path
import pytest
from ingestion.evidence_unit import ProcessingStatus
from ingestion.extractors.pdf_text import extract_pdf_text

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SOP_FIXTURE_PATH = REPO_ROOT / "backend" / "tests" / "fixtures" / "maintenance_sop.pdf"


def test_extract_pdf_text_on_valid_fixture():
    assert SOP_FIXTURE_PATH.exists()
    doc = extract_pdf_text(
        file_path=SOP_FIXTURE_PATH,
        workspace_id="ws_aviation_test",
        doc_id="sop_hyd_04",
        classification_level="INTERNAL",
    )

    assert doc.id == "sop_hyd_04"
    assert doc.status == ProcessingStatus.COMPLETED
    assert doc.total_pages == 1
    assert len(doc.evidence_units) == 1

    unit = doc.evidence_units[0]
    assert unit.id == "sop_hyd_04_p1"
    assert unit.workspace_id == "ws_aviation_test"
    assert unit.classification_level == "INTERNAL"
    assert unit.source_ref == "maintenance_sop.pdf#page=1"
    assert "210 kg/cm2" in unit.extracted_text
    assert "AMG-10" in unit.extracted_text

    # Content blocks contain headings and sections
    block_types = [b.block_type for b in unit.content_blocks]
    assert "heading" in block_types


def test_missing_file_returns_failed_status_without_raising(tmp_path):
    missing_path = tmp_path / "nonexistent_file.pdf"
    doc = extract_pdf_text(file_path=missing_path, workspace_id="ws_test")

    assert doc.status == ProcessingStatus.FAILED
    assert len(doc.errors) == 1
    assert doc.errors[0].error_code == "FILE_NOT_FOUND"


def test_corrupted_file_returns_failed_status_without_raising(tmp_path):
    corrupted_path = tmp_path / "corrupted.pdf"
    corrupted_path.write_bytes(b"%PDF-1.4 not a real pdf content junk junk")

    doc = extract_pdf_text(file_path=corrupted_path, workspace_id="ws_test")

    assert doc.status == ProcessingStatus.FAILED
    assert len(doc.errors) == 1
    assert doc.errors[0].error_code == "CORRUPTED_PDF"

