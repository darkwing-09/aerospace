"""
backend/tests/unit/test_registry_egress_guard.py
─────────────────────────────────────────────────────────────────
Unit tests for zero-egress registry and startup guard (Task 2.5 / PLAN §7.1, §11.20).
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
import yaml

from router.router import ModelRouter

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def test_cloud_model_rejected_by_registry_guard(tmp_path):
    """Adding a cloud model tag to a local tier must raise ValueError at load time."""
    config_data = {
        "local": {
            "cpu_lite": [
                {
                    "name": "kimi-cloud",
                    "provider": "ollama",
                    "endpoint": "http://127.0.0.1:11434",
                    "model_tag": "kimi-k2.5:cloud",
                    "capabilities": ["planning"],
                    "version": "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
                    "rank": 1,
                    "tier": "small",
                }
            ]
        }
    }
    cfg_file = tmp_path / "models.yaml"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    with pytest.raises(ValueError) as exc:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "cloud model tag" in str(exc.value)


def test_non_loopback_endpoint_rejected_by_registry_guard(tmp_path):
    """Adding an external network endpoint to a local tier must raise ValueError at load time."""
    config_data = {
        "local": {
            "cpu_lite": [
                {
                    "name": "remote-openai",
                    "provider": "openai",
                    "endpoint": "https://api.openai.com/v1",
                    "model_tag": "gpt-4o",
                    "capabilities": ["planning"],
                    "version": "v1",
                    "rank": 1,
                    "tier": "large",
                }
            ]
        }
    }
    cfg_file = tmp_path / "models.yaml"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    with pytest.raises(ValueError) as exc:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "non-loopback endpoint" in str(exc.value)


def test_zero_egress_offline_environment_flags():
    """Verify offline flags are enforced when router initializes."""
    router = ModelRouter(hardware_tier="cpu_lite")
    assert os.environ.get("HF_HUB_OFFLINE") == "1"
    assert os.environ.get("TRANSFORMERS_OFFLINE") == "1"
    assert os.environ.get("ENABLE_COLPALI_DOWNLOAD") == "false"


def test_startup_guard_blocks_cloud_reference(monkeypatch, tmp_path):
    """Under ZERO_EGRESS_MODE=true, router startup must block any cloud model reference."""
    monkeypatch.setenv("ZERO_EGRESS_MODE", "true")
    config_data = {
        "local": {
            "cpu_lite": [
                {
                    "name": "malicious-cloud",
                    "provider": "ollama",
                    "endpoint": "http://127.0.0.1:11434",
                    "model_tag": "glm-5:cloud",
                    "capabilities": ["planning"],
                    "version": "sha256:abcdef",
                }
            ]
        }
    }
    cfg_file = tmp_path / "models.yaml"
    with open(cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    # Must be caught either by registry validation or startup guard
    with pytest.raises((ValueError, RuntimeError)) as exc:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "cloud" in str(exc.value).lower()
