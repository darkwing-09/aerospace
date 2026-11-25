"""
backend/ingestion/extractors/pdf_scanned.py
─────────────────────────────────────────────────────────────────
Scanned PDF Extractor for AeroMind 2.0 (PLAN §7.5, Task 1.3, §8.3).
Extracts text from scanned pages using OCR engine when available.
If OCR is unavailable, NEVER fabricates placeholder text (PLAN §11.5).
Emits status=PARTIAL, evidence_tag=UNCERTAIN, and an explicit ExtractionError.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    fitz = None

# OCR engine detection
try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    RapidOCR = None

from ingestion.evidence_unit import (
    ContentBlock,
    Document,
    EvidenceTag,
    EvidenceUnit,
    ExtractionError,
    PageSectionLocation,
    ProcessingStatus,
    Provenance,
    Source,
)


def extract_pdf_scanned(
    file_path: Path,
    workspace_id: str,
    doc_id: Optional[str] = None,
    classification_level: str = "INTERNAL",
    ocr_engine_override: Optional[Any] = None,
) -> Document:
    """
    Extracts text from scanned PDF pages.
    Never invents placeholder text if OCR fails.
    """
    start_time = time.time()
    path = Path(file_path)
    assigned_doc_id = doc_id or f"doc_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}"

    source = Source(
        id=f"src_{assigned_doc_id}",
        uri=f"file://{path.resolve()}",
        source_type="scanned_pdf",
        file_name=path.name,
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        classification_level=classification_level,
    )

    if not path.exists():
        err = ExtractionError(
            error_code="FILE_NOT_FOUND",
            message=f"File not found: {path}",
            component="pdf_scanned_extractor",
            recoverable=False,
        )
        return Document(
            id=assigned_doc_id,
            source=source,
            title=path.stem,
            total_pages=0,
            status=ProcessingStatus.FAILED,
            errors=[err],
        )

    if not HAS_FITZ:
        err = ExtractionError(
            error_code="DEPENDENCY_MISSING",
            message="PyMuPDF (fitz) is not installed.",
            component="pdf_scanned_extractor",
            recoverable=False,
        )
        return Document(
            id=assigned_doc_id,
            source=source,
            title=path.stem,
            total_pages=0,
            status=ProcessingStatus.FAILED,
            errors=[err],
        )

    try:
        pdf_doc = fitz.open(str(path))
    except Exception as e:
        err = ExtractionError(
            error_code="CORRUPTED_PDF",
            message=f"Failed to open PDF document: {e}",
            component="pdf_scanned_extractor",
            recoverable=False,
        )
        return Document(
            id=assigned_doc_id,
            source=source,
            title=path.stem,
            total_pages=0,
            status=ProcessingStatus.FAILED,
            errors=[err],
        )

    evidence_units: List[EvidenceUnit] = []
    errors: List[ExtractionError] = []
    total_pages = len(pdf_doc)

    ocr_instance = ocr_engine_override
    if ocr_instance is None and HAS_OCR:
        try:
            ocr_instance = RapidOCR()
        except Exception as oe:
            ocr_instance = None
            errors.append(
                ExtractionError(
                    error_code="OCR_INIT_FAILED",
                    message=f"Failed to initialize OCR engine: {oe}",
                    component="pdf_scanned_extractor",
                    recoverable=True,
                )
            )

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        unit_id = f"{assigned_doc_id}_p{page_num}"
        source_ref = f"{path.name}#page={page_num}"

        try:
            page = pdf_doc[page_idx]
            extracted_text = ""
            confidence = 0.0
            evidence_tag = EvidenceTag.UNCERTAIN

            if ocr_instance is not None:
                pix = page.get_pixmap(dpi=150)
                ocr_res, _ = ocr_instance(pix.tobytes("png"))
                if ocr_res:
                    lines = [line[1] for line in ocr_res if line and len(line) > 1]
                    confidences = [float(line[2]) for line in ocr_res if line and len(line) > 2]
                    extracted_text = "\n".join(lines)
                    confidence = sum(confidences) / len(confidences) if confidences else 0.85
                    evidence_tag = EvidenceTag.OBSERVED if confidence >= 0.70 else EvidenceTag.UNCERTAIN
            else:
                # No OCR available: record explicit error, do NOT fake text
                errors.append(
                    ExtractionError(
                        error_code="OCR_UNAVAILABLE",
                        message=f"No OCR engine available to transcribe scanned page {page_num}.",
                        component="pdf_scanned_extractor",
                        recoverable=True,
                    )
                )

            prov = Provenance(
                extractor_name="pdf_scanned_extractor",
                extractor_version="1.0.0",
                pipeline_stage="ocr_extraction",
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

            cb = ContentBlock(
                block_type="image_scan",
                content=extracted_text,
                location=PageSectionLocation(page_number=page_num),
            )

            unit = EvidenceUnit(
                id=unit_id,
                source_type="scanned_pdf",
                source_ref=source_ref,
                extracted_text=extracted_text,
                workspace_id=workspace_id,
                classification_level=classification_level,
                content_blocks=[cb],
                evidence_tag=evidence_tag,
                location=PageSectionLocation(page_number=page_num),
                provenance=prov,
                confidence=confidence,
            )
            evidence_units.append(unit)

        except Exception as pe:
            errors.append(
                ExtractionError(
                    error_code="PAGE_SCAN_ERROR",
                    message=f"Error processing page {page_num}: {pe}",
                    component="pdf_scanned_extractor",
                    recoverable=True,
                )
            )

    pdf_doc.close()

    status = ProcessingStatus.COMPLETED
    if not HAS_OCR and ocr_engine_override is None:
        status = ProcessingStatus.PARTIAL
    elif errors:
        status = ProcessingStatus.PARTIAL if evidence_units else ProcessingStatus.FAILED

    return Document(
        id=assigned_doc_id,
        source=source,
        title=path.stem,
        total_pages=total_pages,
        evidence_units=evidence_units,
        status=status,
        errors=errors,
    )
