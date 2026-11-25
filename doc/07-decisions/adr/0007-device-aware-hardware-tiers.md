# ADR-0007: Device-aware hardware tiers selected at backend startup
**Status**: Proposed   **Date**: 2026-11-03

## Context
**The owner's request** (2026-11-03, verbatim):
> "make it device specific , means when i7 will be used then less agents will be used and low models will be used .. where as when GPU device will be used then the better model will be used … when on mac , then the project will be in full quality mode , and the device will be checked on stadting the backend"

**Today the backend ignores the hardware.**
- It always uses the same `AGENT_MODEL_MAP` (`backend/config.py:25-32`).
- Startup in `lifespan` (`backend/main.py:38-49`) only kicks off indexing of the MiG-21 manual and the model load.
- ColPali picks `cuda` or `cpu` (`backend/colpali_retrieval_service.py:48`), but nothing else adapts.
- Ollama options are fixed: `num_thread: 8`, `num_ctx: 2048` (`backend/model_service.py:372-373`).

**Dev hardware, checked 2026-11-03:**
- Intel i7-1185G7, 8 threads.
- Intel Iris Xe iGPU only (`lspci`). No `/dev/nvidia*`, no `nvidia-smi`.
- 31 GiB RAM.
- B1 measured qwen2.5:3b at 9.11 tok/s and gemma4:e4b at 5.06 tok/s on this machine (`bench/results/b1_per_model_AS_IS.json:18`, `:143`).

**Plan constraint.** PLAN §5.3 requires strict code parity: "only `config/models.yaml` and the env var change between environments. No `if env == "prod"` branches in agent code". PLAN §8.2 asks for `vram_gb` per entry. PLAN §12.6 says production hardware sizing is deferred.

## Options considered
**A. A startup hardware probe selects a tier. The tier selects a registry block (ADR-0005) and per-tier agent enablement in `config/agents.yaml`. Agent code is tier-agnostic.**
- Pros:
  - Meets the request.
  - Preserves §5.3 parity as environment × tier, both config only.
  - Testable with mocked probes.
- Cons: more config blocks to maintain; tier-specific quality must be evaluated per tier.

**B. Manual tier through an env var only.**
- Pro: simplest.
- Con: doesn't meet "the device will be checked on starting the backend".

**C. Dynamic per-request autoscaling based on live VRAM.**
- Pro: optimal use.
- Con: complex, hard to test, unpredictable latency; premature before measurements.

## Decision (proposed)
Option A, with an `AEROMIND_HW_TIER` env override that also covers Option B.

**Probe.**
- **Module:** `backend/router/hardware_probe.py`. It uses only stdlib `platform`, `os` and `subprocess`, plus `torch` if already importable, so there's no new dependency.
- **When it runs:** first in `lifespan`, before the model load.
- **What it detects:**
  - OS and architecture.
  - NVIDIA: `nvidia-smi --query-gpu=name,memory.total --format=csv`. GPU count and VRAM.
  - AMD: `rocm-smi`.
  - Apple Silicon: `Darwin` + `arm64`, unified memory via `sysctl -n hw.memsize`, chip via `sysctl -n machdep.cpu.brand_string`.
  - CPU cores and RAM.
  - Ollama reachability: `GET {OLLAMA_HOST}/api/tags` and `/api/ps`.
- **Output:** `DeviceProfile{tier, accelerator, gpu_count, vram_gb, unified_mem_gb, ram_gb, cpu_cores, detected_at, override}`.

**Tier rules** live in `config/hardware_profiles.yaml`. These defaults are proposed:

| Tier | Detected when | Agents enabled | Parallel LLM / max plan depth |
|---|---|---|---|
| `cpu_lite` | no CUDA/ROCm/Metal (this i7 / Iris Xe box) | Main (planner and drafter share one model), Retrieval, Data Analysis (deterministic first), Multimodal limited to OCR (VL only on explicit request), Critic, Memory. Off: Correlation, Optimization, ColPali, video | 1 / 3 |
| `gpu_standard` | one GPU, 8–16 GB | above + Coding + VL by default | 2 / 5 |
| `gpu_high` | one GPU ≥ 24 GB | full plan roster + Correlation + ColPali | 3 / 6 |
| `gpu_multi` | two or more GPUs / server | full roster + Optimization; vLLM per GPU | VRAM-scheduled / 6 |
| `apple_full` | Apple Silicon (Metal; ColPali on `mps`) | **full roster: full-quality mode** | 3 / 6 |

**How the tier is applied.**
- `ModelRouter(environment, hardware_tier)` loads `local.<tier>` from `config/models.yaml`.
- `config/agents.yaml` holds per-tier `enabled`, `max_parallel` and `max_plan_depth`.

**Visibility.**
- The chosen tier is audited as `HARDWARE_PROFILE_SELECTED`.
- It's exposed in `/api/health`.
- It's shown as a UI badge (e.g. "Lite mode: CPU").
- Disabled agents are reported as "not available on this device" (PLAN §8.9 `pending_capabilities`), never silently skipped.

**Invariants (each gets a test):**
1. **Safety never depends on the tier.** The deterministic Critic layer, permission checks, audit, egress guard and approval gating are enabled in every tier. Tiers change capacity only.
2. **The embedding model is identical across tiers.** bge-m3 or nomic-embed-text, per ADR-0004. Otherwise an index built on one device can't be queried on another.
3. Every enabled agent's capability resolves in the selected tier, or is marked unavailable.
4. There are no `if tier ==` branches in `backend/agents/**`. This is enforced by a grep test.
5. Probe classification is unit-tested with mocked outputs: i7 without GPU → `cpu_lite`; RTX 4090 24 GB → `gpu_high`; M3 Max 64 GB → `apple_full`; M1 8 GB → `apple_full` with small models and a warning.

## Alternatives rejected and why
- **B alone:** doesn't satisfy startup detection.
- **C:** a routing dimension that isn't measured yet (PLAN §8.2: "a routing dimension you can't measure is worse than not having it").

## Consequences
- **Files:**
  - new: `backend/router/hardware_probe.py`, `config/hardware_profiles.yaml`, `config/agents.yaml`
  - modified: `backend/main.py` (lifespan), `backend/model_service.py` (`num_ctx` / `num_thread` from the tier), `frontend/src/components/TopBar.jsx` (badge)
- **The eval harness must report results per tier.** A fixture pass on `apple_full` does not imply a pass on `cpu_lite`.
- Cost to change later: low. It's config, and tiers can be added without code changes.

## Open items
- **OI-1 (Mac):** "full quality" on a Mac with 16 GB or less can't fit 27–32B models. The recommendation is that `apple_full` always enables the full roster but sizes models by unified memory: ≥48 GB → 32B-class, 24–36 GB → 14B-class, ≤16 GB → 8B-class with a visible warning. The other option is always using the largest models. **Owner decision.**
- **OI-2:** which Mac models and GPU models are actual targets. The 24 GB GPU MVP tier is assumed; it can't be verified on this machine.
- **OI-3:** whether the UI may switch tiers at runtime, or only the env override at startup.
- **OI-4:** Intel iGPU acceleration (OpenVINO / SYCL builds of llama.cpp) would be a new dependency; out of scope unless requested.

## Verification status
- The dev hardware was detected manually on 2026-11-03 (`lspci`, `free -h`, `/proc/cpuinfo`, no `nvidia-smi`).
- No probe code exists. NVIDIA, AMD and Apple paths are **untested here**, since no such hardware is available.
