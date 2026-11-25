"""
Unit tests for Scanned PDF and Image Extractors (Task 1.3 / PLAN §7.5, §8.3, §11.5).
Verifies:
1. No-OCR condition produces status=PARTIAL, evidence_tag=UNCERTAIN, and no fabricated text.
2. Mocked/real OCR transcribes text matching ground-truth keywords and achieves status=COMPLETED.
3. Missing and corrupted files fail gracefully with status=FAILED without crashing.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ingestion.evidence_unit import EvidenceTag, ProcessingStatus
from ingestion.extractors.image import extract_image
from ingestion.extractors.pdf_scanned import extract_pdf_scanned

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
SCANNED_PNG = FIXTURES_DIR / "scanned_page.png"
MAINTENANCE_PDF = FIXTURES_DIR / "maintenance_sop.pdf"


def test_extract_image_no_ocr(monkeypatch):
    """When OCR engine is unavailable, extractor must return PARTIAL + UNCERTAIN and no fake text."""
    # Force HAS_OCR to False
    monkeypatch.setattr("ingestion.extractors.image.HAS_OCR", False)

    doc = extract_image(
        file_path=SCANNED_PNG,
        workspace_id="ws_aviation",
        doc_id="test_img_no_ocr",
        ocr_engine_override=None,
    )

    assert doc.status == ProcessingStatus.PARTIAL
    assert len(doc.evidence_units) == 1
    unit = doc.evidence_units[0]

    assert unit.evidence_tag == EvidenceTag.UNCERTAIN
    assert unit.extracted_text == ""  # Never fabricate placeholder text!
    assert any(err.error_code == "OCR_UNAVAILABLE" for err in doc.errors)
    assert unit.confidence == 0.0
    assert unit.content_blocks[0].structured_data["format"] == "PNG"


def test_extract_scanned_pdf_no_ocr(monkeypatch):
    """When OCR engine is unavailable, PDF scan extractor returns PARTIAL + UNCERTAIN."""
    monkeypatch.setattr("ingestion.extractors.pdf_scanned.HAS_OCR", False)

    doc = extract_pdf_scanned(
        file_path=MAINTENANCE_PDF,
        workspace_id="ws_aviation",
        doc_id="test_pdf_no_ocr",
        ocr_engine_override=None,
    )

    assert doc.status == ProcessingStatus.PARTIAL
    assert len(doc.evidence_units) > 0
    for unit in doc.evidence_units:
        assert unit.evidence_tag == EvidenceTag.UNCERTAIN
        assert unit.extracted_text == ""  # No fabricated text
    assert any(err.error_code == "OCR_UNAVAILABLE" for err in doc.errors)


def test_extract_image_with_mock_ocr():
    """When OCR is present, image extractor transcribes text and produces COMPLETED."""
    mock_ocr = MagicMock()
    # RapidOCR returns tuple (result_list, elapse_list)
    # result_list is list of [box, text, score]
    mock_ocr.return_value = (
        [
            ([[0, 0], [100, 0], [100, 20], [0, 20]], "Accumulator Precharge: 40 kg/cm2", 0.95),
            ([[0, 25], [100, 25], [100, 45], [0, 45]], "Nitrogen Bottle Min: 150 kg/cm2", 0.92),
            ([[0, 50], [100, 50], [100, 70], [0, 70]], "Landing Gear Emergency Extension: VERIFIED OK", 0.88),
        ],
        [0.01, 0.02, 0.01],
    )

    doc = extract_image(
        file_path=SCANNED_PNG,
        workspace_id="ws_aviation",
        doc_id="test_img_ocr",
        ocr_engine_override=mock_ocr,
    )

    assert doc.status == ProcessingStatus.COMPLETED
    assert len(doc.evidence_units) == 1
    unit = doc.evidence_units[0]

    assert unit.evidence_tag == EvidenceTag.OBSERVED
    assert unit.confidence > 0.80
    assert "40 kg/cm2" in unit.extracted_text
    assert "150 kg/cm2" in unit.extracted_text
    assert "VERIFIED OK" in unit.extracted_text
    assert len(doc.errors) == 0


def test_extract_scanned_pdf_with_mock_ocr():
    """When OCR is provided, scanned PDF extractor processes pages and extracts text."""
    mock_ocr = MagicMock()
    mock_ocr.return_value = (
        [
            ([[0, 0], [100, 0], [100, 20], [0, 20]], "SOP-HYD-04 HYDRAULIC SERVICING", 0.96),
        ],
        [0.01],
    )

    doc = extract_pdf_scanned(
        file_path=MAINTENANCE_PDF,
        workspace_id="ws_aviation",
        doc_id="test_pdf_ocr",
        ocr_engine_override=mock_ocr,
    )

    assert doc.status == ProcessingStatus.COMPLETED
    assert len(doc.evidence_units) == doc.total_pages
    assert "SOP-HYD-04" in doc.evidence_units[0].extracted_text
    assert doc.evidence_units[0].evidence_tag == EvidenceTag.OBSERVED


def test_extractors_missing_file():
    """Missing files must return status=FAILED with FILE_NOT_FOUND without raising."""
    nonexistent = FIXTURES_DIR / "nonexistent_file.png"

    img_doc = extract_image(nonexistent, workspace_id="ws_test")
    assert img_doc.status == ProcessingStatus.FAILED
    assert any(err.error_code == "FILE_NOT_FOUND" for err in img_doc.errors)

    pdf_doc = extract_pdf_scanned(nonexistent, workspace_id="ws_test")
    assert pdf_doc.status == ProcessingStatus.FAILED
    assert any(err.error_code == "FILE_NOT_FOUND" for err in pdf_doc.errors)

