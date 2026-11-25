"""
backend/ingestion/extractors/pdf_text.py
─────────────────────────────────────────────────────────────────
Text PDF Extractor for AeroMind 2.0 (PLAN §7.5, Task 1.2, §11.4).
Emits one EvidenceUnit per page ({doc_id}_p{page_num}) with headings,
locations, and structured content blocks.
Extractors NEVER raise exceptions — failures return Document(status=FAILED, errors=[...]).
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    fitz = None

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


def extract_pdf_text(
    file_path: Path,
    workspace_id: str,
    doc_id: Optional[str] = None,
    classification_level: str = "INTERNAL",
) -> Document:
    """
    Extracts text and headings from a digital PDF file into a Document with EvidenceUnits.
    Never raises an uncaught exception.
    """
    start_time = time.time()
    path = Path(file_path)
    assigned_doc_id = doc_id or f"doc_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}"

    source = Source(
        id=f"src_{assigned_doc_id}",
        uri=f"file://{path.resolve()}",
        source_type="pdf",
        file_name=path.name,
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        classification_level=classification_level,
    )

    if not path.exists():
        err = ExtractionError(
            error_code="FILE_NOT_FOUND",
            message=f"File not found: {path}",
            component="pdf_text_extractor",
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
            message="PyMuPDF (fitz) is not installed in the environment.",
            component="pdf_text_extractor",
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
        # Check if file has non-zero size
        if path.stat().st_size == 0:
            err = ExtractionError(
                error_code="CORRUPTED_PDF",
                message="PDF file is empty (0 bytes).",
                component="pdf_text_extractor",
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

        pdf_doc = fitz.open(str(path))
    except Exception as e:
        err = ExtractionError(
            error_code="CORRUPTED_PDF",
            message=f"Failed to open PDF document: {e}",
            component="pdf_text_extractor",
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

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        unit_id = f"{assigned_doc_id}_p{page_num}"
        source_ref = f"{path.name}#page={page_num}"

        try:
            page = pdf_doc[page_idx]
            page_text = page.get_text() or ""
            blocks_raw = page.get_text("blocks") or []

            content_blocks: List[ContentBlock] = []
            current_section = []

            for b in blocks_raw:
                # b format: (x0, y0, x1, y1, text, block_no, block_type)
                text = b[4].strip() if len(b) > 4 and isinstance(b[4], str) else ""
                if not text:
                    continue

                bbox = (float(b[0]), float(b[1]), float(b[2]), float(b[3])) if len(b) >= 4 else None
                is_heading = False

                # Heuristic: numbered sections like "1. Scope" or "2. Safety"
                lines = text.splitlines()
                first_line = lines[0].strip() if lines else ""
                if first_line and (first_line[0].isdigit() and "." in first_line[:4]) or len(text) < 60 and first_line.isupper():
                    is_heading = True
                    current_section = [first_line]

                loc = PageSectionLocation(
                    page_number=page_num,
                    bounding_box=bbox,
                    section_path=list(current_section),
                )

                content_blocks.append(
                    ContentBlock(
                        block_type="heading" if is_heading else "text",
                        content=text,
                        location=loc,
                    )
                )

            prov = Provenance(
                extractor_name="pdf_text_extractor",
                extractor_version="1.0.0",
                pipeline_stage="ingestion",
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

            unit = EvidenceUnit(
                id=unit_id,
                source_type="pdf",
                source_ref=source_ref,
                extracted_text=page_text.strip(),
                workspace_id=workspace_id,
                classification_level=classification_level,
                content_blocks=content_blocks,
                evidence_tag=EvidenceTag.OBSERVED,
                location=PageSectionLocation(page_number=page_num),
                provenance=prov,
                confidence=1.0,
            )
            evidence_units.append(unit)

        except Exception as pe:
            errors.append(
                ExtractionError(
                    error_code="PAGE_PARSING_ERROR",
                    message=f"Error parsing page {page_num}: {pe}",
                    component="pdf_text_extractor",
                    recoverable=True,
                )
            )

    pdf_doc.close()

    status = ProcessingStatus.COMPLETED
    if errors:
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

