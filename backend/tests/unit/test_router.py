"""
Unit tests for ModelRouter (Task 0.4 / PLAN §7.1, §7.2, ADR-0005).
"""

import tempfile
from pathlib import Path
import pytest
import yaml

from router.router import ModelRouter, NoModelForCapability


def test_default_resolution_returns_default_true():
    router = ModelRouter(hardware_tier="cpu_lite")
    entry = router.resolve("planning")
    assert entry.get("default") is True
    assert entry["model_tag"] == "qwen3:4b-instruct-2507-q4_K_M"


def test_code_gen_and_general_reasoning_resolve_differently():
    router = ModelRouter(hardware_tier="cpu_lite")
    code_entry = router.resolve("code_gen")
    reasoning_entry = router.resolve("general_reasoning")

    assert code_entry["model_tag"] != reasoning_entry["model_tag"]
    assert "qwen2.5-coder" in code_entry["model_tag"]
    assert "qwen3" in reasoning_entry["model_tag"]


def test_unknown_capability_raises_actionable_error():
    router = ModelRouter(hardware_tier="cpu_lite")
    with pytest.raises(NoModelForCapability) as excinfo:
        router.resolve("teleportation_magic")
    msg = str(excinfo.value)
    assert "teleportation_magic" in msg
    assert "Valid capabilities" in msg
    assert "planning" in msg


def test_legacy_role_mapping():
    router = ModelRouter(hardware_tier="cpu_lite")
    assert router.resolve("orchestrator")["model_tag"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert router.resolve("synthesis")["model_tag"] == "qwen3:4b-instruct-2507-q4_K_M"
    assert router.resolve("vision_table")["model_tag"] == "qwen3-vl:2b"
    assert router.resolve("verification")["model_tag"] == "qwen2.5:3b"


def test_cloud_model_rejected_at_load_time(tmp_path):
    bad_config = {
        "local": {
            "cpu_lite": [
                {
                    "name": "cloud-model",
                    "provider": "ollama",
                    "endpoint": "http://127.0.0.1:11434",
                    "model_tag": "kimi-k2.5:cloud",
                    "capabilities": ["planning"],
                    "version": "v1",
                }
            ]
        }
    }
    cfg_file = tmp_path / "bad_models.yaml"
    cfg_file.write_text(yaml.dump(bad_config))

    with pytest.raises(ValueError) as excinfo:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "cloud model tag" in str(excinfo.value)


def test_non_loopback_endpoint_rejected_at_load_time(tmp_path):
    bad_config = {
        "local": {
            "cpu_lite": [
                {
                    "name": "external-model",
                    "provider": "ollama",
                    "endpoint": "https://api.external-cloud.com/v1",
                    "model_tag": "qwen2.5:3b",
                    "capabilities": ["planning"],
                    "version": "v1",
                }
            ]
        }
    }
    cfg_file = tmp_path / "bad_models.yaml"
    cfg_file.write_text(yaml.dump(bad_config))

    with pytest.raises(ValueError) as excinfo:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "non-loopback endpoint" in str(excinfo.value)


def test_missing_version_rejected_at_load_time(tmp_path):
    bad_config = {
        "local": {
            "cpu_lite": [
                {
                    "name": "no-version-model",
                    "provider": "ollama",
                    "endpoint": "http://127.0.0.1:11434",
                    "model_tag": "qwen2.5:3b",
                    "capabilities": ["planning"],
                }
            ]
        }
    }
    cfg_file = tmp_path / "bad_models.yaml"
    cfg_file.write_text(yaml.dump(bad_config))

    with pytest.raises(ValueError) as excinfo:
        ModelRouter(config_path=cfg_file, environment="local", hardware_tier="cpu_lite")
    assert "version" in str(excinfo.value)

