# ADR-0005: Model registry schema extension (`config/models.yaml`)

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.

**Status**: Proposed   **Date**: 2026-11-03

## Context
**Today: models are mapped by role, not capability.**
- `AGENT_MODEL_MAP` in `backend/config.py:25-32` maps the roles `orchestrator/math/vision_table/reasoning/verification/synthesis` to Ollama tags read from the environment.
- `model_service.stream_response` resolves a "capability" by dictionary lookup (`backend/model_service.py:257-265`).
- Vision support is guessed from substrings in the model name (`:357`).

**On a 404 it silently falls back to `OLLAMA_MODEL`** (`:385-390`), which is pitfall §11.5:
- `backend/.env` asks for qwen2.5:7b-instruct, qwen2.5-math:7b, deepseek-r1-distill-qwen:7b and qwen2.5:3b-instruct.
- None of them are installed (`ollama list`, 2026-11-03).
- So every role actually runs on qwen2.5:3b.

**There's no version, VRAM, context or quality metadata.** `num_ctx` is hardcoded to 2048 (`:373`).

**What the plan allows.** PLAN §7.1 defines the registry fields (name, provider, endpoint, capabilities, max_context, default, version, vram_gb, rank). PLAN §7 says "add fields only via ADR". The capability tags are §7.1 plus `asr` and `rerank` at V1.

**What the user's request adds.** The improvement proposal (§4.4) needs:
- per-model quality, latency and quantization data
- tool-calling support
- hardware tiers (ADR-0007)

Ollama on this machine also exposes `*:cloud` models (glm-5.1, glm-5, kimi-k2.5). These are remote inference through a loopback endpoint, so a loopback check alone does not prove zero egress.

## Options considered
**A. Extend §7.1 with optional, validated fields and new capability tags. Validation runs at load time.**
- Pro: one registry drives routing, cascade, scheduling and deployment sizing.
- Con: more schema to keep current.

**B. Keep §7.1 exactly. Put measurements in a separate `model_metrics.json`.**
- Pro: a minimal contract.
- Con: routing then needs two sources, and they drift.

**C. Keep `AGENT_MODEL_MAP`.**
- Con: it violates PLAN §2.1, where agents route by capability tag.

## Decision (proposed)
Option A. These additions are all optional unless marked:
```yaml
local:
  cpu_lite:            # hardware-tier block (ADR-0007); same entry schema in every tier
    - name: qwen3-4b-instruct-2507-q4
      provider: ollama                 # ollama | vllm | transformers | gguf | deterministic
      endpoint: http://127.0.0.1:11434
      model_tag: qwen3:4b-instruct-2507-q4_K_M
      capabilities: [general_reasoning, planning, drafting, summarization, classification, extraction]
      max_context: 32768
      version: "sha256:<ollama blob digest>"   # REQUIRED
      rank: 1                                   # cascade order: lower = try first
      tier: small                               # small | medium | large (escalation ladder)
      vram_gb: 0                                # 0 on CPU
      ram_gb: 3.5
      quant: Q4_K_M
      latency_profile: {ttft_ms_p50: null, tok_s_p50: null, measured_by: null}   # filled ONLY by bench B1
      quality: {}                               # {capability: {score, eval_run_id}} filled ONLY by eval harness
      tool_calling: json_mode                   # native | json_mode | none — re-validated after quantization
      prompt_profile: chatml                    # chatml | alpaca (fine-tuned Mistral, backend/models) | ...
      keep_alive: "30m"
```
- **New capability tags:** `asr`, `rerank`, `sql`, `math`, `translation`, `extraction`, plus `ocr_assist`, `vision` and `embedding` as in §7.1.
- **Load-time validation.** The router refuses to start, with an actionable error, if:
  1. any `local` endpoint is not loopback or allow-listed internal
  2. any `model_tag` ends in `:cloud` or `-cloud`
  3. `version` is missing
  4. an enabled agent's capability has no entry in the selected tier
  5. `quality` or `latency_profile` values lack a provenance id
- **Missing models fail closed.** If a model is missing at runtime, the router raises `NoModelForCapability` / `MODEL_FAILURE`. There is **no silent fallback**. Failover goes only to the next `rank` on the same tag, audited as `MODEL_FAILOVER` (PLAN §8.2).
- **New audit event type `MODEL_ESCALATION`** (PLAN §7.8). Details: `{from_model, to_model, capability, trigger: schema_invalid|critic_fail|low_confidence, hop, budget_left}`.
- **The fine-tuned Mistral 7B is preserved** (`backend/models/config.json`, `MistralForCausalLM`, about 7.25B parameters) as an entry with `provider: transformers|gguf` and `prompt_profile: alpaca`, keeping the format it was trained on (`backend/model_service.py:14-24`).

## Alternatives rejected and why
- **B:** two sources of truth.
- **C:** violates the plan's core principle.

## Consequences
- Routing stays "dumb" (PLAN §8.2). `quality` and `latency` become tiebreakers only once they're populated by the eval harness and bench. Until then: capability → health → VRAM fit → `rank`.
- **Files:**
  - new: `config/models.yaml` (at the **repo root**, because a `backend/config/` package would shadow `backend/config.py`), `backend/router/{router,health,model_onboarding}.py`
  - deprecated, not deleted: `AGENT_MODEL_MAP` in `backend/config.py`. It's kept as a generated fallback until the router lands.
- Cost to change later: medium. The schema is read by the router, the scheduler, the admin UI and the bench.

## Open items
- **OI-1:** confirm the set of new capability tags.
- **OI-2:** whether the fine-tuned Mistral stays in the roster (it needs ~29 GB RAM in fp32 per `backend/test_model.py:13`; GGUF would be required on the `cpu_lite` tier).

## Verification status
- The installed and missing models were confirmed with `ollama list` on 2026-11-03.
- The silent fallback was confirmed by code reading. It's also documented in `bench/FIX_PROPOSALS.md:8-51`.
- No registry file or validator exists yet.
