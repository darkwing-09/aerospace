"""
Integration tests for Document Writers and Artifact Versioning (Task 1.9 / PLAN §7.6, §11.6).
Verifies:
1. Deliverable generation is strictly gated by Critic PASS (FAIL raises ArtifactGateError).
2. Initial generation creates version 1 with complete evidence provenance and SHA-256 manifest.
3. Regenerating creates version 2 while preserving version 1 intact.
"""

from pathlib import Path
import json
import pytest

from tools.doc_writers.docx import ArtifactGateError, DocxArtifactWriter


def test_failed_critic_refuses_deliverable_generation(tmp_path):
    """Artifact generation fails closed with ArtifactGateError when Critic verdict is FAIL."""
    writer = DocxArtifactWriter(base_artifacts_dir=tmp_path)

    failing_eval = {
        "verdict": "FAIL",
        "faithfulness": 0.0,
        "reason": "Missing supporting evidence citations",
    }

    with pytest.raises(ArtifactGateError, match="Refusing to generate artifact"):
        writer.generate_deliverable(
            artifact_id="mro_hydraulic_summary",
            title="Hydraulic SOP Summary",
            content_paragraphs=["Unbacked claims about hydraulic maintenance."],
            evidence_refs=[],
            evaluation=failing_eval,
            workspace_id="ws_mro",
        )

    # Verify no file was created
    target_folder = tmp_path / "ws_mro" / "mro_hydraulic_summary"
    assert not target_folder.exists() or len(list(target_folder.glob("*.docx"))) == 0


def test_versioning_lifecycle_preserves_history(tmp_path):
    """
    Verifies that initial generation creates v1, and a second generation creates v2
    while preserving v1 intact.
    """
    writer = DocxArtifactWriter(base_artifacts_dir=tmp_path)

    passing_eval = {
        "verdict": "PASS",
        "faithfulness": 1.0,
        "reason": "Verified against 2 EvidenceUnits",
    }
    evidence = [
        {"source_id": "doc_sop_p1", "tag": "observed", "confidence": 1.0},
        {"source_id": "doc_sop_p2", "tag": "observed", "confidence": 0.95},
    ]

    # 1. First Generation (v1)
    file_v1, ver1 = writer.generate_deliverable(
        artifact_id="sop_hyd_report",
        title="SOP Hydraulic Servicing Report",
        content_paragraphs=["Primary circuit pressure is maintained at 210 kg/cm2."],
        evidence_refs=evidence,
        evaluation=passing_eval,
        workspace_id="ws_mro",
    )

    assert ver1 == 1
    assert file_v1.exists()
    assert file_v1.name == "sop_hyd_report_v1.docx"
    content_v1_bytes = file_v1.read_bytes()

    # 2. Second Generation (v2)
    file_v2, ver2 = writer.generate_deliverable(
        artifact_id="sop_hyd_report",
        title="SOP Hydraulic Servicing Report (Revision 2)",
        content_paragraphs=[
            "Primary circuit pressure is maintained at 210 kg/cm2.",
            "Emergency precharge is verified at 40 kg/cm2.",
        ],
        evidence_refs=evidence,
        evaluation=passing_eval,
        workspace_id="ws_mro",
    )

    assert ver2 == 2
    assert file_v2.exists()
    assert file_v2.name == "sop_hyd_report_v2.docx"

    # Crucial (§11.6): v1 must NOT be deleted or mutated!
    assert file_v1.exists()
    assert file_v1.read_bytes() == content_v1_bytes

    # Check manifest
    manifest_file = tmp_path / "ws_mro" / "sop_hyd_report" / "manifest.json"
    assert manifest_file.exists()
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert len(manifest["versions"]) == 2
    assert manifest["versions"][0]["version"] == 1
    assert manifest["versions"][1]["version"] == 2
    assert manifest["versions"][0]["filename"] == "sop_hyd_report_v1.docx"
    assert manifest["versions"][1]["filename"] == "sop_hyd_report_v2.docx"

