"""
backend/tools/doc_writers/docx.py
─────────────────────────────────────────────────────────────────
Versioned DOCX Deliverable Writer for AeroMind 2.0 (PLAN §7.6, Task 1.9).
Produces official deliverables with provenance and citations ONLY after Critic PASS.
Maintains version history (v1, v2, ...) without overwriting prior versions (PLAN §11.6).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import docx
    from docx.shared import Inches, Pt, RGBColor
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


class ArtifactGateError(PermissionError):
    """Raised when attempting to generate a deliverable artifact without a Critic PASS."""


class DocxArtifactWriter:
    """
    Produces versioned DOCX deliverables with complete evidence provenance.
    """

    def __init__(self, base_artifacts_dir: Optional[Path] = None) -> None:
        if base_artifacts_dir is None:
            from config import settings
            base_artifacts_dir = Path(settings.DATA_DIR) / "artifacts"
        self.base_dir = Path(base_artifacts_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_next_version(self, artifact_folder: Path) -> int:
        """Inspects existing versions to determine next sequential version number."""
        manifest_file = artifact_folder / "manifest.json"
        if not manifest_file.exists():
            return 1
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                versions = [item["version"] for item in data.get("versions", [])]
                return max(versions, default=0) + 1
        except Exception:
            return 1

    def generate_deliverable(
        self,
        artifact_id: str,
        title: str,
        content_paragraphs: List[str],
        evidence_refs: List[Dict[str, Any]],
        evaluation: Optional[Dict[str, Any]],
        workspace_id: str = "default_workspace",
        author_agent: str = "execution_agent",
    ) -> Tuple[Path, int]:
        """
        Creates a versioned DOCX artifact.
        Fails closed with ArtifactGateError if evaluation verdict is not PASS (PLAN §11.6).
        """
        # CRITIC GATE CHECK: Deliverables can ONLY ship after Critic PASS
        if not evaluation or evaluation.get("verdict") != "PASS":
            verdict = evaluation.get("verdict") if evaluation else "MISSING"
            raise ArtifactGateError(
                f"Refusing to generate artifact '{artifact_id}': Critic evaluation verdict is '{verdict}'. "
                "Deliverables cannot be produced without passing the Critic gate (PLAN §3.2, §11.6)."
            )

        if not HAS_DOCX:
            raise RuntimeError("python-docx is not installed in the environment.")

        # Determine version and target paths
        artifact_folder = self.base_dir / workspace_id / artifact_id
        artifact_folder.mkdir(parents=True, exist_ok=True)

        version = self._get_next_version(artifact_folder)
        filename = f"{artifact_id}_v{version}.docx"
        file_path = artifact_folder / filename

        # Build Word Document
        doc = docx.Document()

        # Title
        title_para = doc.add_heading(title, level=0)
        doc.add_paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | "
            f"Workspace: {workspace_id} | Version: v{version}"
        )
        doc.add_paragraph(f"Authoring Agent: {author_agent}")

        # Deliverable Content
        doc.add_heading("Deliverable Summary", level=1)
        for p_text in content_paragraphs:
            doc.add_paragraph(p_text)

        # Verified Provenance Section
        doc.add_heading("Verified Evidence & Provenance", level=1)
        doc.add_paragraph("This deliverable has been verified by Critic Gate with supporting citations:")

        table = doc.add_table(rows=1, cols=3)
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = "Source ID"
        hdr_cells[1].text = "Evidence Tag"
        hdr_cells[2].text = "Confidence"

        for ref in evidence_refs:
            row_cells = table.add_row().cells
            row_cells[0].text = str(ref.get("source_id", "—"))
            row_cells[1].text = str(ref.get("tag", "observed"))
            row_cells[2].text = f"{float(ref.get('confidence', 1.0)):.2f}"

        # Save DOCX file
        doc.save(str(file_path))

        # Calculate SHA-256
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        digest = sha.hexdigest()

        # Update Manifest preserving history
        manifest_file = artifact_folder / "manifest.json"
        manifest_data = {"artifact_id": artifact_id, "workspace_id": workspace_id, "versions": []}
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception:
                pass

        manifest_data["versions"].append({
            "version": version,
            "filename": filename,
            "path": str(file_path.resolve()),
            "sha256": digest,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "evidence_refs": evidence_refs,
            "evaluation": evaluation,
        })

        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        return file_path, version

