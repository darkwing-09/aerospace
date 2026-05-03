"""
pdf_service.py
─────────────────────────────────────────────────────────────────
Manages aircraft PDF manuals.

AIRCRAFT_REGISTRY is the source of truth for all supported aircraft.
To add a new aircraft:
  1. Add an entry to AIRCRAFT_REGISTRY below
  2. Place the PDF at backend/pdfs/<pdf_file>
  3. Restart the backend
"""
import os
from pathlib import Path
from typing import Optional, Dict, List

from config import settings

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

    # ── Add future aircraft here ───────────────────────────────
    # "su30mk": {
    #     "name": "Su-30MK",
    #     "full_name": "Sukhoi Su-30MK",
    #     "nato_name": "FLANKER-C",
    #     "engine": "Saturn AL-31F",
    #     "pdf_file": "su30mk.pdf",
    #     "accent_color": "#1a8cff",
    #     "total_pages": 450,
    #     "description": "Russian twin-engine supermaneuverable fighter",
    # },
    # "rafale": {
    #     "name": "Rafale",
    #     "full_name": "Dassault Rafale",
    #     "nato_name": "N/A",
    #     "engine": "Snecma M88",
    #     "pdf_file": "rafale.pdf",
    #     "accent_color": "#003189",
    #     "total_pages": 520,
    #     "description": "French multirole omnirole combat aircraft",
    # },
}


class PDFService:
    def __init__(self):
        self.text_cache: Dict[str, List[str]] = {}

    def _get_pdf_text(self, aircraft_id: str) -> List[str]:
        """Lazy-load and cache PDF text by page."""
        if aircraft_id in self.text_cache:
            return self.text_cache[aircraft_id]
        
        path = self.get_pdf_path(aircraft_id)
        if not path: return []

        print(f"[AeroMind] Indexing PDF for {aircraft_id} (this may take a few seconds)...")
        try:
            import fitz
            # Use a fresh doc inside the thread if needed, but since it's read-only it's fine
            doc = fitz.open(str(path))
            pages_text = [page.get_text() for page in doc]
            doc.close()
            self.text_cache[aircraft_id] = pages_text
            return pages_text
        except Exception as e:
            print(f"[AeroMind] Error indexing PDF: {e}")
            return []

    def list_aircraft(self) -> List[Dict]:
        result = []
        for aircraft_id, info in AIRCRAFT_REGISTRY.items():
            pdf_path = PDF_DIR / info["pdf_file"]
            pages = info.get("total_pages", 0)

            # Get real page count from PyMuPDF if available
            # Falls back to registry value if PyMuPDF can't parse (e.g. some PDF 1.7 files)
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
        if aircraft_id not in AIRCRAFT_REGISTRY:
            return None
        path = PDF_DIR / AIRCRAFT_REGISTRY[aircraft_id]["pdf_file"]
        return path if path.exists() else None

    def get_aircraft_info(self, aircraft_id: str) -> Optional[Dict]:
        return AIRCRAFT_REGISTRY.get(aircraft_id)

    async def save_pdf(self, aircraft_id: str, file) -> Dict:
        if aircraft_id not in AIRCRAFT_REGISTRY:
            raise ValueError(
                f"Unknown aircraft: {aircraft_id}. Add to AIRCRAFT_REGISTRY first."
            )
        filename = AIRCRAFT_REGISTRY[aircraft_id]["pdf_file"]
        dest = PDF_DIR / filename
        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)

        pages = 0
        try:
            import fitz
            doc = fitz.open(str(dest))
            pages = len(doc)
            doc.close()
        except Exception:
            pass

        return {
            "success": True,
            "aircraft_id": aircraft_id,
            "filename": filename,
            "pages": pages,
            "size_mb": round(os.path.getsize(dest) / 1024 / 1024, 2),
        }

    def get_relevant_context(self, aircraft_id: str, query: str, max_pages: int = 3) -> tuple[str, int]:
        """
        Simple keyword-based RAG using cached text.
        Returns (context_string, top_page_number)
        """
        pages_text = self._get_pdf_text(aircraft_id)
        if not pages_text:
            return "", 1

        # Simple keyword search
        keywords = [k.lower() for k in query.split() if len(k) > 3]
        scored_pages = []

        for p_num, text in enumerate(pages_text):
            lower_text = text.lower()
            score = sum(1 for k in keywords if k in lower_text)
            if score > 0:
                scored_pages.append((score, p_num, text))

        # Sort by score and take top N
        scored_pages.sort(key=lambda x: x[0], reverse=True)
        top_pages = scored_pages[:max_pages]
        
        context_blocks = []
        for score, p_num, p_text in top_pages:
            context_blocks.append(f"--- Page {p_num + 1} ---\n{p_text[:1200]}")

        top_page = top_pages[0][1] + 1 if top_pages else 1
        return "\n\n".join(context_blocks), top_page
