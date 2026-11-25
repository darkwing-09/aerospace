"""
backend/ingestion/extractors/csv_xlsx.py
─────────────────────────────────────────────────────────────────
CSV and XLSX Extractor for AeroMind 2.0 (PLAN §7.5, Task 1.4).
Preserves tabular structure losslessly without truncation.
Chunks large tables into 20-row EvidenceUnits while preserving headers on every chunk.
Fixes the 15-row truncation bug in legacy ingestion_adapter.py:180.
"""

from __future__ import annotations

import csv
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

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


def _format_markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Formats headers and rows into clean markdown table text."""
    if not headers and not rows:
        return ""
    
    clean_headers = [str(h).strip() if h is not None else "" for h in headers]
    lines = ["| " + " | ".join(clean_headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(clean_headers)) + " |")

    for row in rows:
        # Pad or trim row to match header length
        padded = list(row) + [""] * max(0, len(clean_headers) - len(row))
        padded = padded[:len(clean_headers)]
        row_str = [str(c).replace("\n", " ").strip() if c is not None else "" for c in padded]
        lines.append("| " + " | ".join(row_str) + " |")

    return "\n".join(lines)


def _extract_csv_rows(path: Path) -> Tuple[List[str], List[List[str]]]:
    """Reads CSV file handling various encodings."""
    encodings = ["utf-8", "utf-8-sig", "latin-1"]
    last_err = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.reader(f)
                all_rows = [row for row in reader if any(cell.strip() for cell in row)]
                if not all_rows:
                    return [], []
                headers = all_rows[0]
                rows = all_rows[1:]
                return headers, rows
        except Exception as e:
            last_err = e
            continue
    raise last_err or ValueError(f"Failed to read CSV at {path}")


def _extract_xlsx_sheets(path: Path) -> Dict[str, Tuple[List[str], List[List[Any]]]]:
    """Reads XLSX sheets using openpyxl, extracting headers and rows."""
    if not HAS_OPENPYXL:
        raise ImportError("openpyxl is required to extract XLSX files.")

    wb = openpyxl.load_workbook(path, data_only=True)
    sheets_data = {}

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        raw_rows = []
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                raw_rows.append([cell for cell in row])

        if not raw_rows:
            continue

        # Header detection: find first row with >= 2 non-empty columns, or row 0
        header_idx = 0
        for idx, row in enumerate(raw_rows):
            non_empty = [c for c in row if c is not None and str(c).strip() != ""]
            if len(non_empty) >= 2:
                header_idx = idx
                break

        headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(raw_rows[header_idx])]
        data_rows = raw_rows[header_idx + 1:]
        sheets_data[sheet_name] = (headers, data_rows)

    wb.close()
    return sheets_data


def extract_csv_xlsx(
    file_path: Path,
    workspace_id: str,
    doc_id: Optional[str] = None,
    classification_level: str = "INTERNAL",
    chunk_rows: int = 20,
) -> Document:
    """
    Extracts tabular data from CSV or XLSX files into structured EvidenceUnits.
    Chunks into 20-row segments while preserving header context on each chunk.
    Never truncates at 15 rows.
    """
    start_time = time.time()
    path = Path(file_path)
    suffix = path.suffix.lower()
    source_type = "csv" if suffix == ".csv" else "xlsx"
    assigned_doc_id = doc_id or f"{source_type}_{hashlib.sha256(str(path).encode('utf-8')).hexdigest()[:12]}"

    source = Source(
        id=f"src_{assigned_doc_id}",
        uri=f"file://{path.resolve()}",
        source_type=source_type,
        file_name=path.name,
        file_size_bytes=path.stat().st_size if path.exists() else 0,
        classification_level=classification_level,
    )

    if not path.exists():
        err = ExtractionError(
            error_code="FILE_NOT_FOUND",
            message=f"File not found: {path}",
            component="csv_xlsx_extractor",
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

    try:
        if suffix == ".csv":
            headers, rows = _extract_csv_rows(path)
            sheets_dict = {"Main": (headers, rows)}
        elif suffix in (".xlsx", ".xls"):
            sheets_dict = _extract_xlsx_sheets(path)
        else:
            raise ValueError(f"Unsupported spreadsheet format: {suffix}")
    except Exception as e:
        err = ExtractionError(
            error_code="PARSE_ERROR",
            message=f"Failed to parse tabular file {path.name}: {e}",
            component="csv_xlsx_extractor",
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

    for sheet_name, (headers, rows) in sheets_dict.items():
        total_rows = len(rows)
        if total_rows == 0:
            # Empty table: single unit with headers only
            chunk_chunks = [[]]
        else:
            # Chunk into chunk_rows (default 20)
            chunk_chunks = [rows[i : i + chunk_rows] for i in range(0, total_rows, chunk_rows)]

        for c_idx, chunk_data in enumerate(chunk_chunks):
            start_row = c_idx * chunk_rows + 1
            end_row = start_row + len(chunk_data) - 1 if chunk_data else start_row
            sheet_slug = sheet_name.replace(" ", "_")
            unit_id = f"{assigned_doc_id}_{sheet_slug}_r{start_row}_{end_row}"

            if suffix == ".csv":
                source_ref = f"{path.name}#rows={start_row}-{end_row}"
            else:
                source_ref = f"{path.name}#sheet={sheet_name}&rows={start_row}-{end_row}"

            markdown_content = _format_markdown_table(headers, chunk_data)

            # Convert row list to list of dicts for structured data
            row_dicts = []
            for r in chunk_data:
                padded = list(r) + [""] * max(0, len(headers) - len(r))
                row_dicts.append({headers[i]: padded[i] for i in range(len(headers))})

            cb = ContentBlock(
                block_type="table",
                content=markdown_content,
                structured_data={
                    "sheet": sheet_name,
                    "columns": headers,
                    "rows": row_dicts,
                    "start_row": start_row,
                    "end_row": end_row,
                    "total_rows": total_rows,
                },
                location=PageSectionLocation(
                    row_index=start_row,
                    section_path=[sheet_name] if suffix != ".csv" else [],
                ),
            )

            prov = Provenance(
                extractor_name="csv_xlsx_extractor",
                extractor_version="1.0.0",
                pipeline_stage="table_ingestion",
                execution_time_ms=(time.time() - start_time) * 1000.0,
            )

            unit = EvidenceUnit(
                id=unit_id,
                source_type=source_type,
                source_ref=source_ref,
                extracted_text=markdown_content,
                workspace_id=workspace_id,
                classification_level=classification_level,
                content_blocks=[cb],
                evidence_tag=EvidenceTag.OBSERVED,
                location=PageSectionLocation(
                    row_index=start_row,
                    section_path=[sheet_name] if suffix != ".csv" else [],
                ),
                provenance=prov,
                confidence=1.0,
            )
            evidence_units.append(unit)

    return Document(
        id=assigned_doc_id,
        source=source,
        title=path.stem,
        total_pages=len(sheets_dict),
        evidence_units=evidence_units,
        status=ProcessingStatus.COMPLETED if evidence_units else ProcessingStatus.PARTIAL,
        errors=errors,
    )
