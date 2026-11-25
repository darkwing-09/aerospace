"""QW11 / ADR-0007: device detection and tier selection (mocked probes)."""
import pytest

from config import settings
from router import hardware_probe as hp

CFG = hp.load_profiles(settings.HARDWARE_PROFILES_PATH)


def _runner(outputs):
    def run(cmd):
        return outputs.get(cmd[0])
    return run


def _detect(system, machine, outputs):
    return hp.detect_device(run=_runner(outputs), system=system, machine=machine)


def test_i7_without_gpu_is_cpu_lite():
    prof = _detect("Linux", "x86_64", {})
    assert prof.accelerator == "none"
    assert hp.classify(prof, CFG)["tier"] == "cpu_lite"


def test_rtx_4090_is_gpu_high():
    prof = _detect("Linux", "x86_64", {"nvidia-smi": "NVIDIA GeForce RTX 4090, 24564\n"})
    assert prof.accelerator == "nvidia" and prof.vram_gb == 24.0
    assert hp.classify(prof, CFG)["tier"] == "gpu_high"


def test_rtx_4060_is_gpu_standard_and_small_gpu_is_cpu_lite():
    std = _detect("Linux", "x86_64", {"nvidia-smi": "NVIDIA GeForce RTX 4060 Ti, 16380\n"})
    assert hp.classify(std, CFG)["tier"] == "gpu_standard"
    tiny = _detect("Linux", "x86_64", {"nvidia-smi": "NVIDIA GeForce GTX 1650, 4096\n"})
    assert hp.classify(tiny, CFG)["tier"] == "cpu_lite"


def test_two_a100_is_gpu_multi():
    prof = _detect("Linux", "x86_64", {"nvidia-smi": "NVIDIA A100-SXM4-80GB, 81920\nNVIDIA A100-SXM4-80GB, 81920\n"})
    assert prof.gpu_count == 2
    assert hp.classify(prof, CFG)["tier"] == "gpu_multi"


def test_amd_rocm_detected():
    out = "device,VRAM Total Memory (B),VRAM Total Used Memory (B)\ncard0,25753026560,0\n"
    prof = _detect("Linux", "x86_64", {"rocm-smi": out})
    assert prof.accelerator == "amd"
    assert hp.classify(prof, CFG)["tier"] == "gpu_high"


@pytest.mark.parametrize("mem_bytes,size_class,warn", [
    (64 * 1024**3, "32b", False),   # M3 Max 64 GB
    (32 * 1024**3, "14b", False),
    (8 * 1024**3, "8b", True),      # M1 8 GB
])
def test_apple_silicon_is_full_quality_scaled_by_memory(mem_bytes, size_class, warn):
    prof = _detect("Darwin", "arm64", {"sysctl": str(mem_bytes)})
    choice = hp.classify(prof, CFG)
    assert choice["tier"] == "apple_full"
    assert choice["size_class"] == size_class
    assert bool(choice["warning"]) is warn
    models = hp.tier_agent_models(CFG, "apple_full", size_class)
    assert set(models) == set(CFG["tiers"]["cpu_lite"]["agent_models"])


def test_override_and_invalid_override():
    prof = _detect("Linux", "x86_64", {})
    assert hp.classify(prof, CFG, override="gpu_high")["tier"] == "gpu_high"
    with pytest.raises(ValueError, match="not a valid tier"):
        hp.classify(prof, CFG, override="turbo")


def test_safety_enabled_in_every_tier_and_single_embedding_model():
    for name, tier in CFG["tiers"].items():
        assert tier["safety"] and all(tier["safety"].values()), f"safety disabled in {name}"
        assert "embedding_model" not in tier, f"{name} must not define its own embedding model"
    assert CFG["embedding_model"]


def test_every_tier_maps_every_role():
    roles = set(settings.AGENT_MODEL_MAP)
    for name in hp.VALID_TIERS:
        tier = CFG["tiers"][name]
        classes = tier.get("size_classes") or {None: tier}
        for cls in classes.values():
            assert roles <= set(cls["agent_models"]), f"{name} missing roles"


def test_no_cloud_models_in_any_tier():
    for name in hp.VALID_TIERS:
        tier = CFG["tiers"][name]
        classes = tier.get("size_classes") or {None: tier}
        for cls in classes.values():
            for model in cls["agent_models"].values():
                assert not model.endswith(":cloud") and "-cloud" not in model, f"{name}: {model}"


def test_apply_overlay_respects_explicit_env_pins():
    class S:
        HARDWARE_PROFILES_PATH = settings.HARDWARE_PROFILES_PATH
        AEROMIND_HW_TIER = "cpu_lite"
        AGENT_MODEL_MAP = {"synthesis": "x", "math": "y"}
    s = S()
    summary = hp.apply_hardware_tier(s, run=_runner({}), env={"MATH_MODEL": "pinned:7b"})
    assert s.AGENT_MODEL_MAP["synthesis"] == CFG["tiers"]["cpu_lite"]["agent_models"]["synthesis"]
    assert s.AGENT_MODEL_MAP["math"] == "pinned:7b"
    assert summary["pinned_by_env"] == {"math": "pinned:7b"}
    assert summary["tier"] == "cpu_lite"
