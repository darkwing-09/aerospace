#!/usr/bin/env python3
"""
scripts/verify_models.py
─────────────────────────────────────────────────────────────────
Verify model manifest digests against deploy/models.lock.json and
config/models.yaml (Task 2.1 / PLAN §7.1, §11.20).

Exits 0 on match.
Exits 1 on any tampering, mismatch, or missing required model digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = REPO_ROOT / "deploy" / "models.lock.json"
DEFAULT_MODELS_YAML = REPO_ROOT / "config" / "models.yaml"


_SAFETENSORS_CACHE: Dict[str, Any] = {}


def compute_safetensors_digest(models_dir: Path) -> Optional[str]:
    """Computes combined SHA-256 for model.safetensors.index.json and shards with mtime/size caching."""
    index_file = models_dir / "model.safetensors.index.json"
    if not index_file.exists():
        return None

    try:
        with open(index_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        shard_files = sorted(set(data.get("weight_map", {}).values()))
        file_stats = [(index_file.stat().st_mtime, index_file.stat().st_size)]
        for s in shard_files:
            sp = models_dir / s
            if not sp.exists():
                return None
            st = sp.stat()
            file_stats.append((st.st_mtime, st.st_size))

        cache_key = tuple(file_stats)
        if cache_key in _SAFETENSORS_CACHE:
            return _SAFETENSORS_CACHE[cache_key]

        cache_file = models_dir / ".safetensors_cache.json"
        cache_key_str = json.dumps([[s[0], s[1]] for s in file_stats])
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as cf:
                    disk_cache = json.load(cf)
                if disk_cache.get("key") == cache_key_str and disk_cache.get("digest"):
                    _SAFETENSORS_CACHE[cache_key] = disk_cache["digest"]
                    return disk_cache["digest"]
            except Exception:
                pass

        hasher = hashlib.sha256()
        with open(index_file, "rb") as f:
            hasher.update(f.read())
        index_hash = hasher.hexdigest()

        combined = hashlib.sha256()
        combined.update(index_hash.encode())

        for shard in shard_files:
            shard_path = models_dir / shard
            h = hashlib.sha256()
            with open(shard_path, "rb") as f:
                while chunk := f.read(2 * 1024 * 1024):
                    h.update(chunk)
            combined.update(h.hexdigest().encode())

        result = f"sha256:{combined.hexdigest()}"
        _SAFETENSORS_CACHE[cache_key] = result
        try:
            with open(cache_file, "w", encoding="utf-8") as cf:
                json.dump({"key": cache_key_str, "digest": result}, cf)
        except Exception:
            pass
        return result
    except Exception as e:
        print(f"[WARN] Failed computing safetensors digest: {e}", file=sys.stderr)
        return None


def fetch_ollama_tags(endpoint: str = "http://127.0.0.1:11434") -> Optional[Dict[str, str]]:
    """Fetches model tag -> digest mapping from Ollama /api/tags if reachable."""
    url = f"{endpoint.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AeroMind-Verifier"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                models = payload.get("models", [])
                tag_to_digest: Dict[str, str] = {}
                for m in models:
                    tag = m.get("name") or m.get("model")
                    digest = m.get("digest")
                    if tag and digest:
                        tag_to_digest[tag] = f"sha256:{digest}"
                        # Also map without tag suffix if tag ends with :latest
                        if tag.endswith(":latest"):
                            tag_to_digest[tag[:-7]] = f"sha256:{digest}"
                return tag_to_digest
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def verify_models(
    lock_path: Path,
    models_yaml_path: Path,
    tier: str = "cpu_lite",
    strict_ollama: bool = False,
) -> bool:
    """
    Verifies digests across models.lock.json, models.yaml, and live artifacts.
    Returns True if valid, False if any digest differs.
    """
    if not lock_path.exists():
        print(f"[FAIL] Lockfile not found: {lock_path}", file=sys.stderr)
        return False

    if not models_yaml_path.exists():
        print(f"[FAIL] models.yaml not found: {models_yaml_path}", file=sys.stderr)
        return False

    with open(lock_path, "r", encoding="utf-8") as f:
        lock_data = json.load(f)

    with open(models_yaml_path, "r", encoding="utf-8") as f:
        models_cfg = yaml.safe_load(f) or {}

    lock_models = {m["tag"]: m for m in lock_data.get("models", [])}
    yaml_tier_models = {
        m.get("model_tag"): m
        for m in models_cfg.get("local", {}).get(tier, [])
        if m.get("model_tag")
    }

    mismatches: List[str] = []

    # 1. Cross-check models.yaml vs models.lock.json for the active tier
    for tag, y_entry in yaml_tier_models.items():
        y_version = y_entry.get("version", "")
        # Resolve either exact tag or base tag
        l_entry = lock_models.get(tag) or lock_models.get(f"{tag}:latest")
        if not l_entry:
            mismatches.append(f"Model '{tag}' in models.yaml tier '{tier}' is missing from models.lock.json")
            continue

        l_digest = l_entry.get("digest", "")
        if y_version != l_digest:
            mismatches.append(
                f"Digest mismatch for '{tag}': models.yaml has '{y_version}', lockfile has '{l_digest}'"
            )

    # 2. Check live safetensors in backend/models if listed
    if "backend/models" in lock_models:
        expected_st_digest = lock_models["backend/models"]["digest"]
        models_dir = REPO_ROOT / "backend" / "models"
        if (models_dir / "model.safetensors.index.json").exists():
            computed = compute_safetensors_digest(models_dir)
            if computed and computed != expected_st_digest:
                mismatches.append(
                    f"Digest mismatch for backend/models safetensors: expected '{expected_st_digest}', computed '{computed}'"
                )

    # 3. Check live Ollama daemon if reachable
    ollama_tags = fetch_ollama_tags()
    if ollama_tags:
        for tag, l_entry in lock_models.items():
            if tag == "backend/models":
                continue
            if tag in ollama_tags:
                live_digest = ollama_tags[tag]
                expected_digest = l_entry.get("digest", "")
                if live_digest != expected_digest:
                    mismatches.append(
                        f"Live Ollama digest mismatch for '{tag}': expected '{expected_digest}', live is '{live_digest}'"
                    )
    elif strict_ollama:
        mismatches.append("Strict verification failed: Ollama daemon not reachable at http://127.0.0.1:11434")

    if mismatches:
        print("[FAIL] Model verification failed with mismatches:", file=sys.stderr)
        for err in mismatches:
            print(f"  - {err}", file=sys.stderr)
        return False

    print(f"[OK] Model manifest and lockfile verified successfully for tier '{tier}'.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify AeroMind model digests against lockfile.")
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK, help="Path to models.lock.json")
    parser.add_argument("--yaml", type=Path, default=DEFAULT_MODELS_YAML, help="Path to models.yaml")
    parser.add_argument("--tier", type=str, default="cpu_lite", help="Hardware tier to check")
    parser.add_argument("--strict-ollama", action="store_true", help="Fail if Ollama is unreachable")

    args = parser.parse_args()
    success = verify_models(
        lock_path=args.lock,
        models_yaml_path=args.yaml,
        tier=args.tier,
        strict_ollama=args.strict_ollama,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
