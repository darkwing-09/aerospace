"""
Unit test for Fixture Corpus v0 (Task 0.6 / PLAN §9 Task 0.6).
Verifies that all synthetic fixtures exist, match SHA256 hashes in the manifest,
and contain ground-truth verification data.
"""

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "eval" / "fixtures" / "ground_truth.json"


def get_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_fixtures_manifest_integrity():
    assert MANIFEST_PATH.exists(), f"Ground truth manifest missing at {MANIFEST_PATH}"

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert "fixtures" in manifest
    assert "ground_truth_qa" in manifest

    fixtures = manifest["fixtures"]
    assert len(fixtures) == 5, f"Expected 5 fixtures, found {len(fixtures)}"

    for name, meta in fixtures.items():
        file_path = REPO_ROOT / meta["path"]
        assert file_path.exists(), f"Fixture file '{name}' missing at {file_path}"
        actual_sha = get_file_sha256(file_path)
        assert actual_sha == meta["sha256"], f"SHA256 mismatch for fixture '{name}'"

    qa_pairs = manifest["ground_truth_qa"]
    assert len(qa_pairs) == 20, f"Expected 20 QA pairs, found {len(qa_pairs)}"

    for qa in qa_pairs:
        assert "question" in qa and len(qa["question"]) > 5
        assert "answer" in qa and len(qa["answer"]) > 0
        assert "source" in qa

