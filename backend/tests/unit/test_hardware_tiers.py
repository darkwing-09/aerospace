"""
Unit tests for Hardware Tiers (Task 0.4b / PLAN §8.2, ADR-0007).
"""

from pathlib import Path
import pytest
import yaml

from router.router import ModelRouter
from observability.audit import AuditEvent, audit_logger

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config"


def test_tier_vision_resolution_parity():
    # In cpu_lite tier
    router_cpu = ModelRouter(hardware_tier="cpu_lite")
    entry_cpu = router_cpu.resolve("vision")
    assert entry_cpu["model_tag"] == "qwen3-vl:2b"

    # In gpu_high tier
    router_gpu = ModelRouter(hardware_tier="gpu_high")
    entry_gpu = router_gpu.resolve("vision")
    assert entry_gpu["model_tag"] == "qwen3-vl:8b"


def test_embedding_model_identical_across_all_tiers():
    tiers = ["cpu_lite", "gpu_standard", "gpu_high", "gpu_multi", "apple_full"]
    embedding_tags = set()

    for tier in tiers:
        router = ModelRouter(hardware_tier=tier)
        entry = router.resolve("embedding")
        embedding_tags.add(entry["model_tag"])

    # Invariant: embedding model MUST be identical across every tier (ADR-0007)
    assert len(embedding_tags) == 1
    assert "nomic-embed-text" in embedding_tags


def test_critic_deterministic_layer_enabled_in_all_tiers():
    hw_profiles_path = CONFIG_DIR / "hardware_profiles.yaml"
    with open(hw_profiles_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tiers = data.get("tiers", {})
    assert len(tiers) >= 5

    for tier_name, tier_cfg in tiers.items():
        safety = tier_cfg.get("safety", {})
        assert safety.get("critic_deterministic") is True, f"Critic deterministic layer disabled in {tier_name}"
        assert safety.get("permissions") is True, f"Permissions disabled in {tier_name}"
        assert safety.get("audit") is True, f"Audit disabled in {tier_name}"
        assert safety.get("egress_guard") is True, f"Egress guard disabled in {tier_name}"


def test_disabled_agents_in_cpu_lite():
    agents_path = CONFIG_DIR / "agents.yaml"
    with open(agents_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cpu_tier = data["tiers"]["cpu_lite"]
    assert "coding" in cpu_tier["disabled_agents"]
    assert "correlation" in cpu_tier["disabled_agents"]
    assert cpu_tier["max_parallel_llm_calls"] == 1
    assert cpu_tier["max_plan_depth"] == 3


def test_hardware_profile_selected_audit_event(tmp_path):
    from observability.audit import AuditLogger
    logger = AuditLogger(log_dir=tmp_path)

    router = ModelRouter(hardware_tier="cpu_lite")
    evt = AuditEvent(
        workspace_id="system",
        user_id="system",
        conversation_id="startup",
        task_id="startup",
        event_type="HARDWARE_PROFILE_SELECTED",
        agent_name="hardware_probe",
        details={"tier": router.hardware_tier},
        succeeded=True,
    )
    logger.emit(evt)

    audit_file = tmp_path / "audit.jsonl"
    assert audit_file.exists()
    content = audit_file.read_text(encoding="utf-8")
    assert "HARDWARE_PROFILE_SELECTED" in content
    assert "cpu_lite" in content

