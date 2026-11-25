"""
backend/ingestion/extractors/image.py
─────────────────────────────────────────────────────────────────
Image Extractor for AeroMind 2.0 (PLAN §7.5, Task 1.3).
Extracts image dimensions, format, and runs OCR / VLM if available.
If OCR is unavailable, tags output UNCERTAIN and status PARTIAL.
Never outputs fabricated placeholder strings like "[Image: diagram]".
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional
from PIL import Image

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


def extract_image(
    file_path: Path,
    workspace_id: str,
    doc_id: Optional[str] = None,
    classification_level: str = "INTERNAL",
    ocr_engine_override: Optional[Any] = None,
) -> Document:
    """
    Extracts image metadata and OCR text from standalone image files (PNG/JPG).
    """
    start_time = time.time()
    path = Path(file_path)
    assigned_doc_id = doc_id or f"img_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}"

    source = Source(
        id=f"src_{assigned_doc_id}",
        uri=f"file://{path.resolve()}",
        source_type="image",
        file_name=path.name,
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        classification_level=classification_level,
    )

    if not path.exists():
        err = ExtractionError(
            error_code="FILE_NOT_FOUND",
            message=f"Image file not found: {path}",
            component="image_extractor",
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
        with Image.open(path) as img:
            width, height = img.size
            img_format = img.format
    except Exception as e:
        err = ExtractionError(
            error_code="UNIDENTIFIED_IMAGE",
            message=f"Cannot identify image file: {e}",
            component="image_extractor",
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

    ocr_instance = ocr_engine_override
    errors: List[ExtractionError] = []
    extracted_text = ""
    confidence = 0.0
    evidence_tag = EvidenceTag.UNCERTAIN

    if ocr_instance is None and HAS_OCR:
        try:
            ocr_instance = RapidOCR()
        except Exception as oe:
            ocr_instance = None
            errors.append(
                ExtractionError(
                    error_code="OCR_INIT_FAILED",
                    message=f"OCR engine initialization failed: {oe}",
                    component="image_extractor",
                    recoverable=True,
                )
            )

    if ocr_instance is not None:
        try:
            ocr_res, _ = ocr_instance(str(path))
            if ocr_res:
                lines = [line[1] for line in ocr_res if line and len(line) > 1]
                confidences = [float(line[2]) for line in ocr_res if line and len(line) > 2]
                extracted_text = "\n".join(lines)
                confidence = sum(confidences) / len(confidences) if confidences else 0.85
                evidence_tag = EvidenceTag.OBSERVED if confidence >= 0.70 else EvidenceTag.UNCERTAIN
        except Exception as oe:
            errors.append(
                ExtractionError(
                    error_code="OCR_EXTRACTION_ERROR",
                    message=f"OCR execution failed on image: {oe}",
                    component="image_extractor",
                    recoverable=True,
                )
            )
    else:
        errors.append(
            ExtractionError(
                error_code="OCR_UNAVAILABLE",
                message="No OCR engine installed to extract text from image.",
                component="image_extractor",
                recoverable=True,
            )
        )

    prov = Provenance(
        extractor_name="image_extractor",
        extractor_version="1.0.0",
        pipeline_stage="image_ingestion",
        execution_time_ms=(time.time() - start_time) * 1000.0,
    )

    cb = ContentBlock(
        block_type="image",
        content=extracted_text,
        media_ref=str(path.name),
        structured_data={"width": width, "height": height, "format": img_format},
        location=PageSectionLocation(page_number=1),
    )

    unit = EvidenceUnit(
        id=f"{assigned_doc_id}_p1",
        source_type="image",
        source_ref=f"{path.name}#page=1",
        extracted_text=extracted_text,
        workspace_id=workspace_id,
        classification_level=classification_level,
        content_blocks=[cb],
        evidence_tag=evidence_tag,
        location=PageSectionLocation(page_number=1),
        provenance=prov,
        confidence=confidence,
    )

    status = ProcessingStatus.COMPLETED if (ocr_instance is not None and not errors) else ProcessingStatus.PARTIAL

    return Document(
        id=assigned_doc_id,
        source=source,
        title=path.stem,
        total_pages=1,
        evidence_units=[unit],
        status=status,
        errors=errors,
    )

