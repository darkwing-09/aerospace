"""
visual_rag_service.py
─────────────────────────────────────────────────────────────────
ColPali Multimodal Visual Document Retrieval & Processing.

Key capabilities:
1. High-resolution page image rendering & caching via PyMuPDF (fitz).
2. Layout-aware structural parsing (blocks, tables, diagrams, schematics).
3. Visual feature extraction (detects cockpit diagrams, wiring, instruments).
4. ColPali late-interaction multi-vector scoring via Qdrant index.
5. Base64 & URL generation for VLM input and frontend HUD visualization.
"""

import os
import io
import base64
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import fitz  # PyMuPDF
from PIL import Image

from config import settings


class VisualRAGService:
    def __init__(self):
        self.image_cache_dir = Path(settings.PAGE_IMAGES_DIR)
        self.image_cache_dir.mkdir(parents=True, exist_ok=True)
        self.document_indices: Dict[str, Dict[str, Any]] = {}

    def get_document_cache_dir(self, doc_id: str) -> Path:
        doc_dir = self.image_cache_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir

    def get_page_image_path(self, doc_id: str, page_num: int) -> Path:
        """Page numbers are 1-indexed."""
        return self.get_document_cache_dir(doc_id) / f"page_{page_num}.png"

    def get_page_thumb_path(self, doc_id: str, page_num: int) -> Path:
        return self.get_document_cache_dir(doc_id) / f"thumb_{page_num}.jpg"

    def render_and_cache_page_image(
        self, doc_path: Path, doc_id: str, page_num: int, dpi: int = 150
    ) -> Optional[Path]:
        """
        Renders a single PDF page into a high-quality PNG image.
        page_num is 1-indexed.
        """
        img_path = self.get_page_image_path(doc_id, page_num)
        thumb_path = self.get_page_thumb_path(doc_id, page_num)

        if img_path.exists() and thumb_path.exists():
            return img_path

        try:
            doc = fitz.open(str(doc_path))
            if page_num < 1 or page_num > len(doc):
                doc.close()
                return None

            page = doc[page_num - 1]
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)

            img_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(img_path))

            # Also create lightweight thumbnail for fast UI previews
            thumb_matrix = fitz.Matrix(60 / 72.0, 60 / 72.0)
            thumb_pix = page.get_pixmap(matrix=thumb_matrix, alpha=False)
            thumb_pix.save(str(thumb_path))

            doc.close()
            return img_path
        except Exception as e:
            print(f"[VisualRAG] Error rendering page {page_num} of {doc_id}: {e}")
            return None

    def index_document(self, doc_path: Path, doc_id: str) -> Dict[str, Any]:
        """
        Extracts visual layout and structural features across all pages,
        renders rasterized page images, and populates the ColPali Qdrant multi-vector index.
        """
        if doc_id in self.document_indices:
            return self.document_indices[doc_id]

        index_file = self.get_document_cache_dir(doc_id) / "index_meta.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)
                    self.document_indices[doc_id] = index_data
                    return index_data
            except Exception:
                pass

        print(f"[VisualRAG] Indexing visual & layout structure for '{doc_id}'...")
        pages_meta = []
        try:
            doc = fitz.open(str(doc_path))
            total_pages = len(doc)

            for idx, page in enumerate(doc):
                p_num = idx + 1
                raw_text = page.get_text("text") or ""
                blocks = page.get_text("blocks") or []
                images = page.get_images(full=True) or []
                drawings = page.get_drawings() or []

                # OCR Fallback for scanned/handwritten documents
                if not raw_text or len(raw_text.strip()) < 30:
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        if not hasattr(self, "_ocr_engine"):
                            self._ocr_engine = RapidOCR()
                        pix = page.get_pixmap(dpi=150)
                        ocr_res, _ = self._ocr_engine(pix.tobytes("png"))
                        if ocr_res:
                            ocr_lines = [line[1] for line in ocr_res if line and len(line) > 1]
                            raw_text = "\n".join(ocr_lines)
                    except Exception as e:
                        print(f"[VisualRAG] OCR fallback for page {p_num} note: {e}")

                # Visual feature heuristic (cockpit panels, hydraulic diagrams, wiring, tables)
                has_images = len(images) > 0
                has_vector_drawings = len(drawings) > 10
                is_diagram = has_images or has_vector_drawings

                # Detect schematic keywords
                lower_text = raw_text.lower()
                is_schematic = any(
                    k in lower_text
                    for k in [
                        "schematic",
                        "diagram",
                        "figure",
                        "panel",
                        "switch",
                        "cockpit",
                        "hydraulic",
                        "wiring",
                        "circuit",
                        "valve",
                        "gauge",
                        "chart",
                        "table",
                    ]
                )

                page_info = {
                    "page_number": p_num,
                    "text": raw_text[:4000],
                    "char_count": len(raw_text),
                    "block_count": len(blocks),
                    "image_count": len(images),
                    "is_diagram": is_diagram,
                    "is_schematic": is_schematic,
                    "headings": [
                        b[4].strip()
                        for b in blocks
                        if len(b) > 4 and len(b[4].strip()) < 80 and "\n" not in b[4].strip()
                    ][:5],
                }
                pages_meta.append(page_info)

            doc.close()

            index_data = {
                "doc_id": doc_id,
                "total_pages": total_pages,
                "pages": pages_meta,
            }

            self.document_indices[doc_id] = index_data

            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f)

            print(f"[VisualRAG] Indexed {total_pages} pages for '{doc_id}'.")

            # Hook into ColPali multi-vector Qdrant index
            try:
                from colpali_retrieval_service import colpali_retrieval_service
                image_paths = {
                    p["page_number"]: self.get_page_image_path(doc_id, p["page_number"])
                    for p in pages_meta
                }
                colpali_retrieval_service.index_document_pages(doc_id, pages_meta, image_paths)
            except Exception as e:
                print(f"[VisualRAG] ColPali Qdrant indexing hook error: {e}")

            return index_data
        except Exception as e:
            print(f"[VisualRAG] Indexing failed for {doc_id}: {e}")
            return {"doc_id": doc_id, "total_pages": 0, "pages": []}

    def retrieve_visual_context(
        self,
        doc_path: Path,
        doc_id: str,
        query: str,
        max_pages: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top matching visual pages using ColPali multi-vector
        late-interaction scoring via Qdrant.
        Maintains the exact return shape expected by VisualDiagramCard.jsx and callers.
        """
        index = self.index_document(doc_path, doc_id)
        pages = index.get("pages", [])
        if not pages:
            return []

        # Perform ColPali late-interaction search via Qdrant
        try:
            from colpali_retrieval_service import colpali_retrieval_service
            colpali_results = colpali_retrieval_service.search_visual_pages(
                doc_id=doc_id,
                query=query,
                top_k=max_pages,
            )
        except Exception as e:
            print(f"[VisualRAG] ColPali query error: {e}")
            colpali_results = []

        if colpali_results:
            # Ensure high-res page image is rendered on demand
            for r in colpali_results:
                p_num = r["page_number"]
                img_path = self.render_and_cache_page_image(doc_path, doc_id, p_num)
                r["image_available"] = img_path is not None and img_path.exists()
            return colpali_results

        # Fallback scoring if Qdrant is initializing
        query_terms = [q.lower() for q in query.split() if len(q) > 2]
        scored_pages = []
        for p in pages:
            text_lower = p["text"].lower()
            score = 0
            for term in query_terms:
                if term in text_lower:
                    score += 2
                for h in p["headings"]:
                    if term in h.lower():
                        score += 4
            if p["is_diagram"] or p["is_schematic"]:
                score += 5
            if score > 0:
                scored_pages.append((score, p))

        scored_pages.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored_pages[:max_pages]

        results = []
        for score, p in top_candidates:
            p_num = p["page_number"]
            img_path = self.render_and_cache_page_image(doc_path, doc_id, p_num)
            thumb_path = self.get_page_thumb_path(doc_id, p_num)

            thumb_b64 = ""
            if thumb_path.exists():
                try:
                    with open(thumb_path, "rb") as img_f:
                        thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(img_f.read()).decode("utf-8")
                except Exception:
                    pass

            results.append({
                "page_number": p_num,
                "score": score,
                "is_diagram": p["is_diagram"],
                "is_schematic": p["is_schematic"],
                "headings": p["headings"],
                "text_snippet": p["text"][:500],
                "image_url": f"/api/documents/{doc_id}/page/{p_num}/image",
                "thumbnail_b64": thumb_b64,
                "image_available": img_path is not None and img_path.exists(),
            })

        return results

    def get_page_image_base64(self, doc_id: str, page_num: int, max_dim: int = 800) -> Optional[str]:
        """Returns page image encoded as optimized base64 string for VLM inference."""
        img_path = self.get_page_image_path(doc_id, page_num)
        if not img_path.exists():
            return None
        try:
            with Image.open(str(img_path)) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=80)
                return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            print(f"[VisualRAG] Base64 encoding error: {e}")
            return None


visual_rag_service = VisualRAGService()
