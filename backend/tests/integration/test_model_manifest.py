"""
backend/tests/integration/test_model_manifest.py
─────────────────────────────────────────────────────────────────
Integration tests for model manifests, lockfile, and integrity
verification (Task 2.1 / PLAN §7.1, §11.20).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import urllib.request
import urllib.error
import pytest
import yaml

from scripts.verify_models import verify_models

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOCK_PATH = REPO_ROOT / "deploy" / "models.lock.json"
MODELS_YAML_PATH = REPO_ROOT / "config" / "models.yaml"

SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


def test_models_lock_valid():
    """Verify deploy/models.lock.json exists, is valid JSON, and has valid SHA-256 digests."""
    assert LOCK_PATH.exists(), f"Missing lockfile: {LOCK_PATH}"
    with open(LOCK_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("version") == 1
    models = data.get("models", [])
    assert len(models) >= 5, "Expected at least 5 models in lockfile"

    tags = set()
    for m in models:
        assert "name" in m
        assert "tag" in m
        assert "digest" in m
        assert "size" in m
        assert "tier" in m
        assert "licence" in m
        assert SHA256_RE.match(m["digest"]), f"Invalid digest format: {m['digest']}"
        tags.add(m["tag"])

    # Ensure key cpu_lite models are tracked
    assert "qwen3:4b-instruct-2507-q4_K_M" in tags
    assert "qwen2.5-coder:1.5b" in tags
    assert "qwen3-vl:2b" in tags
    assert "qwen2.5:3b" in tags
    assert "nomic-embed-text:latest" in tags or "nomic-embed-text" in tags


def test_models_yaml_pinned_digests():
    """Verify all models in models.yaml have pinned sha256 digests matching lockfile."""
    assert MODELS_YAML_PATH.exists()
    with open(MODELS_YAML_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    with open(LOCK_PATH, "r", encoding="utf-8") as f:
        lock_data = json.load(f)

    lock_by_tag = {m["tag"]: m for m in lock_data.get("models", [])}

    cpu_lite_models = config.get("local", {}).get("cpu_lite", [])
    assert len(cpu_lite_models) > 0

    for m in cpu_lite_models:
        tag = m.get("model_tag")
        version = m.get("version")
        assert version, f"Missing version for {m.get('name')}"
        assert SHA256_RE.match(version), f"Version is not a pinned sha256: {version}"
        
        # Check against lockfile
        l_entry = lock_by_tag.get(tag) or lock_by_tag.get(f"{tag}:latest")
        assert l_entry is not None, f"Model tag '{tag}' in models.yaml missing from lockfile"
        assert version == l_entry["digest"], f"Digest mismatch for {tag}: {version} != {l_entry['digest']}"


def test_verify_models_script_passes():
    """Verify verify_models() returns True on the clean repo."""
    assert verify_models(
        lock_path=LOCK_PATH,
        models_yaml_path=MODELS_YAML_PATH,
        tier="cpu_lite",
        strict_ollama=False,
    ) is True


def test_tampered_digest_fails_verification(tmp_path):
    """Tampering a single digest in models.lock.json causes verification to fail."""
    with open(LOCK_PATH, "r", encoding="utf-8") as f:
        lock_data = json.load(f)

    # Tamper one model digest
    lock_data["models"][0]["digest"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    tampered_lock = tmp_path / "models.lock.json"
    with open(tampered_lock, "w", encoding="utf-8") as f:
        json.dump(lock_data, f)

    assert verify_models(
        lock_path=tampered_lock,
        models_yaml_path=MODELS_YAML_PATH,
        tier="cpu_lite",
        strict_ollama=False,
    ) is False


@pytest.mark.needs_ollama
def test_local_models_smoke_prompt():
    """Verify every local model in cpu_lite can answer a smoke prompt if Ollama is running."""
    endpoint = "http://127.0.0.1:11434"
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status != 200:
                pytest.skip("Ollama not responding with 200")
    except Exception:
        pytest.skip("Ollama daemon is not reachable on 127.0.0.1:11434")

    with open(MODELS_YAML_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    cpu_lite_models = config.get("local", {}).get("cpu_lite", [])
    for m in cpu_lite_models:
        if m.get("provider") != "ollama":
            continue
        tag = m["model_tag"]
        # embedding model uses /api/embeddings
        if "embedding" in m.get("capabilities", []):
            url = f"{endpoint}/api/embeddings"
            body = json.dumps({"model": tag, "prompt": "smoke test"}).encode("utf-8")
        else:
            url = f"{endpoint}/api/generate"
            body = json.dumps({"model": tag, "prompt": "Reply with 1", "stream": False}).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                assert resp.status == 200
                res = json.loads(resp.read().decode("utf-8"))
                if "embedding" in m.get("capabilities", []):
                    assert "embedding" in res and len(res["embedding"]) > 0
                else:
                    assert "response" in res
        except Exception as e:
            pytest.fail(f"Smoke prompt failed for model '{tag}': {e}")
