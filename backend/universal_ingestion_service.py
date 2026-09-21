"""
universal_ingestion_service.py
─────────────────────────────────────────────────────────────────
Universal Multi-Format Document Ingestion Engine for Army & Defense Datasets.

Supports:
- PDF (Aviation manuals, technical schematics)
- DOCX (Standard Operating Procedures, NATO checklists)
- CSV / XLSX (Inventory manifests, ammunition counts, telemetry)
- JSON (Tactical data, avionics schemas, flight plans)
- TXT / LOG / MD (Flight recorder dumps, maintenance logs)
- Images: PNG / JPG (Cockpit photos, blueprint schematics)
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import fitz  # PyMuPDF
import pandas as pd

from config import settings
from visual_rag_service import visual_rag_service


class UniversalIngestionService:
    def __init__(self):
        self.uploads_dir = Path(settings.UPLOADS_DIR)
        self.pdf_dir = Path(settings.PDF_DIR)
        self.registry_file = Path(settings.DATA_DIR) / "document_registry.json"
        self.documents: Dict[str, Dict[str, Any]] = {}
        self._load_registry()
        self._seed_default_manuals()

    def _load_registry(self):
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self.documents = json.load(f)
            except Exception as e:
                print(f"[Ingestion] Error loading registry: {e}")
                self.documents = {}

    def _save_registry(self):
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, indent=2)
        except Exception as e:
            print(f"[Ingestion] Error saving registry: {e}")

    def _seed_default_manuals(self):
        """Register any existing PDFs in backend/pdfs."""
        mig_pdf = self.pdf_dir / "mig21bis.pdf"
        if mig_pdf.exists() and "mig21bis" not in self.documents:
            self.documents["mig21bis"] = {
                "id": "mig21bis",
                "name": "MiG-21bis Flight & Systems Manual",
                "filename": "mig21bis.pdf",
                "file_path": str(mig_pdf),
                "file_type": "pdf",
                "category": "AIRCRAFT_MANUAL",
                "description": "Tactical flight operations, cockpit instruments, and Tumansky R25-300 engine maintenance.",
                "size_mb": round(os.path.getsize(mig_pdf) / (1024 * 1024), 2),
                "total_pages": 330,
                "accent_color": "#e8780a",
                "nato_name": "FISHBED",
                "engine": "Tumansky R25-300",
                "tags": ["fighter", "supersonic", "soviet", "manual", "cockpit"],
                "created_at": "2026-08-30",
            }
            self._save_registry()

    def list_all_documents(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        docs = list(self.documents.values())
        if category:
            docs = [d for d in docs if d.get("category") == category]
        return docs

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.documents.get(doc_id)

    async def ingest_file(
        self,
        file_obj,
        filename: str,
        category: str = "AIRCRAFT_MANUAL",
        custom_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ingests any file into the defense data repository, automatically
        parsing its content and indexing it for multi-agent RAG.
        """
        ext = Path(filename).suffix.lower()
        doc_id = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")

        # Determine target directory
        if ext == ".pdf":
            dest = self.pdf_dir / filename
        else:
            dest = self.uploads_dir / filename

        content = await file_obj.read() if hasattr(file_obj, "read") else file_obj
        with open(dest, "wb") as f:
            f.write(content)

        file_size_mb = round(os.path.getsize(dest) / (1024 * 1024), 2)
        parsed_meta: Dict[str, Any] = {
            "id": doc_id,
            "name": custom_name or filename,
            "filename": filename,
            "file_path": str(dest),
            "file_type": ext.replace(".", ""),
            "category": category,
            "description": description or f"Imported {ext.upper()} defense data record.",
            "size_mb": file_size_mb,
            "tags": [ext.replace(".", ""), category.lower()],
            "created_at": "2026-08-30",
        }

        # ── Format-Specific Parser ──────────────────────────────
        if ext == ".pdf":
            try:
                doc = fitz.open(str(dest))
                parsed_meta["total_pages"] = len(doc)
                doc.close()
                # Trigger ColPali layout & multi-vector indexing
                index_meta = visual_rag_service.index_document(dest, doc_id)
                try:
                    from colpali_retrieval_service import colpali_retrieval_service
                    pages_meta = index_meta.get("pages", [])
                    image_paths = {
                        p["page_number"]: visual_rag_service.get_page_image_path(doc_id, p["page_number"])
                        for p in pages_meta
                    }
                    colpali_retrieval_service.index_document_pages(doc_id, pages_meta, image_paths)
                except Exception as ci_err:
                    print(f"[Ingestion] ColPali indexing note: {ci_err}")
            except Exception as e:
                parsed_meta["total_pages"] = 0
                print(f"[Ingestion] Error parsing PDF {filename}: {e}")

        elif ext in [".csv", ".tsv", ".xlsx", ".xls"]:
            parsed_meta["category"] = "LOGISTICS_INVENTORY"
            try:
                if ext in [".csv", ".tsv"]:
                    df = pd.read_csv(dest)
                else:
                    df = pd.read_excel(dest)

                parsed_meta["table_summary"] = {
                    "row_count": len(df),
                    "columns": list(df.columns),
                    "preview_sample": df.head(5).to_dict(orient="records"),
                }
                parsed_meta["description"] = f"Tabular dataset with {len(df)} rows and columns: {', '.join(df.columns[:6])}"
            except Exception as e:
                print(f"[Ingestion] Error parsing table {filename}: {e}")

        elif ext in [".docx", ".doc"]:
            parsed_meta["category"] = "TACTICAL_SOP"
            try:
                import docx
                doc = docx.Document(str(dest))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                parsed_meta["paragraph_count"] = len(paragraphs)
                parsed_meta["text_sample"] = "\n".join(paragraphs[:8])
            except Exception as e:
                print(f"[Ingestion] Error parsing docx {filename}: {e}")

        elif ext in [".json", ".geojson"]:
            parsed_meta["category"] = "AVIONICS_TELEMETRY"
            try:
                with open(dest, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
                if isinstance(data, list):
                    parsed_meta["json_type"] = f"Array of {len(data)} items"
                elif isinstance(data, dict):
                    parsed_meta["json_type"] = f"Object with keys: {', '.join(list(data.keys())[:8])}"
            except Exception as e:
                print(f"[Ingestion] Error parsing JSON {filename}: {e}")

        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            parsed_meta["category"] = "AVIONICS_TELEMETRY"
            parsed_meta["is_image"] = True

        self.documents[doc_id] = parsed_meta
        self._save_registry()
        print(f"[Ingestion] ✓ Successfully ingested '{filename}' as doc_id: {doc_id}")
        return parsed_meta

    def search_multi_dataset(self, query: str, active_doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Searches across all documents or focused on the active aircraft manual.
        """
        results = []
        target_docs = (
            [self.documents[active_doc_id]]
            if active_doc_id and active_doc_id in self.documents
            else list(self.documents.values())
        )

        for doc_info in target_docs:
            doc_id = doc_info["id"]
            file_path = Path(doc_info["file_path"])
            file_type = doc_info["file_type"]

            if file_type == "pdf" and file_path.exists():
                visual_matches = visual_rag_service.retrieve_visual_context(
                    file_path, doc_id, query, max_pages=3
                )
                for vm in visual_matches:
                    results.append({
                        "doc_id": doc_id,
                        "doc_name": doc_info["name"],
                        "file_type": "pdf",
                        "page_number": vm["page_number"],
                        "text": vm["text_snippet"],
                        "headings": vm["headings"],
                        "is_schematic": vm["is_schematic"],
                        "is_diagram": vm["is_diagram"],
                        "image_url": vm["image_url"],
                        "thumbnail_b64": vm["thumbnail_b64"],
                        "score": vm["score"],
                    })

            elif file_type in ["csv", "xlsx"] and file_path.exists():
                try:
                    df = pd.read_csv(file_path) if file_type == "csv" else pd.read_excel(file_path)
                    # Search text columns
                    matching_rows = df[
                        df.astype(str).apply(
                            lambda row: any(query.lower() in str(val).lower() for val in row),
                            axis=1,
                        )
                    ]
                    if not matching_rows.empty:
                        sample_records = matching_rows.head(5).to_dict(orient="records")
                        results.append({
                            "doc_id": doc_id,
                            "doc_name": doc_info["name"],
                            "file_type": file_type,
                            "page_number": 1,
                            "text": f"Found {len(matching_rows)} matching records:\n"
                            + json.dumps(sample_records, indent=2),
                            "score": 10,
                        })
                except Exception:
                    pass

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results


universal_ingestion = UniversalIngestionService()
