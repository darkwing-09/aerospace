"""Detect the host's compute hardware at startup and pick a hardware tier.

Why this exists (ADR-0007, user request 2026-11-03): the same code must run
lean on a CPU-only i7 laptop (fewer agents, small models), use larger models
when an NVIDIA/AMD GPU is present (sized by VRAM), and run in full-quality mode
on Apple Silicon. The tier only *selects configuration* from
config/hardware_profiles.yaml — agent code never branches on it (plan §5.3
code parity), and safety components are enabled in every tier.

Detection uses only the standard library plus vendor CLIs if present
(nvidia-smi, rocm-smi, sysctl), so it adds no dependency and never touches the
network.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

VALID_TIERS = ("cpu_lite", "gpu_standard", "gpu_high", "gpu_multi", "apple_full")

# Per-role environment variables an operator may export to pin a model
# explicitly; these win over the tier overlay (operator intent beats defaults).
ROLE_ENV_VARS = {
    "orchestrator": "ORCHESTRATOR_MODEL",
    "math": "MATH_MODEL",
    "vision_table": "VISION_MODEL",
    "reasoning": "REASONING_MODEL",
    "verification": "VERIFICATION_MODEL",
    "synthesis": "SYNTHESIS_MODEL",
}

Runner = Callable[[list[str]], Optional[str]]


@dataclass
class DeviceProfile:
    os: str
    arch: str
    accelerator: str                 # "nvidia" | "amd" | "apple" | "none"
    gpu_names: list[str] = field(default_factory=list)
    gpu_count: int = 0
    vram_gb: float = 0.0             # largest single GPU, GiB
    total_vram_gb: float = 0.0
    unified_mem_gb: float = 0.0      # Apple Silicon only
    ram_gb: float = 0.0
    cpu_cores: int = 0
    cpu_name: str = ""
    detected_at: str = ""


# ── Detection ────────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> Optional[str]:
    """Run a vendor CLI if it exists; return stdout or None. Never raises."""
    if shutil.which(cmd[0]) is None:
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def parse_nvidia_smi(output: str) -> list[tuple[str, float]]:
    """Parse `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`."""
    gpus = []
    for line in output.strip().splitlines():
        if "," not in line:
            continue
        name, mem = line.rsplit(",", 1)
        try:
            gpus.append((name.strip(), round(float(mem.strip()) / 1024.0, 1)))  # MiB → GiB
        except ValueError:
            continue
    return gpus


def parse_rocm_smi(output: str) -> list[float]:
    """Parse `rocm-smi --showmeminfo vram --csv`; returns VRAM totals in GiB."""
    totals = []
    lines = [l for l in output.strip().splitlines() if l.strip()]
    if not lines:
        return totals
    header = [h.strip().lower() for h in lines[0].split(",")]
    idx = next((i for i, h in enumerate(header) if "total" in h and "vram" in h), None)
    if idx is None:
        return totals
    for line in lines[1:]:
        cols = line.split(",")
        try:
            totals.append(round(int(cols[idx]) / 1024**3, 1))
        except (ValueError, IndexError):
            continue
    return totals


def _linux_ram_gb() -> float:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (ValueError, OSError, AttributeError):
        return 0.0


def _cpu_name() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or ""


def detect_device(run: Runner = _run, system: str | None = None, machine: str | None = None) -> DeviceProfile:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    prof = DeviceProfile(
        os=system, arch=machine, accelerator="none",
        cpu_cores=os.cpu_count() or 0,
        detected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    if system == "Darwin":
        mem = run(["sysctl", "-n", "hw.memsize"])
        try:
            prof.ram_gb = round(int((mem or "0").strip()) / 1024**3, 1)
        except ValueError:
            prof.ram_gb = 0.0
        prof.cpu_name = (run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "").strip()
        if machine in ("arm64", "aarch64"):
            prof.accelerator = "apple"
            prof.unified_mem_gb = prof.ram_gb
            prof.gpu_names = [prof.cpu_name or "Apple Silicon"]
            prof.gpu_count = 1
        return prof

    prof.ram_gb = _linux_ram_gb()
    prof.cpu_name = _cpu_name()

    nv = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = parse_nvidia_smi(nv) if nv else []
    if gpus:
        prof.accelerator = "nvidia"
        prof.gpu_names = [g[0] for g in gpus]
        prof.gpu_count = len(gpus)
        prof.vram_gb = max(g[1] for g in gpus)
        prof.total_vram_gb = round(sum(g[1] for g in gpus), 1)
        return prof

    rocm = run(["rocm-smi", "--showmeminfo", "vram", "--csv"])
    amd = parse_rocm_smi(rocm) if rocm else []
    if amd:
        prof.accelerator = "amd"
        prof.gpu_names = [f"AMD GPU {i}" for i in range(len(amd))]
        prof.gpu_count = len(amd)
        prof.vram_gb = max(amd)
        prof.total_vram_gb = round(sum(amd), 1)
    return prof


# ── Classification ───────────────────────────────────────────────────────

def load_profiles(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"Hardware profile config not found: {p}. It is required to select models (ADR-0007).")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    missing = [t for t in VALID_TIERS if t not in cfg.get("tiers", {})]
    if missing:
        raise RuntimeError(f"{p} is missing tier definitions: {missing}")
    return cfg


def classify(prof: DeviceProfile, cfg: dict[str, Any], override: str = "") -> dict[str, Any]:
    """Return {tier, size_class, reason, warning}. Pure function — easy to test."""
    th = cfg.get("thresholds", {})
    if override:
        if override not in VALID_TIERS:
            raise ValueError(f"AEROMIND_HW_TIER={override!r} is not a valid tier. Valid: {', '.join(VALID_TIERS)}")
        tier, reason = override, "forced by AEROMIND_HW_TIER"
    elif prof.accelerator == "apple":
        tier, reason = "apple_full", f"Apple Silicon, {prof.unified_mem_gb} GB unified memory"
    elif prof.accelerator in ("nvidia", "amd") and prof.gpu_count >= th.get("gpu_multi_min_gpus", 2):
        tier, reason = "gpu_multi", f"{prof.gpu_count} GPUs, {prof.total_vram_gb} GB VRAM total"
    elif prof.accelerator in ("nvidia", "amd") and prof.vram_gb >= th.get("gpu_high_min_vram_gb", 23):
        tier, reason = "gpu_high", f"{prof.gpu_names[0] if prof.gpu_names else 'GPU'} with {prof.vram_gb} GB VRAM"
    elif prof.accelerator in ("nvidia", "amd") and prof.vram_gb >= th.get("gpu_standard_min_vram_gb", 8):
        tier, reason = "gpu_standard", f"{prof.gpu_names[0] if prof.gpu_names else 'GPU'} with {prof.vram_gb} GB VRAM"
    else:
        small_gpu = f" (GPU with {prof.vram_gb} GB is below the GPU threshold)" if prof.accelerator in ("nvidia", "amd") else ""
        tier, reason = "cpu_lite", f"no supported GPU accelerator{small_gpu}"

    size_class, warning = None, None
    tier_cfg = cfg["tiers"][tier]
    if tier_cfg.get("size_classes"):
        mem = prof.unified_mem_gb if tier == "apple_full" else prof.vram_gb
        for rule in th.get("apple_memory_classes", []):
            if mem >= rule.get("min_gb", 0):
                size_class, warning = rule["size_class"], rule.get("warning")
                break
        if size_class is None:
            size_class = sorted(tier_cfg["size_classes"])[0]
    return {"tier": tier, "size_class": size_class, "reason": reason, "warning": warning}


def tier_agent_models(cfg: dict[str, Any], tier: str, size_class: str | None) -> dict[str, str]:
    tier_cfg = cfg["tiers"][tier]
    if tier_cfg.get("size_classes"):
        return dict(tier_cfg["size_classes"][size_class]["agent_models"])
    return dict(tier_cfg["agent_models"])


def get_current_tier(run: Runner = _run, override: str | None = None) -> str:
    """Detect the device and return the chosen tier name (e.g. 'cpu_lite')."""
    if override:
        return override.strip()
    env_override = os.environ.get("AEROMIND_HW_TIER")
    if env_override:
        return env_override.strip()
    root = Path(__file__).resolve().parent.parent.parent
    cfg_path = root / "config" / "hardware_profiles.yaml"
    cfg = load_profiles(cfg_path)
    prof = detect_device(run=run)
    choice = classify(prof, cfg)
    return choice["tier"]


def apply_hardware_tier(settings, run: Runner = _run, env: dict | None = None) -> dict[str, Any]:
    """Detect hardware, choose a tier, and overlay the tier's models onto
    settings.AGENT_MODEL_MAP (explicitly exported per-role env vars win).
    Returns a JSON-serialisable summary for /api/health and logs."""
    env = os.environ if env is None else env
    cfg = load_profiles(settings.HARDWARE_PROFILES_PATH)
    prof = detect_device(run=run)
    choice = classify(prof, cfg, override=(settings.AEROMIND_HW_TIER or "").strip())
    tier, size_class = choice["tier"], choice["size_class"]
    tier_cfg = cfg["tiers"][tier]

    overlay = tier_agent_models(cfg, tier, size_class)
    pinned = {}
    for role, model in overlay.items():
        env_var = ROLE_ENV_VARS.get(role)
        if env_var and env.get(env_var):
            pinned[role] = env[env_var]
        else:
            settings.AGENT_MODEL_MAP[role] = model
    settings.AGENT_MODEL_MAP.update(pinned)

    summary = {
        "tier": tier,
        "size_class": size_class,
        "label": tier_cfg.get("label", tier),
        "reason": choice["reason"],
        "warning": choice["warning"],
        "device": asdict(prof),
        "agents_enabled": tier_cfg.get("agents_enabled", []),
        "agents_disabled": tier_cfg.get("agents_disabled", []),
        "max_parallel_llm_calls": tier_cfg.get("max_parallel_llm_calls"),
        "max_plan_depth": tier_cfg.get("max_plan_depth"),
        "safety": tier_cfg.get("safety", {}),
        "embedding_model": cfg.get("embedding_model"),
        "agent_models": dict(settings.AGENT_MODEL_MAP),
        "pinned_by_env": pinned,
    }
    # Audit event type per ADR-0007; written to the log until the audit sink (task 0.4) exists.
    print(f"[AeroMind] HARDWARE_PROFILE_SELECTED tier={tier} size_class={size_class} reason={choice['reason']}"
          + (f" WARNING={choice['warning']}" if choice["warning"] else ""))
    return summary
