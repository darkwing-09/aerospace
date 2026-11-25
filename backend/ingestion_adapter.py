"""
ingestion_adapter.py
─────────────────────────────────────────────────────────────────
Universal Ingestion Adapter Layer for AeroMind.

Normalizes arbitrary file types (DOCX, XLSX, CSV, Images, ZIP)
into standardized PDF/image structures for ColPali Visual RAG
and multi-agent analysis.
"""

import os
import io
import re
import json
import zipfile
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

import fitz  # PyMuPDF
import pandas as pd
from PIL import Image

from config import settings
from visual_rag_service import visual_rag_service
from security.paths import UnsafePathError, safe_join


class UnsafeArchiveError(ValueError):
    """Raised when an uploaded archive exceeds limits or contains unsafe members (QW3)."""


_ARCHIVE_EXTS = (".zip", ".tar", ".gz", ".tgz", ".7z", ".rar")


class IngestionAdapter:
    def __init__(self):
        self.temp_dir = Path(settings.DATA_DIR) / "adapter_scratch"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.session_docs: Dict[str, Dict[str, Any]] = {}

    def normalize_to_pdf_or_image(
        self,
        input_path: Path,
        doc_id: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Takes any input file and produces a standardized document package:
        {
            "doc_id": doc_id,
            "session_id": session_id,
            "original_filename": input_path.name,
            "file_type": ext,
            "pdf_path": Optional[Path],
            "image_paths": List[Path],
            "total_pages": int,
            "tables": List[Dict],
            "extracted_text": str,
            "metadata": Dict[str, Any]
        }
        """
        ext = input_path.suffix.lower()
        output_dir = self.temp_dir / doc_id
        output_dir.mkdir(parents=True, exist_ok=True)

        if ext == ".pdf":
            return self._process_pdf(input_path, doc_id, session_id)
        elif ext in [".docx", ".doc"]:
            return self._process_docx(input_path, doc_id, session_id, output_dir)
        elif ext in [".xlsx", ".xls"]:
            return self._process_xlsx(input_path, doc_id, session_id, output_dir)
        elif ext in [".csv", ".tsv"]:
            return self._process_csv(input_path, doc_id, session_id, output_dir)
        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
            return self._process_image(input_path, doc_id, session_id, output_dir)
        elif ext == ".zip":
            return self._process_zip(input_path, doc_id, session_id, output_dir)
        elif ext in [".txt", ".md", ".log", ".json"]:
            return self._process_text_file(input_path, doc_id, session_id, output_dir)
        else:
            # Attempt generic text conversion
            return self._process_text_file(input_path, doc_id, session_id, output_dir)

    def _process_pdf(self, input_path: Path, doc_id: str, session_id: Optional[str]) -> Dict[str, Any]:
        doc = fitz.open(str(input_path))
        num_pages = len(doc)
        doc.close()

        # Render images via VisualRAGService
        index_meta = visual_rag_service.index_document(input_path, doc_id)
        image_paths = [
            visual_rag_service.get_page_image_path(doc_id, p["page_number"])
            for p in index_meta.get("pages", [])
        ]

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "pdf",
            "pdf_path": input_path,
            "image_paths": image_paths,
            "total_pages": num_pages,
            "tables": [],
            "extracted_text": "",
            "metadata": {"source": "pdf"},
        }

    def _process_docx(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        pdf_out = output_dir / f"{doc_id}.pdf"
        converted = self._try_libreoffice_convert(input_path, output_dir)

        if not converted or not pdf_out.exists():
            # Python fallback conversion using python-docx and reportlab
            pdf_out = self._docx_to_pdf_python(input_path, pdf_out)

        if pdf_out.exists():
            return self._process_pdf(pdf_out, doc_id, session_id)

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "docx",
            "pdf_path": None,
            "image_paths": [],
            "total_pages": 1,
            "tables": [],
            "extracted_text": "",
            "metadata": {"source": "docx"},
        }

    def _process_xlsx(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        pdf_out = output_dir / f"{doc_id}.pdf"
        # Read Excel sheets and build clean PDF table report
        try:
            excel_file = pd.ExcelFile(input_path)
            sheet_summaries = []
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(input_path, sheet_name=sheet_name)
                sheet_summaries.append({
                    "sheet": sheet_name,
                    "rows": len(df),
                    "columns": list(df.columns),
                    "preview": df.head(10).to_dict(orient="records"),
                })
            self._table_to_pdf_report(sheet_summaries, pdf_out, title=input_path.name)
            if pdf_out.exists():
                res = self._process_pdf(pdf_out, doc_id, session_id)
                res["tables"] = sheet_summaries
                res["file_type"] = "xlsx"
                return res
        except Exception as e:
            print(f"[IngestionAdapter] Error converting XLSX to PDF: {e}")

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "xlsx",
            "pdf_path": None,
            "image_paths": [],
            "total_pages": 1,
            "tables": [],
            "extracted_text": "",
            "metadata": {"source": "xlsx"},
        }

    def _process_csv(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        pdf_out = output_dir / f"{doc_id}.pdf"
        try:
            df = pd.read_csv(input_path)
            table_summary = [{
                "sheet": "Main",
                "rows": len(df),
                "columns": list(df.columns),
                "preview": df.head(15).to_dict(orient="records"),
            }]
            self._table_to_pdf_report(table_summary, pdf_out, title=input_path.name)
            if pdf_out.exists():
                res = self._process_pdf(pdf_out, doc_id, session_id)
                res["tables"] = table_summary
                res["file_type"] = "csv"
                return res
        except Exception as e:
            print(f"[IngestionAdapter] CSV parse error: {e}")

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "csv",
            "pdf_path": None,
            "image_paths": [],
            "total_pages": 1,
            "tables": [],
            "extracted_text": "",
            "metadata": {"source": "csv"},
        }

    def _process_image(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        """Direct ColPali embedding without rasterization."""
        cache_dir = visual_rag_service.get_document_cache_dir(doc_id)
        target_img = cache_dir / "page_1.png"
        target_thumb = cache_dir / "thumb_1.jpg"

        with Image.open(input_path) as img:
            rgb_img = img.convert("RGB")
            rgb_img.save(target_img, "PNG")
            thumb_copy = rgb_img.copy()
            thumb_copy.thumbnail((120, 120))
            thumb_copy.save(target_thumb, "JPEG")

        # Also create a single-page PDF wrapper for the viewer
        pdf_out = output_dir / f"{doc_id}.pdf"
        try:
            doc = fitz.open()
            page = doc.new_page(width=img.width, height=img.height)
            page.insert_image(page.rect, filename=str(target_img))
            doc.save(str(pdf_out))
            doc.close()
        except Exception as e:
            print(f"[IngestionAdapter] Image PDF wrapper note: {e}")

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "image",
            "pdf_path": pdf_out if pdf_out.exists() else None,
            "image_paths": [target_img],
            "total_pages": 1,
            "tables": [],
            "extracted_text": f"Direct visual image schematic {input_path.name}",
            "metadata": {"source": "image", "is_schematic": True},
        }

    def _process_zip(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        """Unpack ZIP archive and process each child file."""
        extracted_dir = output_dir / "unpacked"
        extracted_dir.mkdir(parents=True, exist_ok=True)

        child_packages = []
        self._safe_extract_zip(input_path, extracted_dir)

        for root, _, files in os.walk(extracted_dir):
            for f in files:
                child_file = Path(root) / f
                if child_file.is_file() and not child_file.name.startswith("."):
                    child_id = f"{doc_id}_{child_file.stem}".replace(" ", "_").lower()
                    child_pkg = self.normalize_to_pdf_or_image(
                        child_file, child_id, session_id=session_id
                    )
                    child_packages.append(child_pkg)

        # Merge or return master zip package
        first_pdf = next((cp["pdf_path"] for cp in child_packages if cp.get("pdf_path")), None)
        all_images = [img for cp in child_packages for img in cp.get("image_paths", [])]

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "zip",
            "pdf_path": first_pdf,
            "image_paths": all_images,
            "total_pages": sum(cp.get("total_pages", 0) for cp in child_packages) or 1,
            "child_documents": child_packages,
            "tables": [t for cp in child_packages for t in cp.get("tables", [])],
            "extracted_text": f"Archive containing {len(child_packages)} documents.",
            "metadata": {"source": "zip", "file_count": len(child_packages)},
        }

    def _process_text_file(
        self, input_path: Path, doc_id: str, session_id: Optional[str], output_dir: Path
    ) -> Dict[str, Any]:
        pdf_out = output_dir / f"{doc_id}.pdf"
        try:
            with open(input_path, "r", encoding="utf-8", errors="ignore") as tf:
                text_content = tf.read()
            self._text_to_pdf(text_content, pdf_out, title=input_path.name)
            if pdf_out.exists():
                res = self._process_pdf(pdf_out, doc_id, session_id)
                res["extracted_text"] = text_content[:2000]
                return res
        except Exception as e:
            print(f"[IngestionAdapter] Text to PDF error: {e}")

        return {
            "doc_id": doc_id,
            "session_id": session_id,
            "name": input_path.stem,
            "original_filename": input_path.name,
            "file_type": "text",
            "pdf_path": None,
            "image_paths": [],
            "total_pages": 1,
            "tables": [],
            "extracted_text": "",
            "metadata": {"source": "text"},
        }

    def _safe_extract_zip(self, zip_path: Path, dest: Path) -> None:
        """Extract with hard limits instead of zipfile.extractall (QW3).

        Why: extractall has no size/member limits (zip bombs) and the old code
        recursed into nested archives without bound. Limits come from config;
        sizes are enforced while streaming, so a member that lies about its
        declared size in the header is still stopped.
        """
        max_members = settings.ZIP_MAX_MEMBERS
        budget = settings.ZIP_MAX_UNCOMPRESSED_MB * 1024 * 1024
        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except zipfile.BadZipFile as e:
            raise UnsafeArchiveError(f"Not a valid ZIP archive: {e}")
        with zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            if len(members) > max_members:
                raise UnsafeArchiveError(f"Archive has {len(members)} files; the limit is {max_members}.")
            declared = sum(m.file_size for m in members)
            if declared > budget:
                raise UnsafeArchiveError(
                    f"Archive expands to {declared // (1024 * 1024)} MB; the limit is {settings.ZIP_MAX_UNCOMPRESSED_MB} MB."
                )
            for m in members:
                if (m.external_attr >> 16) & 0o170000 == 0o120000:
                    raise UnsafeArchiveError(f"Archive member {m.filename!r} is a symbolic link.")
                if m.filename.lower().endswith(_ARCHIVE_EXTS):
                    raise UnsafeArchiveError(f"Nested archives are not allowed ({m.filename!r}).")
                if m.filename.startswith(("/", "\\")) or ".." in Path(m.filename).parts:
                    raise UnsafeArchiveError(f"Archive member {m.filename!r} has an unsafe path.")
            written = 0
            for m in members:
                try:
                    target = safe_join(dest, m.filename)
                except UnsafePathError as e:
                    raise UnsafeArchiveError(f"Archive member {m.filename!r}: {e}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, open(target, "wb") as out:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > budget:
                            raise UnsafeArchiveError(
                                f"Archive expands beyond the {settings.ZIP_MAX_UNCOMPRESSED_MB} MB limit."
                            )
                        out.write(chunk)

    # ── Conversion Helpers ─────────────────────────────────────────

    def _try_libreoffice_convert(self, input_path: Path, output_dir: Path) -> bool:
        for cmd in ["soffice", "libreoffice"]:
            try:
                proc = subprocess.run(
                    [cmd, "--headless", "--convert-to", "pdf", str(input_path), "--outdir", str(output_dir)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                )
                if proc.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    def _docx_to_pdf_python(self, docx_path: Path, pdf_path: Path) -> Path:
        try:
            import docx
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            doc_obj = docx.Document(str(docx_path))
            pdf_doc = SimpleDocTemplate(str(pdf_path), pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            styles = getSampleStyleSheet()

            story = []
            title_style = ParagraphStyle(
                'DocTitle',
                parent=styles['Heading1'],
                fontSize=16,
                leading=20,
                textColor=colors.HexColor('#e8780a'),
                spaceAfter=12
            )
            body_style = ParagraphStyle(
                'DocBody',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor('#222222'),
                spaceAfter=8
            )

            story.append(Paragraph(docx_path.name, title_style))
            story.append(Spacer(1, 10))

            for p in doc_obj.paragraphs:
                if p.text.strip():
                    story.append(Paragraph(p.text, body_style))

            for t in doc_obj.tables:
                table_data = []
                for row in t.rows:
                    table_data.append([cell.text.strip() for cell in row.cells])
                if table_data:
                    rt = Table(table_data)
                    rt.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f0f4f8')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#111827')),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('FONTSIZE', (0,0), (-1,-1), 8),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#d1d5db')),
                    ]))
                    story.append(Spacer(1, 8))
                    story.append(rt)
                    story.append(Spacer(1, 8))

            pdf_doc.build(story)
            return pdf_path
        except Exception as e:
            print(f"[IngestionAdapter] Python docx-to-pdf fallback note: {e}")
            return pdf_path

    def _table_to_pdf_report(self, sheets: List[Dict], pdf_path: Path, title: str):
        try:
            from reportlab.lib.pagesizes import letter, landscape
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            pdf_doc = SimpleDocTemplate(str(pdf_path), pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            styles = getSampleStyleSheet()
            story = []

            title_style = ParagraphStyle(
                'ReportTitle',
                parent=styles['Heading1'],
                fontSize=14,
                leading=18,
                textColor=colors.HexColor('#e8780a'),
                spaceAfter=10
            )

            story.append(Paragraph(f"Data Manifest: {title}", title_style))
            story.append(Spacer(1, 8))

            for sheet in sheets:
                story.append(Paragraph(f"Sheet: {sheet['sheet']} ({sheet['rows']} Rows)", styles['Heading3']))
                cols = sheet['columns'][:8]  # Limit to 8 cols for landscape fit
                preview = sheet['preview']
                t_data = [cols]
                for row in preview:
                    t_data.append([str(row.get(c, ''))[:30] for c in cols])

                if t_data:
                    rt = Table(t_data)
                    rt.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('FONTSIZE', (0,0), (-1,-1), 7),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#9ca3af')),
                    ]))
                    story.append(rt)
                    story.append(Spacer(1, 12))

            pdf_doc.build(story)
        except Exception as e:
            print(f"[IngestionAdapter] Table to PDF generation note: {e}")

    def _text_to_pdf(self, text: str, pdf_path: Path, title: str):
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors

            pdf_doc = SimpleDocTemplate(str(pdf_path), pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
            styles = getSampleStyleSheet()
            story = []

            story.append(Paragraph(title, styles['Heading2']))
            story.append(Spacer(1, 10))

            body_style = ParagraphStyle('Mono', parent=styles['Normal'], fontSize=9, leading=12)
            for line in text.split('\n'):
                if line.strip():
                    story.append(Paragraph(line.replace('<', '&lt;').replace('>', '&gt;'), body_style))

            pdf_doc.build(story)
        except Exception as e:
            print(f"[IngestionAdapter] Text to PDF note: {e}")


ingestion_adapter = IngestionAdapter()
