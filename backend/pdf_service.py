"""
pdf_service.py
─────────────────────────────────────────────────────────────────
Manages aircraft PDF manuals and document metadata.
Integrates with Universal Ingestion Service and Visual RAG Service.
"""
import os
from pathlib import Path
from typing import Optional, Dict, List

from config import settings
from universal_ingestion_service import universal_ingestion
from visual_rag_service import visual_rag_service

PDF_DIR = Path(settings.PDF_DIR)
PDF_DIR.mkdir(parents=True, exist_ok=True)


AIRCRAFT_REGISTRY: Dict[str, Dict] = {
    "mig21bis": {
        "name": "MiG-21BIS",
        "full_name": "Mikoyan-Gurevich MiG-21bis",
        "nato_name": "FISHBED",
        "engine": "Tumansky R25-300",
        "pdf_file": "mig21bis.pdf",
        "accent_color": "#e8780a",
        "total_pages": 330,
        "description": "Third-generation Soviet supersonic interceptor",
        "max_mach": 2.0,
        "crew": 1,
    },
}


class PDFService:
    def __init__(self):
        self.text_cache: Dict[str, List[str]] = {}

    def list_aircraft(self) -> List[Dict]:
        result = []
        for aircraft_id, info in AIRCRAFT_REGISTRY.items():
            pdf_path = PDF_DIR / info["pdf_file"]
            pages = info.get("total_pages", 330)

            if pdf_path.exists():
                try:
                    import fitz
                    doc = fitz.open(str(pdf_path))
                    detected = len(doc)
                    if detected > 0:
                        pages = detected
                    doc.close()
                except Exception:
                    pass

            result.append({
                **info,
                "id": aircraft_id,
                "pdf_available": pdf_path.exists(),
                "total_pages": pages,
            })
        return result

    def get_pdf_path(self, aircraft_id: str) -> Optional[Path]:
        # First check registry
        if aircraft_id in AIRCRAFT_REGISTRY:
            path = PDF_DIR / AIRCRAFT_REGISTRY[aircraft_id]["pdf_file"]
            if path.exists():
                return path

        # Check universal ingestion documents
        doc = universal_ingestion.get_document(aircraft_id)
        if doc and Path(doc["file_path"]).exists():
            return Path(doc["file_path"])

        # Fallback check direct file
        fallback = PDF_DIR / f"{aircraft_id}.pdf"
        return fallback if fallback.exists() else None

    def get_aircraft_info(self, aircraft_id: str) -> Optional[Dict]:
        if aircraft_id in AIRCRAFT_REGISTRY:
            return AIRCRAFT_REGISTRY[aircraft_id]
        return universal_ingestion.get_document(aircraft_id)

    async def save_pdf(self, aircraft_id: str, file) -> Dict:
        filename = f"{aircraft_id}.pdf"
        meta = await universal_ingestion.ingest_file(
            file_obj=file,
            filename=filename,
            category="AIRCRAFT_MANUAL",
            custom_name=aircraft_id.upper(),
        )
        return {
            "success": True,
            "aircraft_id": aircraft_id,
            "filename": filename,
            "pages": meta.get("total_pages", 0),
            "size_mb": meta.get("size_mb", 0.0),
        }

    def get_relevant_context(self, aircraft_id: str, query: str, max_pages: int = 3) -> str:
        """
        Multimodal visual & layout-aware context retrieval.
        """
        path = self.get_pdf_path(aircraft_id)
        if not path:
            return ""

        visual_contexts = visual_rag_service.retrieve_visual_context(
            path, aircraft_id, query, max_pages=max_pages
        )
        if not visual_contexts:
            return ""

        blocks = []
        for vc in visual_contexts:
            p_num = vc["page_number"]
            is_sch = " [DIAGRAM/SCHEMATIC]" if vc.get("is_schematic") else ""
            blocks.append(f"--- Page {p_num}{is_sch} ---\n{vc['text_snippet']}")

        return "\n\n".join(blocks)


pdf_svc = PDFService()
