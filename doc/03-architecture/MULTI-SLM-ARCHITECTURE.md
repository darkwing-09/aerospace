# AeroMind 2.0: Multi-SLM Subagent Architecture

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.


**Status:** Proposed. Implementation design for proposal §4.4. Implements PLAN §6–§8 and §11; depends on ADR-0003 (orchestration), ADR-0005 (registry schema), ADR-0007 (hardware tiers).
**Audience:** the coding agent implementing Phases 0–2, and reviewers of those phases.
**Plan references:** "PLAN §x" means `PROJECT-IMPLEMENTATION-PLAN.md` section x. Pitfall numbers are PLAN §11.
**Open items** (never resolve silently, see §13):
- C1 local-only vs. dual profile
- PLAN §12.7 embedding model
- 24 GB hardware not verified on the dev box
- Mac sizing policy

---

## 0. Why this document exists

Today AeroMind maps *roles* to model names through a flat dict (`backend/config.py:25-32`). That mapping has six problems:
- Unknown names silently fall back to `qwen2.5:3b` (`backend/model_service.py:385-390`, pitfall §11.5).
- Vision is detected by substring (`backend/model_service.py:357`).
- The planner is a keyword heuristic (`backend/orchestrator_planner.py:229-230`).
- The emitted DAG is never executed (`backend/agent_orchestrator.py:206-211`, pitfall §11.6).
- The "verification agent" is a canned string (`backend/agent_orchestrator.py:406-427`).
- On the dev box (i7-1185G7, Iris Xe, **no CUDA**, 31 GiB RAM), four of the six configured models are not installed in Ollama.

This document defines the replacement:
- capability-tagged models
- hardware-aware tiers
- an executed DAG
- a cascade from small to large models
- a real Critic gate

It also covers how to get there **without deleting the existing code**.

---

## 1. Capability registry: `config/models.yaml`

### 1.1 Location

`config/` lives at the **repository root**, not in `backend/`. `backend/config.py` is imported as `from config import settings` by every module, and a `backend/config/` package would shadow it.

The router resolves the path as `Path(__file__).resolve().parents[2] / "config"` from `backend/router/router.py`. `AEROMIND_CONFIG_DIR` overrides it.

### 1.2 Capability tag vocabulary

These are the only tags agents may request. Adding a tag requires editing this table and `router/capabilities.py` (an enum), and passing the registry validation tests.

| Tag | Meaning | Typical I/O | Deterministic-first? |
|---|---|---|---|
| `planning` | Decompose a task into a TaskPlan DAG (JSON schema) | text → JSON | yes (templates, §3.2) |
| `general_reasoning` | Open-ended analysis, query formulation, sufficiency judgment | text → text/JSON | no |
| `drafting` | Long-form prose: reports, briefs, RCA narrative | evidence → markdown | no |
| `summarization` | Compress a passage or set of units, keeping refs | text → text | no |
| `classification` | Intent or label from a closed set | text → enum | **yes** (keyword first; model only if ambiguous) |
| `extraction` | Entities, fields, key-values → JSON schema | text → JSON | partially (regex for tags/IDs) |
| `code_gen` | Write Python/SQL for the sandbox | spec → code | no |
| `code_review` / `debugging` | Fix code given a traceback | code + error → code | no |
| `sql` | NL → SQL against a declared schema (V1) | schema + q → SQL | no |
| `math` | Symbolic or numeric reasoning *when no deterministic tool fits* | text → JSON | **yes** (`AvionicsMathEngine`, pandas) |
| `vision` | Describe an image region, chart or diagram, with boxes | image + prompt → JSON | no |
| `ocr_assist` | VLM read of low-confidence OCR regions | image crop → text | **yes** (RapidOCR first) |
| `asr` | Speech → timed transcript | audio → segments | **yes** (it is a tool, not an LLM) |
| `embedding` | Dense vector for chunks and queries | text → float[] | n/a |
| `rerank` | Cross-encoder relevance score | (q, passage) → float | n/a |
| `evaluation` | Critic LLM pass: claim → SUPPORTED/UNSUPPORTED/CONTRADICTED | draft + evidence → JSON | deterministic layer always runs first |
| `translation` | Text between languages, incl. Indic (V1) | text → text | no |

`asr`, `embedding` and `rerank` entries are served by non-chat providers (`faster_whisper`, `ollama_embed`, `cross_encoder`). The router returns a provider-specific client; callers use the matching tool, not `chat()`.

### 1.3 Entry schema (ADR-0005 extends PLAN §7.1)

PLAN §7 says "Add fields only via ADR". **ADR-0005 must be accepted before the new fields below are used for routing.** Until then the router ignores everything except `capabilities`, `default`, `rank` and `endpoint`.

| Field | Type | Required | Source of truth | Used for |
|---|---|---|---|---|
| `name` | str | ✔ | config | logical id used in audit |
| `provider` | `ollama \| vllm \| transformers \| gguf \| faster_whisper \| ollama_embed \| cross_encoder \| huggingface` | ✔ | config | client builder switch |
| `model_ref` | str | ✔ | config | provider-native name (`qwen3:4b-instruct-2507-q4_K_M`) |
| `endpoint` | URL | ✔ (network providers) | config | must be loopback/internal (§1.5 rule V3) |
| `capabilities` | list[tag] | ✔ | config | **primary routing filter** |
| `max_context` | int | ✔ | config | context budget (PLAN §8.6) |
| `vram_gb` | float \| null | ✔ for GPU tiers | measured / model card | VRAM-fit filter, GpuBudget weight |
| `ram_gb` | float | ✔ for cpu_lite/apple | measured | RAM-fit filter on CPU / unified memory |
| `quant` | str | ✔ | config | `q4_K_M`, `awq`, `fp16`, … |
| `latency_profile` | `{ttft_ms_p50, tok_s, measured_on, bench_run_id}` \| null | ✘ | **`bench/b1_per_model.py` only** | tiebreak after ADR (§4.3) |
| `quality` | `{<tag>: {score, eval_run_id}}` \| null | ✘ | **eval harness only** (never hand-edited) | tiebreak after ADR (§4.3) |
| `tool_calling` | `native \| json_mode \| none` | ✔ | validated by Phase 2.3 test | agents that need tools filter on it |
| `version` | `sha256:<64 hex>` | ✔ | `ollama show --modelfile` digest / weight-file sha256 | audit, reproducibility (PLAN §8.14) |
| `rank` | int (1 = try first) | ✔ | config | failover order **and** cascade order (smallest first) |
| `tier` | `small \| medium \| large` | ✔ | config | cascade ceiling (`SubTask.max_tier`) |
| `default` | bool | ✘ | config | PLAN §7.2 resolution rule |
| `prompt_profile` | `chatml \| alpaca \| gemma \| plain` | ✔ for chat | config | shared `assemble_prompt` renders evidence for this template |
| `keep_alive` | `pinned \| warm \| cold` | ✘ (default cold) | config | Ollama `keep_alive` policy (§6.3) |
| `family` | str | ✔ | config | Critic cross-family rule (§7.4) |
| `licence` | str | ✔ | config | release gate: must be on the approved-licence list |

### 1.4 Full example

**Every model name below is a *candidate*.** The `cpu_lite` block lists models verified installed on the dev laptop via `ollama list` (this session). Everything else must be confirmed by the eval harness and a licence check before promotion. The digests are placeholders that the Phase 2.1 task fills in.

```yaml
# config/models.yaml: environment × hardware tier.
# Agents request a capability tag, never a name. Changing models = editing this file.
schema_version: 2            # ADR-0005
embedding_lock:              # rule V5: identical across every tier of an environment
  name: bge-m3
  dim: 1024
  adr: ADR-0008-embedding-model   # PLAN §12.7 open; until decided Phase 0 uses nomic-embed-text (dim 768)

local:
  cpu_lite:                  # x86 / no CUDA / no ROCm / no Metal (e.g. i7-1185G7 + Iris Xe)
    - name: qwen3-4b-instruct
      provider: ollama
      model_ref: qwen3:4b-instruct-2507-q4_K_M      # installed ✔
      endpoint: http://127.0.0.1:11434
      capabilities: [planning, general_reasoning, drafting, summarization, classification, extraction]
      max_context: 8192
      vram_gb: null
      ram_gb: 3.5
      quant: q4_K_M
      tool_calling: json_mode
      version: "sha256:<fill-phase-2.1>"
      rank: 1
      tier: small
      default: true
      prompt_profile: chatml
      keep_alive: pinned
      family: qwen
      licence: apache-2.0
      latency_profile: null      # fill from B1 re-run (old B1 measured qwen2.5:3b at 9.11 tok/s, 552 ms warm TTFT)
      quality: null
    - name: qwen2.5-3b
      provider: ollama
      model_ref: qwen2.5:3b                          # installed ✔ (today's OLLAMA_MODEL)
      endpoint: http://127.0.0.1:11434
      capabilities: [evaluation, classification, summarization]
      max_context: 8192
      vram_gb: null
      ram_gb: 2.3
      quant: q4_K_M
      tool_calling: json_mode
      version: "sha256:<fill>"
      rank: 1
      tier: small
      prompt_profile: chatml
      keep_alive: warm
      family: qwen2.5            # different generation from qwen3; cross-family rule relaxed on cpu_lite (§7.4)
      licence: qwen-research     # CHECK: Qwen2.5-3B licence differs from Apache. Release gate
    - name: qwen2.5-coder-1.5b
      provider: ollama
      model_ref: qwen2.5-coder:1.5b                  # installed ✔
      endpoint: http://127.0.0.1:11434
      capabilities: [code_gen, code_review, debugging, sql]
      max_context: 8192
      vram_gb: null
      ram_gb: 1.2
      quant: q4_K_M
      tool_calling: json_mode
      version: "sha256:<fill>"
      rank: 1
      tier: small
      prompt_profile: chatml
      keep_alive: cold
      family: qwen
      licence: apache-2.0
    - name: qwen3-vl-2b
      provider: ollama
      model_ref: qwen3-vl:2b                         # installed ✔
      endpoint: http://127.0.0.1:11434
      capabilities: [vision, ocr_assist]
      max_context: 8192
      vram_gb: null
      ram_gb: 2.4
      quant: q4_K_M
      tool_calling: none
      version: "sha256:<fill>"
      rank: 1
      tier: small
      prompt_profile: chatml
      keep_alive: cold
      family: qwen
      licence: apache-2.0
    - name: gemma4-e4b
      provider: ollama
      model_ref: gemma4:e4b                          # installed ✔ (old B1: 5.06 tok/s, 10.2 GB RSS; too slow to be the default critic)
      endpoint: http://127.0.0.1:11434
      capabilities: [evaluation, vision]
      max_context: 8192
      vram_gb: null
      ram_gb: 10.3
      quant: q4_K_M
      tool_calling: none
      version: "sha256:<fill>"
      rank: 2                    # escalation target for evaluation on cpu_lite ("deep check")
      tier: medium
      prompt_profile: gemma
      keep_alive: cold
      family: gemma
      licence: gemma-terms       # CHECK
    - name: aeromind-mistral-7b-ft     # PRESERVED existing fine-tune (backend/models, Mistral 7B, unsloth)
      provider: transformers           # or gguf when USE_LLAMA_CPP=true (backend/model_service.py:88-107)
      model_ref: backend/models
      endpoint: null
      capabilities: [drafting]
      max_context: 8192
      vram_gb: null
      ram_gb: 29                 # fp32 on CPU (backend/model_service.py:140-142); impractical on 31 GiB, hence rank 9
      quant: fp16
      tool_calling: none
      version: "sha256:<sha of model.safetensors.index.json + shards>"
      rank: 9
      tier: medium
      prompt_profile: alpaca     # matches its training format (backend/model_service.py:14-24)
      keep_alive: cold
      family: mistral
      licence: apache-2.0 + dataset-terms   # CHECK provenance mismatch (models/README.md vs export_metadata.json)
      enabled: false             # opt-in; conflict C7
    - name: nomic-embed-text
      provider: ollama_embed
      model_ref: nomic-embed-text:latest             # installed ✔. Phase-0 stand-in; see embedding_lock
      endpoint: http://127.0.0.1:11434
      capabilities: [embedding]
      max_context: 8192
      vram_gb: null
      ram_gb: 0.4
      quant: fp16
      tool_calling: none
      version: "sha256:<fill>"
      rank: 1
      tier: small
      keep_alive: pinned
      family: nomic
      licence: apache-2.0
    - name: faster-whisper-small
      provider: faster_whisper   # new dependency → ADR (ASR engine, PLAN §13)
      model_ref: /opt/aeromind/models/faster-whisper-small-int8
      endpoint: null
      capabilities: [asr]
      max_context: 0
      vram_gb: null
      ram_gb: 1.0
      quant: int8
      tool_calling: none
      version: "sha256:<fill>"
      rank: 1
      tier: small
      family: whisper
      licence: mit

  gpu_standard:              # one NVIDIA/AMD GPU, 8 ≤ VRAM < 20 GB
    - { name: qwen3-8b,        provider: ollama, model_ref: "qwen3:8b-q4_K_M",           endpoint: "http://127.0.0.1:11434", capabilities: [planning, general_reasoning, drafting, summarization, classification, extraction], max_context: 32768, vram_gb: 6.0, ram_gb: 1, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: medium, default: true, prompt_profile: chatml, keep_alive: pinned, family: qwen, licence: apache-2.0 }
    - { name: qwen3-4b-instruct, provider: ollama, model_ref: "qwen3:4b-instruct-2507-q4_K_M", endpoint: "http://127.0.0.1:11434", capabilities: [classification, extraction, summarization], max_context: 32768, vram_gb: 3.2, ram_gb: 1, quant: q4_K_M, tool_calling: json_mode, version: "sha256:<fill>", rank: 1, tier: small, prompt_profile: chatml, keep_alive: warm, family: qwen, licence: apache-2.0 }
    - { name: qwen2.5-coder-7b, provider: ollama, model_ref: "qwen2.5-coder:7b-instruct-q4_K_M", endpoint: "http://127.0.0.1:11434", capabilities: [code_gen, code_review, debugging, sql], max_context: 32768, vram_gb: 5.0, ram_gb: 1, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: medium, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0 }
    - { name: qwen3-vl-4b,     provider: ollama, model_ref: "qwen3-vl:4b",               endpoint: "http://127.0.0.1:11434", capabilities: [vision, ocr_assist], max_context: 16384, vram_gb: 4.0, ram_gb: 1, quant: q4_K_M, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: small, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0 }
    - { name: gemma3-12b,      provider: ollama, model_ref: "gemma3:12b-it-q4_K_M",      endpoint: "http://127.0.0.1:11434", capabilities: [evaluation], max_context: 32768, vram_gb: 8.5, ram_gb: 1, quant: q4_K_M, tool_calling: json_mode, version: "sha256:<fill>", rank: 1, tier: medium, prompt_profile: gemma, keep_alive: cold, family: gemma, licence: gemma-terms }
    - { name: bge-m3,          provider: ollama_embed, model_ref: "bge-m3",              endpoint: "http://127.0.0.1:11434", capabilities: [embedding], max_context: 8192, vram_gb: 1.2, ram_gb: 1, quant: fp16, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: small, keep_alive: pinned, family: bge, licence: mit }
    - { name: bge-reranker-v2-m3, provider: cross_encoder, model_ref: "/opt/aeromind/models/bge-reranker-v2-m3", endpoint: null, capabilities: [rerank], max_context: 8192, vram_gb: 1.1, ram_gb: 1, quant: fp16, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: small, keep_alive: pinned, family: bge, licence: apache-2.0 }
    - { name: faster-whisper-large-v3-turbo, provider: faster_whisper, model_ref: "/opt/aeromind/models/fw-large-v3-turbo-int8", endpoint: null, capabilities: [asr], max_context: 0, vram_gb: 1.6, ram_gb: 1, quant: int8_float16, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: small, family: whisper, licence: mit }

  gpu_high:                  # one GPU ≥ 20 GB (the "24 GB MVP")
    # = gpu_standard, plus/replacing:
    - { name: qwen3-8b,        "...": "as gpu_standard", rank: 1, tier: medium, default: true }
    - { name: qwen3-14b,       provider: ollama, model_ref: "qwen3:14b-q4_K_M",          endpoint: "http://127.0.0.1:11434", capabilities: [planning, general_reasoning, drafting, evaluation], max_context: 32768, vram_gb: 10.5, ram_gb: 1, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 2, tier: large, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0 }   # escalation target
    - { name: qwen3-vl-8b,     provider: ollama, model_ref: "qwen3-vl:8b",               endpoint: "http://127.0.0.1:11434", capabilities: [vision, ocr_assist], max_context: 16384, vram_gb: 6.5, ram_gb: 1, quant: q4_K_M, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: medium, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0 }
    - { name: colqwen2,        provider: transformers, model_ref: "/opt/aeromind/models/colqwen2-v1.0", endpoint: null, capabilities: [embedding_visual], max_context: 0, vram_gb: 4.5, ram_gb: 2, quant: bf16, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: small, family: colpali, licence: CHECK }   # optional page-level index (ADR-0004, conflict C4)
    # gemma3-12b (evaluation), qwen2.5-coder-7b, bge-m3, bge-reranker-v2-m3, faster-whisper-large-v3-turbo: as gpu_standard

  gpu_multi:                 # ≥2 GPUs or server-class. vLLM, one model (group) per GPU
    - { name: qwen3-32b-awq,   provider: vllm, model_ref: "Qwen/Qwen3-32B-AWQ",          endpoint: "http://vllm-general:8000/v1", capabilities: [planning, general_reasoning, drafting, summarization, extraction], max_context: 32768, vram_gb: 20, quant: awq, tool_calling: native, version: "sha256:<fill>", rank: 2, tier: large, prompt_profile: chatml, family: qwen, licence: apache-2.0 }
    - { name: qwen3-8b,        provider: vllm, model_ref: "Qwen/Qwen3-8B",               endpoint: "http://vllm-small:8000/v1", capabilities: [planning, general_reasoning, drafting, summarization, classification, extraction], max_context: 32768, vram_gb: 17, quant: bf16, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: medium, default: true, prompt_profile: chatml, family: qwen, licence: apache-2.0 }
    - { name: qwen3-coder-30b-a3b, provider: vllm, model_ref: "Qwen/Qwen3-Coder-30B-A3B-Instruct", endpoint: "http://vllm-code:8000/v1", capabilities: [code_gen, code_review, debugging, sql], max_context: 65536, vram_gb: 18, quant: awq, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: large, prompt_profile: chatml, family: qwen, licence: apache-2.0 }
    - { name: qwen2.5-vl-32b-awq, provider: vllm, model_ref: "Qwen/Qwen2.5-VL-32B-Instruct-AWQ", endpoint: "http://vllm-vision:8000/v1", capabilities: [vision, ocr_assist], max_context: 32768, vram_gb: 20, quant: awq, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: large, prompt_profile: chatml, family: qwen, licence: CHECK }
    - { name: gemma3-27b,      provider: vllm, model_ref: "google/gemma-3-27b-it",       endpoint: "http://vllm-critic:8000/v1", capabilities: [evaluation], max_context: 32768, vram_gb: 18, quant: awq, tool_calling: json_mode, version: "sha256:<fill>", rank: 1, tier: large, prompt_profile: gemma, family: gemma, licence: gemma-terms }
    # bge-m3, bge-reranker-v2-m3, faster-whisper-large-v3-turbo, colqwen2 as gpu_high (endpoints on an internal network)

  apple_full:                # Apple Silicon (Metal). Sizes scaled by unified memory, see §2.4
    - { name: qwen3-32b,       provider: ollama, model_ref: "qwen3:32b-q4_K_M",          endpoint: "http://127.0.0.1:11434", capabilities: [planning, general_reasoning, drafting, summarization, extraction], max_context: 32768, vram_gb: null, ram_gb: 21, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 2, tier: large, prompt_profile: chatml, keep_alive: warm, family: qwen, licence: apache-2.0, min_unified_mem_gb: 48 }
    - { name: qwen3-14b,       provider: ollama, model_ref: "qwen3:14b-q4_K_M",          endpoint: "http://127.0.0.1:11434", capabilities: [planning, general_reasoning, drafting, summarization, extraction], max_context: 32768, vram_gb: null, ram_gb: 10.5, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 2, tier: large, prompt_profile: chatml, keep_alive: warm, family: qwen, licence: apache-2.0, min_unified_mem_gb: 24, max_unified_mem_gb: 47 }
    - { name: qwen3-8b,        provider: ollama, model_ref: "qwen3:8b-q4_K_M",           endpoint: "http://127.0.0.1:11434", capabilities: [planning, general_reasoning, drafting, summarization, classification, extraction], max_context: 32768, vram_gb: null, ram_gb: 6, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: medium, default: true, prompt_profile: chatml, keep_alive: pinned, family: qwen, licence: apache-2.0 }
    - { name: qwen2.5-coder-14b, provider: ollama, model_ref: "qwen2.5-coder:14b-instruct-q4_K_M", endpoint: "http://127.0.0.1:11434", capabilities: [code_gen, code_review, debugging, sql], max_context: 32768, ram_gb: 9.5, quant: q4_K_M, tool_calling: native, version: "sha256:<fill>", rank: 1, tier: medium, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0, min_unified_mem_gb: 24 }
    - { name: qwen3-vl-8b,     provider: ollama, model_ref: "qwen3-vl:8b",               endpoint: "http://127.0.0.1:11434", capabilities: [vision, ocr_assist], max_context: 16384, ram_gb: 6.5, quant: q4_K_M, tool_calling: none, version: "sha256:<fill>", rank: 1, tier: medium, prompt_profile: chatml, keep_alive: cold, family: qwen, licence: apache-2.0 }
    - { name: gemma3-27b,      provider: ollama, model_ref: "gemma3:27b-it-q4_K_M",      endpoint: "http://127.0.0.1:11434", capabilities: [evaluation], max_context: 32768, ram_gb: 17, quant: q4_K_M, tool_calling: json_mode, version: "sha256:<fill>", rank: 1, tier: large, prompt_profile: gemma, keep_alive: cold, family: gemma, licence: gemma-terms, min_unified_mem_gb: 48 }
    - { name: gemma3-12b,      "...": "as gpu_standard", ram_gb: 8.5, rank: 2, max_unified_mem_gb: 47 }
    # bge-m3, bge-reranker-v2-m3 (device mps), faster-whisper (CPU int8 on Mac), colqwen2 (device mps): as gpu_high

hf:                          # dev hosted profile: ONLY if conflict C1 resolves to "dual profile".
  []                         # Empty by default. conversation.md session 3 asked for "no online connection".
```

The `"...": "as gpu_standard"` shorthand is for readability only. The real file must spell every entry out (no YAML merge magic), or use explicit `&anchor`/`<<: *anchor` that the loader test covers.

### 1.5 Load-time validation (`router/registry.py::validate()`, fail loud at startup)

| Rule | Check | On violation |
|---|---|---|
| V1 coverage | For each tier, ∪capabilities ⊇ capabilities required by that tier's *enabled* agents (`agents.yaml`). If `hf` is non-empty: caps(hf) ⊆ caps(local.<every tier>) (PLAN §7.1 invariant) | `RegistryError` listing the missing (tier, capability) pairs |
| V2 required fields | `name, provider, model_ref, capabilities, max_context, quant, tool_calling, version, rank, tier, family, licence` (+ `prompt_profile` for chat providers) | `RegistryError(entry, field)` |
| V3 endpoint locality | In `local.*`: the host resolves to loopback, RFC1918, a `.internal` name, or a docker service name on the allowlist in `config/network.yaml`. `https://` to a public host is rejected | `RegistryError("non-internal endpoint")` + `SECURITY_VIOLATION` audit |
| V4 no cloud tags | `model_ref` matching `:cloud$`, `-cloud`, or present in `ollama list` with size `-` is rejected. The dev box has `glm-5.1:cloud`, `glm-5:cloud` and `kimi-k2.5:cloud`, all **remote** | `RegistryError` + `SECURITY_VIOLATION`. **Runtime guard too:** the Ollama client refuses any model name not in the loaded registry |
| V5 embedding lock | Every tier's `embedding` entry has the same `model_ref` + `dim` as `embedding_lock` | `RegistryError("embedding drift")`. Changing it = a re-ingestion event (PLAN §8.4, §10.3) |
| V6 version format | `^sha256:[0-9a-f]{64}$`; `<fill>` placeholders are allowed only when `AEROMIND_ALLOW_UNPINNED=1` (dev), never in the prod build | error / warning |
| V7 rank uniqueness | No two entries in the same (tier, capability) share a `rank` | error |
| V8 licence allowlist | `licence` ∈ `config/licences.yaml` approved list (`CHECK` → blocked in prod) | prod: error; dev: warning |
| V9 hosted-only isolation | No `provider: huggingface` entry in any `local.*` block (PLAN §5.3) | error |
| V10 installed check (startup, not import) | For Ollama entries in the selected tier: present in `GET /api/tags`. Missing → entry marked `unavailable`, **never silently substituted** (fixes pitfall §11.5 / `model_service.py:385`) | warn + health status `degraded` with reason |

Tests (all in `tests/unit/router/test_registry.py`):
- `test_every_tier_covers_enabled_agents`
- `test_cloud_tag_rejected`
- `test_public_endpoint_rejected`
- `test_embedding_lock_identical_across_tiers`
- `test_missing_model_is_unavailable_not_substituted`
- `test_hf_capabilities_subset_of_local` (skipped by *selection* only when `hf: []`, asserting emptiness instead)

---

## 2. Hardware probe and tiers (ADR-0007)

### 2.1 `backend/router/hardware_probe.py`

The probe uses the stdlib only (`platform`, `os`, `subprocess`, `shutil`, `json`) plus an optional `torch` import. **No new dependency.** It runs once in the FastAPI `lifespan` (`backend/main.py:38-49`) **before** `model_svc.load_model()`. Each subprocess has a 3 s timeout, and every probe step is wrapped so that a failure degrades to "unknown", never to a crash.

```python
@dataclass(frozen=True)
class GpuInfo:
    vendor: Literal["nvidia", "amd", "apple", "intel"]
    name: str
    vram_gb: float | None          # None for unified memory / iGPU
    compute_usable: bool           # False for Iris Xe (no CUDA/ROCm path for our stack)

@dataclass(frozen=True)
class DeviceProfile:
    tier: Literal["cpu_lite", "gpu_standard", "gpu_high", "gpu_multi", "apple_full"]
    accelerator: Literal["none", "cuda", "rocm", "metal"]
    os: str; arch: str
    cpu_model: str; cpu_cores: int
    ram_gb: float
    unified_mem_gb: float | None   # Apple only
    gpus: tuple[GpuInfo, ...]
    gpu_count: int                 # usable accelerators only
    vram_gb: float                 # max single-GPU VRAM (0 when none)
    ollama_reachable: bool
    ollama_vram_in_use_gb: float | None   # from /api/ps size_vram
    source: Literal["probe", "override"]
    reasons: tuple[str, ...]       # human-readable decision trail, shown in /api/health
    detected_at: str               # ISO-8601 UTC
    def to_dict(self) -> dict: ...
```

**Detection order** (the first conclusive answer wins; every step appends to `reasons`):

| Step | Command / API | Parsing | Fallback |
|---|---|---|---|
| 1 override | env `AEROMIND_HW_TIER` | must be a key in `hardware_profiles.yaml`, else `ValueError` listing the valid tiers (fail loud) | — |
| 2 OS/arch | `platform.system()`, `platform.machine()` | `Darwin`+`arm64` → Apple path | — |
| 3 NVIDIA | `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits` | one line per GPU, MiB → GB | `torch.cuda.is_available()` + `torch.cuda.get_device_properties(i).total_memory` if torch imports; else none |
| 4 AMD | `rocm-smi --showproductname --showmeminfo vram --json` | `VRAM Total Memory (B)` | `torch.version.hip` + `torch.cuda.*` |
| 5 Apple | `sysctl -n hw.memsize`, `sysctl -n machdep.cpu.brand_string` | bytes → GB; chip string ("Apple M3 Max") | `platform.processor()` |
| 6 Intel/other iGPU | `lspci` (Linux) grep VGA | recorded with `compute_usable=False` | — |
| 7 CPU/RAM | `/proc/meminfo` MemTotal; `os.sysconf('SC_PAGE_SIZE')*SC_PHYS_PAGES`; `os.cpu_count()`; `/proc/cpuinfo` model name | — | — |
| 8 Ollama | `GET {OLLAMA_HOST}/api/ps` (2 s) | sum of `size_vram` | `ollama_reachable=False` (the tier still selects; health = degraded) |

**Never** probe by sending data anywhere. All commands are local, and the egress socket guard in tests must stay green while the probe runs.

### 2.2 `config/hardware_profiles.yaml`

```yaml
# First matching rule wins (top → bottom). Thresholds are config, not code.
rules:
  - tier: gpu_multi
    when: { accelerator: [cuda, rocm], gpu_count_gte: 2, vram_gb_gte: 20 }
  - tier: gpu_high
    when: { accelerator: [cuda, rocm], vram_gb_gte: 20 }
  - tier: gpu_standard
    when: { accelerator: [cuda, rocm], vram_gb_gte: 8 }
  - tier: apple_full
    when: { accelerator: [metal] }           # user decision: Mac = full quality (sizes scale, §2.4)
  - tier: cpu_lite
    when: {}                                 # default: x86 CPU, iGPU, or GPU < 8 GB
safety_margin:
  vram_fraction_usable: 0.90                 # keep 10% headroom for KV-cache spikes
  ram_reserve_gb: 6                          # OS + browser + app on the dev box (31 GiB measured)
apple_memory_scaling:                        # §2.4. Thresholds on unified memory
  large_gte_gb: 48                           # 32B-class planner escalation, 27B critic
  medium_gte_gb: 24                          # 14B-class
  # below medium: 8B-class + visible "memory-limited" warning
warn_if:
  ollama_unreachable: true
  tier_overridden: true
```

### 2.3 `config/agents.yaml` (per tier)

The agent contract fields (PLAN §3.6) are tier-independent. Only `enabled`, `max_parallel`, `max_plan_depth` and the budgets vary.

```yaml
agents:                      # tier-independent contract
  main:          { capability: planning,          tools: [agents.*],                                retry_budget: 1, max_steps: 12 }
  execution:     { capability: drafting,          tools: [write_docx, write_xlsx, write_pptx, render_chart, search_knowledge_base], retry_budget: 2, max_steps: 6 }
  coding:        { capability: code_gen,          tools: [run_python_sandboxed, ruff_check, pytest_run], retry_budget: 3, max_steps: 8, min_role: ANALYST }
  retrieval:     { capability: general_reasoning, tools: [search_knowledge_base, rerank, graph_query], retry_budget: 2, max_steps: 4 }
  data_analysis: { capability: code_gen,          tools: [run_pandas_sandboxed, avionics_math, render_chart], retry_budget: 3, max_steps: 6 }
  multimodal:    { capability: vision,            tools: [ocr_extract, vlm_describe, asr_transcribe, frame_sampler], retry_budget: 2, max_steps: 6 }
  critic:        { capability: evaluation,        tools: [search_knowledge_base], retry_budget: 1, max_steps: 2, read_only: true }
  correlation:   { capability: general_reasoning, tools: [graph_query, entity_resolve, similarity], retry_budget: 2, max_steps: 4, read_only: true }
  memory:        { capability: null,              tools: [memory_store] }
  optimization:  { capability: general_reasoning, tools: [audit_reader, proposal_queue_writer], mode: offline_batch }

tiers:
  cpu_lite:
    enabled: [main, execution, retrieval, data_analysis, multimodal, critic, memory]
    disabled_reason: { coding: "sandboxed code loop too slow on CPU; enable via AEROMIND_ENABLE_AGENTS", correlation: "V1 + needs graph", optimization: "offline only" }
    multimodal_mode: ocr_first          # VLM only when user asks or OCR confidence < 0.6
    colpali: false
    max_parallel_llm: 1
    max_plan_depth: 3
    critic_llm_pass: factual_only       # deterministic layer ALWAYS; LLM pass on factual subtasks + final
    escalation_max_hops: 1
  gpu_standard:
    enabled: [main, execution, coding, retrieval, data_analysis, multimodal, critic, memory]
    multimodal_mode: vlm_on
    colpali: false
    max_parallel_llm: 2
    max_plan_depth: 5
    critic_llm_pass: all
    escalation_max_hops: 1
  gpu_high:
    enabled: [main, execution, coding, retrieval, data_analysis, multimodal, critic, correlation, memory]
    multimodal_mode: vlm_on
    colpali: true
    max_parallel_llm: 3
    max_plan_depth: 6
    critic_llm_pass: all
    escalation_max_hops: 1
  gpu_multi:
    enabled: [main, execution, coding, retrieval, data_analysis, multimodal, critic, correlation, memory, optimization]
    multimodal_mode: vlm_on
    colpali: true
    max_parallel_llm: vram_scheduled
    max_plan_depth: 6
    critic_llm_pass: all
    escalation_max_hops: 2
  apple_full:
    enabled: [main, execution, coding, retrieval, data_analysis, multimodal, critic, correlation, memory, optimization]
    multimodal_mode: vlm_on
    colpali: true                       # device mps
    max_parallel_llm: 3                 # 2 when unified_mem_gb < 24
    max_plan_depth: 6
    critic_llm_pass: all
    escalation_max_hops: 1

safety:                      # NOT per tier. Loader rejects any tier key that names these.
  permission_checks: always
  audit: always
  egress_guard: always
  critic_deterministic_layer: always
  approval_gate: always
  injection_guard: always
```

### 2.4 Mac memory scaling (open question for the user)

The user asked for "Mac = full quality mode". `apple_full` therefore **always enables the full agent roster**, but model *sizes* are filtered by `min_unified_mem_gb` / `max_unified_mem_gb` on each entry:

| Unified memory | Planner default → escalation | Critic | Coder | Warning |
|---|---|---|---|---|
| ≥ 48 GB (e.g. M3 Max 64 GB) | qwen3-8b → qwen3-32b | gemma3-27b | qwen2.5-coder-14b | — |
| 24–47 GB | qwen3-8b → qwen3-14b | gemma3-12b | qwen2.5-coder-14b | — |
| ≤ 23 GB (e.g. M1 8 GB) | qwen3-4b → qwen3-8b | gemma3-4b-class | qwen2.5-coder-1.5b | UI: "Full mode on limited memory: larger models unavailable" |

If the user instead wants "always largest models", that is a one-line config change. It will OOM or swap on small Macs, which is why it isn't the recommendation.

### 2.5 Selection, visibility and audit

1. `DeviceProfile` is selected, then a `ModelRouter(environment=AEROMIND_ENV or "local", hardware_tier=profile.tier)` is built. It loads `local.<tier>` and filters entries by memory constraints.
2. The audit event `HARDWARE_PROFILE_SELECTED` records `details={tier, source, accelerator, gpu_count, vram_gb, unified_mem_gb, ram_gb, reasons, registry_hash, agents_enabled}` (no hostnames or serials).
3. `GET /api/health` gains:
   ```json
   "hardware": {"tier":"cpu_lite","source":"probe","accelerator":"none","vram_gb":0,"ram_gb":31.0,
                "reasons":["no nvidia-smi","no rocm-smi","Intel Iris Xe: compute_usable=false"]},
   "agents": {"enabled":["main","execution","retrieval","data_analysis","multimodal","critic","memory"],
              "unavailable":{"coding":"disabled on cpu_lite","correlation":"V1 + needs graph"}},
   "models": {"available":[...], "unavailable":[{"name":"qwen3-8b","reason":"not in ollama /api/tags"}]}
   ```
4. The UI shows a `TopBar` badge next to the status badge: **"Lite mode · CPU"**, "GPU mode · 24 GB", "Multi-GPU", or "Full quality · Apple M3 Max 64 GB". The tooltip shows `reasons` and the unavailable agents. When a plan needs a disabled agent, the activity view shows "Not available on this device: Coding agent", and the Main Agent answers with what it *can* do. It never silently skips (PLAN §8.9 `pending_capabilities`).
5. Override: `AEROMIND_HW_TIER=gpu_high` is honoured even when the probe disagrees. The event has `source=override`, and the health status shows `warning: tier overridden`.

### 2.6 Invariants and tests (`tests/unit/router/test_hardware_probe.py`)

Fixtures are mocked command outputs; there are no real subprocess calls.

| Test | Mocked inputs | Expected |
|---|---|---|
| `test_i7_no_gpu_is_cpu_lite` | Linux x86_64; `nvidia-smi` FileNotFoundError; `rocm-smi` missing; lspci "Iris Xe"; MemTotal 32,5xx,xxx kB | `cpu_lite`, accelerator `none`, reasons contain "Iris Xe" |
| `test_rtx4090_is_gpu_high` | `nvidia-smi` → `NVIDIA GeForce RTX 4090, 24564` | `gpu_high`, vram_gb≈24.0 |
| `test_rtx3060_12gb_is_gpu_standard` | `NVIDIA GeForce RTX 3060, 12288` | `gpu_standard` |
| `test_two_a100_is_gpu_multi` | two lines `A100-SXM4-80GB, 81920` | `gpu_multi`, gpu_count 2 |
| `test_m3_max_64_is_apple_full_large` | Darwin arm64; hw.memsize 68719476736; "Apple M3 Max" | `apple_full`, planner escalation = qwen3-32b |
| `test_m1_8gb_is_apple_full_with_warning` | Darwin arm64; 8 GB | `apple_full`, only ≤8B entries, warning present |
| `test_override_wins_and_is_audited` | env `AEROMIND_HW_TIER=gpu_high` on the i7 mocks | `gpu_high`, `source=override`, audit event emitted |
| `test_invalid_override_fails_loud` | `AEROMIND_HW_TIER=turbo` | `ValueError` listing valid tiers |
| `test_probe_timeout_degrades_to_unknown` | `nvidia-smi` hangs (TimeoutExpired) | continues; reason "nvidia-smi timeout" |
| `test_safety_keys_not_tier_overridable` | agents.yaml tier block containing `audit: false` | loader raises |
| `test_no_tier_branches_in_agent_code` | static: grep `backend/agents/**/*.py` for `tier ==` / `hardware_tier` | zero matches (PLAN §5.3 code parity) |
| `test_embedding_identical_all_tiers` | load real `config/models.yaml` | one `(model_ref, dim)` |

---

## 3. Task decomposition (planner node)

### 3.1 Pipeline

`classify_intent` (deterministic) produces `task_type`, then `planner`:

1. **Complexity check** (deterministic, PLAN §8.1.3). A task is complex if any of these hold:
   - `attachments ≥ 2`
   - mixed modalities
   - trigger words: *and, compare, correlate, verify, then, report, spreadsheet, multiple, RCA, draft, match*
   - length > 400 chars
2. **Template match.** `config/plan_templates.yaml` holds named DAG templates keyed by `(task_type, modality set, trigger)`, e.g. `rca_report`, `doc_qa`, `table_question`, `compare_docs`, `code_task`. The existing four heuristic DAGs (`backend/orchestrator_planner.py:18-134`) migrate here unchanged, as `aviation_visual_math`, `aviation_visual_only`, `aviation_math_only` and `aviation_logistics`. They are preserved as the aviation starter kit.
3. **LLM fallback**, only if there is no template and the task is complex. Call `router.get("planning")` with JSON-schema constrained output (Ollama `format: <json schema>`; vLLM `guided_json`). Max 1 retry on schema failure, then escalate per §5.
4. **Validation** (`planner/validate.py`):
   - acyclic (topological sort)
   - depth ≤ `tiers.<tier>.max_plan_depth`
   - each `assigned_agent` ∈ enabled agents, else that subtask is marked `SKIPPED(reason="not available on this device")` and surfaced
   - each `required_capability` is resolvable in the tier
   - every factual subtask has a downstream `critic` node
   - the plan ends in `synthesize → task_evaluation`
5. **Persist** `TaskPlan` into state (`plan`), audit `PLAN`, stream a `plan` SSE event.

### 3.2 SubTask (PLAN §7.9 + ADR-0005 proposed fields)

```python
class SubTaskBudget(BaseModel):
    max_tokens_out: int = 800
    max_wall_s: float = 120
    retry_budget: int = 1                 # overrides agent default downward only

class SubTask(BaseModel):                 # PLAN §7.9 fields first
    subtask_id: str
    title: str
    description: str
    assigned_agent: str
    depends_on: list[str] = []
    status: Literal["PENDING","RUNNING","DONE","FAILED","SKIPPED"] = "PENDING"
    result: dict | None = None
    # ADR-0005 additions:
    required_capability: CapabilityTag
    input_schema: str                     # dotted path to Pydantic model, e.g. "schemas.io.ExtractEntitiesIn"
    output_schema: str                    # validated after every attempt
    budget: SubTaskBudget = SubTaskBudget()
    max_tier: Literal["small","medium","large"] = "medium"    # cascade ceiling
    critic_mode: Literal["deterministic","deterministic+llm","none"] = "deterministic+llm"
    deterministic_tool: str | None = None # when set, run the tool; model only on tool failure/ambiguity
    priority: Literal["interactive","background"] = "interactive"
```

### 3.3 Example plan (RCA task; shortened; full trace in §10)

```json
{
  "plan_id": "plan_7f3c", "original_task": "Analyse these 3 inspection PDFs + maintenance CSV + audio note and draft an RCA report",
  "is_complex": true, "template": "rca_report", "status": "PLAN_GENERATED",
  "subtasks": [
    {"subtask_id":"s1a","assigned_agent":"multimodal","required_capability":"ocr_assist","deterministic_tool":"pdf_extract","depends_on":[],"max_tier":"small","output_schema":"schemas.io.DocumentOut"},
    {"subtask_id":"s1d","assigned_agent":"data_analysis","required_capability":"code_gen","deterministic_tool":"csv_extract","depends_on":[],"output_schema":"schemas.io.DocumentOut"},
    {"subtask_id":"s1e","assigned_agent":"multimodal","required_capability":"asr","deterministic_tool":"asr_transcribe","depends_on":[],"output_schema":"schemas.io.DocumentOut"},
    {"subtask_id":"s2","assigned_agent":"multimodal","required_capability":"extraction","depends_on":["s1a","s1b","s1c","s1d","s1e"],"max_tier":"medium","output_schema":"schemas.io.EntitiesOut"},
    {"subtask_id":"s7","assigned_agent":"execution","required_capability":"drafting","depends_on":["s5","s6c"],"max_tier":"large","critic_mode":"deterministic+llm","output_schema":"schemas.io.DraftOut"}
  ]
}
```

---

## 4. Capability-based routing

### 4.1 Algorithm (`router/router.py`)

```python
def candidates(self, capability: str, *, max_tier="large", need_tools=False,
               need_vision_input=False) -> list[Entry]:
    pool = [e for e in self.entries                     # entries of the selected (env, tier)
            if capability in e.capabilities             # 1. capability match (the ONLY semantic filter)
            and e.status != "unavailable"               #    V10: not installed → never served
            and TIER_ORDER[e.tier] <= TIER_ORDER[max_tier]
            and (not need_tools or e.tool_calling != "none")]
    if not pool:
        raise NoModelForCapability(capability, self.tier, reason=self._explain_empty(capability))
    pool = [e for e in pool if self.breaker.allow(e.name)]        # 2. health / circuit breaker
    pool = [e for e in pool if self.budget.fits(e)]               # 3. VRAM/RAM fit (GpuBudget, §6.2): soft
    # 4. deterministic ordering: rank asc (smallest first = cascade order), default first among equal rank
    pool.sort(key=lambda e: (e.rank, not e.default, e.name))
    # 5. (ONLY after ADR-0005 accepted AND every candidate has measured data) tiebreak equal-rank
    #    entries by quality[capability].score desc, then latency_profile.ttft_ms_p50 asc.
    return pool

def get(self, capability, **kw) -> RoutedClient:
    pool = self.candidates(capability, **kw)
    if not pool: raise AllCandidatesUnhealthy(capability)   # → degradation matrix §9.3
    entry = pool[0]
    return RoutedClient(entry, self._client_cache[entry.name], audit_ctx=...)   # client cached per entry
```

When step 3 removes everything, the router returns the smallest entry and lets the scheduler *queue* it (wait for VRAM). It never picks a different capability.

### 4.2 Every call is audited

Each call emits `MODEL_CALL`:
- `model_capability` (requested tag) and `model_name` + `model_version` (served)
- `tier`
- `tokens_in/out`, `ttft_ms`, `latency_ms`, `queue_wait_ms`
- `attempt`, `escalated_from`

This closes the plan requirement "tag requested vs served model" (PLAN §8.2).

### 4.3 Why routing stays dumb (PLAN §8.2)

Quality and latency only enter routing when **both** conditions hold:
- (a) ADR-0005 is accepted.
- (b) Every candidate in that (tier, capability) has a `quality` score with an `eval_run_id` from the harness (or a `latency_profile` with a `bench_run_id` from B1 re-run on *this* hardware).

The reason: an unmeasured dimension silently re-orders models on guesses, and it can't be tested. Rank order is reproducible, explainable in the audit log, and covered by a unit test per tier.

Today's evidence that guesses are wrong:
- The "vision" model in `.env` (`gemma4:e4b`) is never sent images, because synthesis uses `qwen2.5:3b` (`backend/model_service.py:357`).
- The stale B4 benchmark scored a *copy* of the router (`bench/b4_router_accuracy.py:44-78`).

---

## 5. Cascade and escalation

### 5.1 Triggers

The router always tries the smallest capable entry first. Escalation to the next entry with a **higher tier on the same capability** (staying within `SubTask.max_tier`) happens only on:

| Trigger | Detected by | Example |
|---|---|---|
| `SCHEMA_INVALID` | Pydantic validation of output against `output_schema`, after one same-model repair attempt | extraction JSON missing `entities` |
| `CRITIC_FAIL` | Critic verdict `FAIL` / `NEEDS_REVISION` with `suggested_action` not `RETRY_RETRIEVAL` (evidence problems → retrieval, not a bigger model) | draft claims a date not in evidence |
| `LOW_CONFIDENCE` | `AgentMessage.confidence < thresholds.escalation.min_confidence[capability]` | VLM reading of a gauge at 0.42 |
| `MODEL_FAILURE` | timeout, 5xx, OOM, empty output | `qwen3-vl-2b` OOM on a 4k image |

Not triggers:
- user impatience
- "longer answer wanted"
- retrieval returning insufficient evidence (that goes to the Retrieval Agent's reformulation path, PLAN §8.5)

### 5.2 `config/thresholds.yaml` keys (additions to PLAN §15)

```yaml
escalation:
  max_hops: 1                  # tier value from agents.yaml overrides (gpu_multi: 2)
  same_model_repair_attempts: 1  # schema repair prompt before escalating
  min_confidence:
    extraction: 0.70
    vision: 0.60
    ocr_assist: 0.60
    classification: 0.75
    drafting: null             # drafting uses Critic only
  max_total_attempts_per_subtask: 3
  timeout_s: { small: 90, medium: 180, large: 300 }   # cpu_lite multiplies by 2 (config, not code)
critic:
  correction_passes: 1         # PLAN §15
```

### 5.3 Pseudocode (`orchestration/cascade.py`)

```python
async def run_with_cascade(sub: SubTask, agent, state, router) -> AgentMessage:
    pool = router.candidates(sub.required_capability, max_tier=sub.max_tier)
    hops, attempts, last = 0, 0, None
    for entry in pool:                                    # smallest → largest
        for repair in range(1 + TH.same_model_repair_attempts):
            attempts += 1
            if attempts > TH.max_total_attempts_per_subtask: break
            check_cancel(state)                           # cooperative cancel between attempts
            msg = await agent.run(sub, state, model=entry, repair_notes=last and last.feedback)
            if msg.degraded:                              # fallback/template output
                last = msg; break                         # never accepted, never PASS (pitfall §11.5)
            if not schema_ok(msg, sub.output_schema):
                last = msg.with_feedback("schema"); continue
            verdict = await critic.check_subtask(sub, msg, state)       # §7.3
            if verdict.verdict == "PASS" and confidence_ok(msg, sub):
                return msg.with_eval(verdict)
            if verdict.suggested_action == "RETRY_RETRIEVAL":
                return msg.with_eval(verdict)             # Main Agent re-plans retrieval; not a model problem
            last = msg.with_eval(verdict); break          # escalate rather than same-model retry on Critic fail
        if hops >= tier_cfg.escalation_max_hops: break
        nxt = next_larger(pool, entry)
        if not nxt: break
        audit("MODEL_ESCALATION", capability=sub.required_capability, from_model=entry.name,
              to_model=nxt.name, trigger=last.trigger, subtask_id=sub.subtask_id, attempt=attempts)
        stream("agent_activity", phase="escalating", ...)
        hops += 1
    # budget exhausted: honest failure, Main Agent decides (retry differently / human review)
    return AgentMessage.failed(sub, last, needs_human_review=True, reason=explain(last))
```

Rules:
- `degraded=True` is set by any code path that used a template or fallback, or by a model other than the routed one. The Critic deterministic layer **hard-FAILs** any message with `degraded=True`.
- Escalation never changes the capability, and never crosses into the `hf` environment.
- Every hop is an audit event (`MODEL_ESCALATION`, new event type proposed in ADR-0005). The UI timeline shows it.

---

## 6. Parallel execution and scheduling

### 6.1 DAG executor (`orchestration/dag_executor.py`, inside the LangGraph `dispatch` node)

```python
async def execute_plan(plan: TaskPlan, state, ctx) -> dict[str, AgentMessage]:
    done: dict[str, AgentMessage] = {}
    pending = {s.subtask_id: s for s in plan.subtasks}
    running: dict[str, asyncio.Task] = {}
    while pending or running:
        ready = [s for s in pending.values()
                 if all(d in done and done[d].ok for d in s.depends_on)]
        blocked = [s for s in pending.values()
                   if any(d in done and not done[d].ok for d in s.depends_on)]
        for s in blocked:                                  # never silently drop (PLAN §8.1)
            done[s.subtask_id] = AgentMessage.skipped(s, reason="upstream failed"); pending.pop(s.subtask_id)
        for s in ready:
            pending.pop(s.subtask_id)
            ctx.permissions.authorize_agent_invocation(ctx.user, s.assigned_agent, state["workspace_id"])
            running[s.subtask_id] = asyncio.create_task(ctx.scheduler.submit(s, state))
        if not running: break
        fin, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
        for t in fin:
            sid = next(k for k, v in running.items() if v is t); running.pop(sid)
            done[sid] = t.result(); stream_subtask_done(done[sid])
        if state_cancel_requested(state):
            for t in running.values(): t.cancel()
            raise TaskCancelled
    return done
```

- Deterministic tool subtasks (`pdf_extract`, `csv_extract`, `asr_transcribe`, `ocr_extract`) bypass the GPU budget. They use a CPU `ThreadPoolExecutor(max_workers=thresholds.queue.max_workers)`.
- LLM subtasks go through the `Scheduler`.

### 6.2 GpuBudget: VRAM-weighted admission (`router/scheduler.py`)

```python
class GpuBudget:
    def __init__(self, profile: DeviceProfile, cfg):
        self.capacity = (profile.vram_gb * cfg.vram_fraction_usable) if profile.vram_gb else \
                        (profile.unified_mem_gb or profile.ram_gb) - cfg.ram_reserve_gb
        self.resident: dict[str, float] = {}    # model name → GB currently loaded (from ollama /api/ps, refreshed 5 s)
        self.cond = asyncio.Condition()
        self.slots = asyncio.Semaphore(tier_cfg.max_parallel_llm)   # cpu_lite: 1
    def cost(self, e: Entry) -> float:
        return 0.0 if e.name in self.resident else (e.vram_gb or e.ram_gb)
    def fits(self, e: Entry) -> bool:
        return sum(self.resident.values()) + self.cost(e) <= self.capacity
    async def acquire(self, e: Entry, priority: int):
        async with self.slots:                  # concurrency cap
            async with self.cond:
                await self.cond.wait_for(lambda: self.fits(e) or self._evict_cold(e))
                self.resident[e.name] = e.vram_gb or e.ram_gb
```

- `_evict_cold` asks Ollama to unload `cold` models (`POST /api/generate {"model":..., "keep_alive":0}`), least recently used first. It never evicts `pinned` models.
- **Priority queue.** `interactive` subtasks (chat turn, the user waiting) jump ahead of `background` work (ingestion embedding, scheduled tasks, Optimization). It is implemented as an `asyncio.PriorityQueue` in front of `acquire`, with aging (+1 priority per 30 s waited) so background work can't starve.

### 6.3 Hot/cold sets (Ollama `keep_alive`)

| Tier | `pinned` (keep_alive -1) | `warm` (keep_alive 10m) | `cold` (keep_alive 0 after use) | Ollama env |
|---|---|---|---|---|
| cpu_lite | qwen3-4b-instruct, nomic-embed/bge-m3 | qwen2.5-3b (critic) | qwen2.5-coder-1.5b, qwen3-vl-2b, gemma4-e4b | `OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=5m`, `num_thread=cpu_cores` |
| gpu_standard | qwen3-8b, bge-m3, reranker | qwen3-4b | coder-7b, vl-4b, gemma3-12b | `MAX_LOADED=3`, `NUM_PARALLEL=2` |
| gpu_high | qwen3-8b, bge-m3, reranker | gemma3-12b, qwen3-vl-8b | coder-7b, qwen3-14b, colqwen2 | `MAX_LOADED=4`, `NUM_PARALLEL=2` |
| gpu_multi | all (one vLLM server per GPU group; `--gpu-memory-utilization 0.90`, `--max-model-len 32768`) | — | — | vLLM `--enable-prefix-caching`; multi-LoRA for kit-specific adapters (ADR) |
| apple_full | qwen3-8b, bge-m3 | critic, vl-8b | 14B/32B escalation, coder | `MAX_LOADED=3`, `NUM_PARALLEL=2` (1 if <24 GB) |

The Ollama env values are written into the deploy files `deploy/ollama.<tier>.env`, which the `hardware_probe` prints as a recommendation. The app never mutates a running Ollama's env.

### 6.4 Batching

- **Embeddings:** batch 32 texts per request at ingestion (`thresholds.embedding.batch=32`); single requests are allowed for interactive queries. A cache keyed on `sha256(model_version + text)` lives in SQLite (`.storage/embed_cache.db`).
- **Reranker:** one batched call per query over top-K (K=24 → keep 8).
- **Entity extraction:** per document, in chunks of ≤ `max_context × 0.6` tokens.
- **vLLM:** continuous batching is native; the app sends concurrent requests up to `max_parallel_llm`.

### 6.5 Cooperative cancel

- `POST /api/tasks/{id}/cancel` sets `cancel_requested` in the persisted state.
- The executor checks it between subtasks; the cascade checks it between attempts.
- Running HTTP streams are closed with `client.aclose()`, the GPU slot is released, and the status becomes `CANCELLED` with an audit `CANCELLED` event.

---

## 7. Inter-agent contract, merge, and the Critic

### 7.1 AgentMessage (PLAN §7.4 verbatim + ADR-0005 additions)

```python
class AgentMessage(TypedDict):
    from_agent: str; to_agent: str; task_id: str
    payload: dict                       # validated against SubTask.output_schema
    evidence_refs: list[EvidenceRef]    # REQUIRED if payload has any factual claim
    inference: bool
    confidence: float                   # agent-computed, see 7.2
    requires_human_approval: bool
    agent_version: str
    # ADR-0005 additions
    subtask_id: str
    model_name: str | None; model_version: str | None; capability: str | None
    attempt: int; escalated_from: str | None
    degraded: bool                      # template/fallback/any non-routed model → True
    claims: list[Claim]                 # [{claim_id, text, evidence_ref_ids[], tag}]
```

### 7.2 Confidence must be grounded, not self-reported

| Agent | Confidence source |
|---|---|
| Multimodal OCR | mean OCR line confidence (RapidOCR returns scores) |
| Multimodal VLM | min over claims of (VLM logprob if available, else 0.5) × bbox present |
| Extraction | fraction of entities whose span string occurs verbatim in source text |
| Data Analysis | 1.0 if sandbox `exit_code==0` and result is reproducible on re-run, else 0 |
| Retrieval | top rerank score, calibrated (`retrieval.min_relevance` = 0.3) |
| Drafting | not self-scored; Critic verdict only |

A model's own "I am 95% sure" is **never** used.

### 7.3 Merge rules (`orchestration/merge.py`, in the `synthesize` node before drafting)

1. **Collect** all `done` messages with `ok=True`. Failed or skipped ones go into `state.review_reason`, plus a "what I couldn't do" section.
2. **Normalize claims** into `(subject_entity_id, predicate, value, unit, time, evidence_ref_ids)` using the entity resolver (P-104 ≡ "Pump 104"). Unresolvable subjects stay as raw strings with `AMBIGUOUS`.
3. **Deduplicate** identical tuples by union of `evidence_ref_ids`, keeping max confidence.
4. **Conflict detection:** the same `(subject, predicate, time-window)` with incompatible values. For numbers, |a−b|/max > `merge.numeric_tolerance` (0.02), with unit-normalised comparison. For enums, not equal.
   - Both claims are kept, and a `CONTRADICTS` edge is added between their evidence units (graph store, PLAN §7.10).
   - A `ContradictionClaim` goes to the drafter, which must present both, cited.
   - The Critic checks that contradictions were surfaced, not resolved by fiat.
5. **Evidence phrasing** is rendered from tags, not prompts (PLAN §8.10): observed → "The inspection report states…", retrieved → "According to …", inferred → "Based on the available evidence…", uncertain → an explicit caveat.

### 7.4 Critic (PLAN §8.10): two layers, at two points

**Per subtask** (inside the cascade, §5.3) and **on the final synthesis** (`task_evaluation` node).

*Layer 1: deterministic (`agents/critic/rules.py`, always on, every tier).* Each rule is a hard FAIL:
- every claim has ≥1 `evidence_ref` that resolves *by id* in the same `workspace_id` (pitfall §11.13: lookup by id, not by search)
- tag strength: `observed` requires a source unit of modality `pdf/csv/audio/image` with matching location
- the claim text's numbers appear in the cited unit (or in a sandbox result that cites it)
- `degraded=True`
- empty payload
- a failed tool call (`succeeded=False`, real exit code, pitfall §11.7)
- injection markers present in output (cross-check with the injection guard)
- dates and quantities parse

*Layer 2: LLM pass (`evaluation` capability).*
- Input: each claim, the cited evidence text (inside `<untrusted_document_evidence>` per PLAN §8.7), and the instruction "classify SUPPORTED / UNSUPPORTED / CONTRADICTED".
- Output: JSON schema.
- PASS only if *every* claim is SUPPORTED; any hedge is a fail.
- **Cross-family rule:** the critic entry's `family` ≠ producer's `family` where the tier has one: gemma vs qwen on gpu_* and apple, Mistral-Small or Gemma on gpu_multi.
  - On cpu_lite the only installed cross-family critic is `gemma4:e4b` (5 tok/s).
  - So the default critic there is qwen2.5:3b (a different generation), with escalation to gemma4 on `CRITIC_FAIL` borderline cases or final synthesis of deliverables.
  - This relaxation is recorded in every `EVALUATION` audit event (`cross_family=false`).

*Task-level evaluation (final).*
- Does the synthesis faithfully represent each sub-result?
- Every sub-result claim used must map to a sentence; no new claims without refs; contradictions surfaced; omitted subtasks disclosed.
- Correction policy: one correction pass by the producer (`critic.correction_passes: 1`), then `WAITING_FOR_USER` + `needs_human_review`.

**The scorecard UI** (`frontend/src/components/EvaluationScorecard.jsx`) is fed from `EvaluationReport`:
- claim counts by status
- verdict
- `cross_family`

The invented defaults (`EvaluationScorecard.jsx:17-18`) and the floored heuristic (`backend/evaluation_service.py:50`) are replaced. The old `evaluation_service` is kept as `heuristic_overlap` and shown as a secondary "keyword overlap" metric, clearly labelled.

---

## 8. Agent ↔ SLM mapping

Every model name is a **candidate**: confirm it with the eval harness (Phase 2.2), the tool-calling parity test (Phase 2.3) and the licence allowlist (V8).

**Assumptions:**
- `cpu_lite` models are verified installed on the dev laptop (this session, `ollama list`).
- All GPU and Apple columns are **unverified on this machine** (no CUDA, no Mac). The 24 GB figure is the user's stated MVP target, not measured hardware.
- VRAM numbers are approximate Q4 weights plus ~1 GB KV cache at 8k context.

| Agent (capability) | cpu_lite (i7, CPU, installed) | gpu_standard (8–16 GB) | gpu_high (24 GB MVP) | gpu_multi (production) | apple_full (≥48 GB / 24–47 / ≤23) |
|---|---|---|---|---|---|
| Main: planning, routing judgment | qwen3:4b-instruct-2507 (~3.5 GB RAM) | Qwen3-8B Q4 (~6 GB) | Qwen3-8B Q4 → esc. Qwen3-14B (~10.5) | Qwen3-8B bf16 → esc. Qwen3-32B AWQ (~20) | 8B → 32B / 8B → 14B / 4B → 8B |
| Execution: drafting, summarization | same as Main (shared weights) | Qwen3-8B | Qwen3-8B → Qwen3-14B | Qwen3-32B AWQ | as Main |
| Coding: code_gen/debugging | qwen2.5-coder:1.5b (~1.2) *agent disabled by default* | Qwen2.5-Coder-7B (~5) | Qwen2.5-Coder-7B (~5) | Qwen3-Coder-30B-A3B AWQ (~18) | Coder-14B / 14B / 1.5B |
| Retrieval: embedding / rerank / query reformulation | nomic-embed-text → **bge-m3 (lock)** / bge-reranker-v2-m3 on CPU / qwen3-4b | bge-m3 (~1.2) + reranker (~1.1) + Qwen3-4B | same + optional ColQwen2 (~4.5) | same (dedicated embedding GPU slice) | same (mps) |
| Data Analysis: code_gen + tools | deterministic (pandas, `AvionicsMathEngine`) → coder-1.5b | Coder-7B + sandbox | Coder-7B + sandbox | Coder-30B-A3B | Coder-14B |
| Multimodal: vision / ocr_assist / asr | RapidOCR → qwen3-vl:2b (~2.4, lazy) / faster-whisper-small int8 | Qwen3-VL-4B (~4) / fw-large-v3-turbo (~1.6) | Qwen3-VL-8B (~6.5) / fw-large-v3-turbo | Qwen2.5-VL-32B AWQ (~20) / fw-large-v3 | VL-8B / VL-8B / VL-2B; whisper on CPU |
| Critic: evaluation (cross-family) | qwen2.5:3b → esc. gemma4:e4b (~10 RAM) | Gemma-3-12B Q4 (~8.5, cold) | Gemma-3-12B Q4 (~8.5) | Gemma-3-27B (~18) or Mistral-Small-24B | Gemma-3-27B / 12B / 4B |
| Correlation: general_reasoning + embedding | *disabled* (deterministic resolver available) | *disabled* | Qwen3-8B + bge-m3 + resolver | Qwen3-32B + resolver | as Main |
| Memory | deterministic (SQLite) | deterministic | deterministic | deterministic (Postgres) | deterministic |
| Optimization: general_reasoning (offline) | *disabled* | *disabled* | Qwen3-14B nightly batch | Qwen3-32B weekly batch | 32B / 14B / off |
| Classification | keyword rules → qwen2.5:3b | rules → Qwen3-4B | rules → Qwen3-4B | rules → Qwen3-8B | rules → 4B |
| Translation (V1, Indic) | — | IndicTrans2 (ADR; ~1–2 GB) | IndicTrans2 | IndicTrans2 / Qwen3-32B | IndicTrans2 |

**24 GB VRAM budget (gpu_high)** with `vram_fraction_usable=0.90`, which gives 21.6 GB:

| Resident set | GB |
|---|---|
| Pinned: Qwen3-8B (6.0) + bge-m3 (1.2) + reranker (1.1) | 8.3 |
| Typical concurrent cold: Qwen3-VL-8B (6.5) + Gemma-3-12B critic (8.5) | +15.0 → 23.3 ✗ over budget |
| So the scheduler serialises: VL **or** critic resident with the pinned set | 8.3 + 8.5 = 16.8 ✓ (4.8 headroom for KV / Coder-7B 5.0 ✓ just fits) |
| Escalation Qwen3-14B (10.5) evicts cold models: 8.3 + 10.5 | 18.8 ✓ |
| ColQwen2 (4.5) runs only in background ingestion, evicted before interactive work | — |

On cpu_lite, RAM is the budget: 31 GiB − 6 GB reserve = 25 GB. Pinned 4B (3.5) + embed (0.4 → 1.2 for bge-m3) + warm critic 3B (2.3) is about 7 GB. gemma4 escalation (10.3) fits but is slow (~5 tok/s measured), which is why it is used only for final-deliverable critique.

---

## 9. Failover and health

### 9.1 Probes (`router/health.py`)

- **Ollama:**
  - `GET /api/tags` lists installed models (marks V10 `unavailable`).
  - `GET /api/ps` shows resident models and VRAM.
  - Per-model liveness is a 1-token `POST /api/generate {"num_predict":1}` at startup warm-up, only for `pinned` models.
- **vLLM:** `GET /health`, then `GET /v1/models`.
- **Non-HTTP providers** (faster_whisper, cross_encoder, transformers): an in-process load check, run lazily on first use.
- **Timing:** `router.health_timeout_s: 2.0` (PLAN §15). Background re-check every 30 s; on-demand re-check before routing to an entry whose breaker is half-open.

### 9.2 Circuit breaker (per entry)

```yaml
router:
  circuit_breaker:
    failure_threshold: 3          # consecutive failures (timeout, 5xx, OOM, connection refused)
    cooldown_s: 60                # OPEN → HALF_OPEN after cooldown
    half_open_probes: 1           # one trial request; success → CLOSED, failure → OPEN (cooldown ×2, max 600)
```

State changes are audited as `MODEL_FAILOVER` / `CIRCUIT_OPEN` / `CIRCUIT_CLOSED`. Failover goes to the next `rank` on the **same capability**, wired into `router.get()` (pitfall §11.6, PLAN §8.2 V1).

### 9.3 Graceful degradation matrix

| Failure | Behaviour | User sees |
|---|---|---|
| Default chat model down, next rank available | failover, `MODEL_FAILOVER` | activity: "Switched to qwen2.5-3b (primary unavailable)" |
| All `planning` entries down | deterministic template planner only; LLM fallback disabled | "Using built-in plan templates" |
| All `drafting` entries down | **no draft**; return the structured findings table with citations | "Drafting model unavailable: here are the verified findings" (status FAILED → human review) |
| `evaluation` down | deterministic Critic layer only; **deliverables blocked** (no artifact writes without the LLM pass) | "Verification incomplete: draft not exported" |
| `vision` down | OCR text only, `pending_capabilities=[vision]` | "Images not analysed on this device right now" |
| `asr` down | audio unit `FAILED` with reason; the rest continues | "Audio note could not be transcribed" |
| `embedding` down | keyword/metadata retrieval only (BM25 over stored text) with a note; ingestion queued, not lost | "Search running in keyword-only mode" |
| Qdrant down / embedded lock held | **fail loud**. Today's silent `:memory:` fallback (`backend/colpali_retrieval_service.py:75-77`) is removed: it loses the index | "Knowledge base unavailable" |
| Ollama unreachable | health `down`; chat returns an honest error event, never `[Generation error]` as tokens (`backend/model_service.py:419-425`) | error banner with retry |
| GPU OOM | entry breaker counts a failure; scheduler evicts cold models, then retries once; then escalates or fails | "Retrying with lower memory use" |

---

## 10. Worked example, end to end

**Task:** *"Analyse these 3 inspection PDFs + this maintenance CSV + this audio note and draft an RCA report."*

**Inputs:**
- `insp_A.pdf`: text-native, 12 p, mentions "Pump 104 mechanical seal weeping".
- `insp_B.pdf`: a **scanned** 6 p with photos.
- `insp_C.pdf`: text-native, 8 p, a different unit (the negative-control candidate, "P-401").
- `maint.csv`: 2,400 rows: `date, tag, work_order, action, part, downtime_h`.
- `note.m4a`: 3 min shift-supervisor voice note.

### 10.1 DAG (template `rca_report`, validated depth 6)

```
L0  s1a pdf_extract(A)  s1b pdf_extract+OCR(B)  s1c pdf_extract(C)  s1d csv_extract(maint)  s1e asr(note)   [deterministic tools]
L1  s2a extract_entities(A)  s2b (B)  s2c (C)  s2d (CSV tags)  s2e (transcript)                             [extraction]
    s3  vlm_describe(B photos, low-conf OCR regions)                                                         [vision]
L2  s4  entity_resolution(all entities) → canonical equipment                                                [deterministic + embedding]
L3  s5  data_analysis: failure timeline, MTBF, repeat WOs for resolved tags (sandbox pandas)                 [code_gen]
    s6a correlation: inspection findings ↔ WOs ↔ voice note (temporal + numeric + semantic)                  [general_reasoning]
L4  s6c critic(subtasks s3,s5,s6a)                                                                           [evaluation]
L5  s7  draft RCA (5-Whys + fishbone sections, kit template kits/manufacturing/templates/rca.md)             [drafting]
L6  s8  critic(final) + task_evaluation → approval_gate → write_docx v1 → continuation
```

Critic checkpoints:
- deterministic layer after every L1–L3 subtask
- LLM pass at s6c (batched over factual subtasks) and s8 (final)

### 10.2 Assignment and rationale

| Subtask | gpu_high model | cpu_lite model | Why |
|---|---|---|---|
| s1a/s1c | PyMuPDF text (tool) | same | text-native; deterministic beats an LLM (PLAN §2.3) |
| s1b | RapidOCR (tool) → `ocr_assist` Qwen3-VL-8B for lines with conf < 0.6 | RapidOCR → qwen3-vl:2b *only* for conf < 0.6 lines (≤10 crops) | OCR first; VLM only where OCR is weak |
| s1d | CSV extractor, 20-row units (tool) | same | structure-preserving EvidenceUnits, no 15-row truncation (`backend/ingestion_adapter.py:180`) |
| s1e | faster-whisper large-v3-turbo | faster-whisper small int8 (CPU) | ASR is a tool |
| s2a–e | Qwen3-4B (`extraction`, small, JSON schema) → esc. Qwen3-8B on SCHEMA_INVALID | qwen3:4b-instruct (sequential) → esc. none (max_tier small on cpu_lite) → regex tag extractor as floor | cheap, parallel, schema-checked |
| s3 | Qwen3-VL-8B (photos of seal, gauge) | qwen3-vl:2b, lazy; capped at 6 images; others `pending_capabilities` | per-claim confidence + bbox |
| s4 | resolver: normalize "Pump 104"/"P-104"/"pump no. 104" → exact/normalized 0.90 → bge-m3 sim; RESOLVED only ≥0.85 with margin >0.15 | same (CPU bge-m3) | precision over recall (PLAN §8.4); "P-401" stays distinct |
| s5 | Qwen2.5-Coder-7B writes pandas → sandbox | **deterministic pandas recipe** from kit (no codegen): groupby tag, timeline, repeat-WO count; coder-1.5b only if the recipe can't answer | correct numbers must come from execution, not generation |
| s6a | Qwen3-8B + graph | **disabled agent**: Main Agent does flat temporal join (deterministic) and says "Correlation agent not available on this device: matched by date and tag only" | honest degradation |
| s6c | Gemma-3-12B (cross-family) | qwen2.5:3b | independent verifier |
| s7 | Qwen3-8B → esc. Qwen3-14B on CRITIC_FAIL | qwen3:4b-instruct → esc. none; on fail → human review | smallest first |
| s8 | Gemma-3-12B | qwen2.5:3b → esc. gemma4:e4b (final deliverable deserves the cross-family check even if slow) | deliverable gate |

### 10.3 Swimlane (gpu_high, illustrative timing; **not measured**)

```
time(s)  0    5    10   15   20   25   30   35   40   45   50   55   60   70   80   90
CPU-pool [s1a][s1c][s1d────][s1b OCR──────────][s1e ASR(GPU 1.6)]
GPU      [pinned: qwen3-8b 6.0 + bge-m3 1.2 + rerank 1.1 = 8.3 GB ───────────────────────────────────]
              [embed batches ingestion ──────────]
                         [qwen3-4b s2a|s2c|s2d (3.2)]  [s2b|s2e]
                         [qwen3-vl-8b s3 (6.5) ──────]
                                               [s4 resolver CPU+embed]
                                                     [coder-7b s5 (5.0)]┐
                                                     [qwen3-8b s6a ────]┘
                                                                    [gemma3-12b s6c (8.5)]
                                                                                [qwen3-8b s7 draft ─────]
                                                                                             [gemma3 s8][approval]
VRAM(GB) 8.3  9.9  9.9  18.0 18.0 18.0 16.8 16.8 13.3 13.3 16.8 16.8 8.3  16.8 8.3  16.8
```

On cpu_lite the same DAG runs with `max_parallel_llm=1`. LLM subtasks serialise (L1 extraction runs 5 calls back-to-back) while deterministic tools still run in parallel on the CPU pool. Expect minutes, not seconds; the UI says so up front ("Lite mode: this task will take several minutes").

### 10.4 Escalation and approval points

- **s2b:** the scanned report's extraction returns invalid JSON → one repair, then escalation to Qwen3-8B (`MODEL_ESCALATION trigger=SCHEMA_INVALID`).
- **s7:** the Critic marks the claim "seal failure began 14 Aug" UNSUPPORTED (the PDF says 16 Aug) → `CRITIC_FAIL` → one correction pass on Qwen3-8B with Critic notes. If that still fails → Qwen3-14B. If still failing → human review.
- **Approval gate:** `write_docx` is a write tool triggered by a document-derived task (PLAN §8.13). It needs `APPROVAL_REQUIRED`, LangGraph `interrupt`, and the UI approval card. On approve → `rca_P-104_v1.docx` with:
  - a citations appendix: `insp_A.pdf#page=4`, `maint.csv#rows=1201-1220`, `note.m4a#t=42.0-55.5`
  - a provenance record (task_id, agent chain, models + versions)
- **Continuation:** the threshold check passes, so the Main Agent proposes: "maint.csv shows the same seal replacement on P-102 and P-107 within 90 days: analyse them as a common-cause pattern?" If nothing clears `continuation.relevance_threshold`, it stays silent.

### 10.5 SSE stream the user sees (`/api/tasks/{id}/stream`, typed events, §11.3)

```
event: hardware        data: {"tier":"gpu_high","badge":"GPU mode · 24 GB"}
event: plan            data: {"plan_id":"plan_7f3c","template":"rca_report","subtasks":[...15...],"depth":6}
event: agent_activity  data: {"subtask_id":"s1a","agent":"multimodal","phase":"started","tool":"pdf_extract","model":null}
event: ingest_progress data: {"file":"insp_B.pdf","stage":"ocr","done":3,"total":6}
event: agent_activity  data: {"subtask_id":"s2b","phase":"escalating","from_model":"qwen3-4b","to_model":"qwen3-8b","trigger":"SCHEMA_INVALID"}
event: agent_activity  data: {"subtask_id":"s3","agent":"multimodal","phase":"done","model":"qwen3-vl-8b","confidence":0.71,"evidence_refs":4}
event: finding         data: {"claim":"P-104 seal replaced 3× in 60 days","evidence_refs":["maint.csv#rows=1201-1220"],"tag":"observed"}
event: contradiction   data: {"subject":"P-104","predicate":"failure_onset","values":["14 Aug (note.m4a#t=42-55)","16 Aug (insp_A.pdf#page=4)"]}
event: critic          data: {"scope":"subtasks","verdict":"PASS","claims":{"SUPPORTED":11,"UNSUPPORTED":0,"CONTRADICTED":0},"cross_family":true}
event: token           data: {"text":"## 1. Problem statement\n"}            (… streamed draft …)
event: critic          data: {"scope":"final","verdict":"NEEDS_REVISION","claims":{"UNSUPPORTED":1},"action":"correction_pass"}
event: token           data: {"text":"…", "revision":2}
event: critic          data: {"scope":"final","verdict":"PASS"}
event: approval        data: {"action":"write_docx","artifact":"rca_P-104","risk":"write","requires":"ANALYST"}
event: artifact        data: {"artifact_id":"art_91","version":1,"name":"rca_P-104_v1.docx"}
event: continuation    data: {"proposal":"Analyse P-102 and P-107 as a common-cause pattern?"}
event: done            data: {"status":"COMPLETED","latency_ms":...}
```

---

## 11. Observability

### 11.1 Per-SLM metrics (computed from `MODEL_CALL` / `EVALUATION` audit events; local only)

- `model_calls_total{model,capability,tier,outcome}`
- `ttft_ms{model}` p50/p95
- `tokens_per_s{model}`
- `queue_wait_ms{model,priority}`
- `escalation_rate{capability,from_model}`
- `critic_pass_rate{capability,producer_model}`
- `schema_invalid_rate{model}`
- `vram_resident_gb{model}`
- `evictions_total{model}`
- `breaker_state{model}`
- `degraded_outputs_total` (must be 0 PASSes)

These are exported via JSONL now, and an OTel local collector at V1 (ADR-0006). The admin dashboard renders them.

### 11.2 Audit event types used by this design (PLAN §7.8; new types via ADR-0005/0007 marked ✚)

`REQUEST`, `PLAN`, `AGENT_DISPATCH`, `MODEL_CALL`, ✚`MODEL_ESCALATION`, `MODEL_FAILOVER`, ✚`CIRCUIT_OPEN`/✚`CIRCUIT_CLOSED`, ✚`HARDWARE_PROFILE_SELECTED`, `TOOL_CALL`, `EVALUATION`, `APPROVAL_REQUESTED`/`APPROVAL_GRANTED`/`APPROVAL_DENIED`, `CHECKPOINT_SAVED`, `RESPONSE`, `SECURITY_CHECK`/`SECURITY_VIOLATION` (registry V3/V4), `CANCELLED`.

All of them carry `workspace_id, user_id, task_id, agent_name, agent_version, model_capability, model_name, model_version`. Details hold hashes and counts only (`scrub_secrets`).

### 11.3 SSE schema (replaces in-band `[TAG:json]` frames)

Today control frames are mixed into token text (`backend/agent_orchestrator.py:185`, `:404`; parsed in `frontend/src/hooks/useChat.js:106-257`), so model or document text can spoof `[DONE]` or `[ERROR:]`. The new stream uses SSE `event:` names with JSON `data:` only.

```ts
type AgentActivity = {
  task_id: string; subtask_id: string; agent: string; title: string;
  phase: "queued"|"started"|"tool"|"model"|"escalating"|"failover"|"critic"|"done"|"failed"|"skipped";
  capability?: string; model?: string; model_version?: string; tier?: string;
  attempt?: number; from_model?: string; to_model?: string; trigger?: string;
  queue_wait_ms?: number; latency_ms?: number; tokens_out?: number;
  confidence?: number; evidence_refs?: number; reason?: string; ts: string;
};
```

The legacy `/api/chat/stream` keeps emitting the old frames through an adapter, so the current UI works until the new timeline ships.

### 11.4 UI timeline

`AgentActivityHUD.jsx` evolves into a timeline. Swimlanes are per agent; bars are coloured by phase. Each bar is labelled with model + tier badge, and escalations are drawn as arrows. Clicking a bar shows inputs/outputs refs, Critic verdicts, and audit ids (ADMIN: full trail). The header shows the tier badge and current VRAM/RAM use from `/api/ps`.

---

## 12. Migration from today's code (wrap, don't delete)

| Today | Becomes | Kept how |
|---|---|---|
| `Settings.AGENT_MODEL_MAP` (`backend/config.py:25-32`) | input to a one-time generator `scripts/gen_models_yaml.py` that writes `local.cpu_lite` entries | stays in `config.py`. Read only when `config/models.yaml` is absent (with a loud warning), so old `.env` files keep working |
| `ModelService.stream_response(capability=…)` (`backend/model_service.py:235-268`) | thin adapter: `capability` → `router.get(tag)`. The Ollama/GGUF/transformers backends become provider clients in `router/providers/` | keeps the signature and existing callers. The **double generation** (`:380-396`) and **silent 404 fallback** (`:385-390`) are removed in the provider (QW1/QW2) |
| `ModelService._build_prompt` Alpaca (`backend/model_service.py:152-218`) | `prompt_profile: alpaca` renderer inside shared `assemble_prompt` with an untrusted-evidence section | kept for the fine-tuned Mistral entry |
| `OrchestratorPlanner` + `DEFAULT_DAG_TEMPLATES` (`backend/orchestrator_planner.py:18-233`) | templates → `config/plan_templates.yaml` (aviation kit); heuristic keyword sets → `classify_intent` rules | same behaviour for aviation queries, verified by an existing-query regression test |
| `MultiAgentOrchestrator.execute_query_stream` (`backend/agent_orchestrator.py:150-456`) | legacy entry point that builds a `WorkbenchState` and runs the LangGraph graph; an SSE adapter converts typed events to the old `[TAG:]` frames | route `/api/chat/stream` unchanged for the current UI |
| `AvionicsMathEngine` (`backend/agent_orchestrator.py:31-143`) | tool `avionics_math` (ToolSpec, read, no network), **without invented defaults** (QW5): missing inputs → `needs_input` | — |
| `visual_rag_service` / `colpali_retrieval_service` | page-render cache stays (viewer and VLM inputs); ColPali becomes the optional `embedding_visual` capability; fallback random vectors removed (fail loud) | — |
| `evaluation_service` | `heuristic_overlap` metric, labelled, never a verdict | — |
| Safety validator stage (`backend/agent_orchestrator.py:406-427`) | Critic node; until it lands, the UI label says "Not verified" (honesty QW4) | — |

**Migration steps** (each one is small and independently reviewable, with its test):

1. `router/registry.py` + `config/models.yaml` (cpu_lite from installed models) + validation V1–V10.
   - Tests: §1.5 list; `test_missing_model_is_unavailable_not_substituted` (pitfall §11.5).
2. `router/hardware_probe.py` + `hardware_profiles.yaml` + lifespan hook + `/api/health` fields.
   - Tests: §2.6 table.
3. `router/router.py` `resolve/get/candidates` (rank-only) + `ModelService` adapter.
   - Tests: "code vs reasoning resolve separately", unknown capability raises, every call audited with requested vs served (PLAN 0.4).
4. Provider clients (Ollama streaming without double call; `num_ctx` from `max_context`; `OLLAMA_HOST` honoured).
   - Test: a mock server counts exactly 1 generate request per call.
5. `orchestration/state.py` (PLAN §7.3) + LangGraph graph wrapping the existing workers (ADR-0003).
   - Tests: routing per `task_type` **through the compiled graph** (pitfall §11.1); reducers, no in-place mutation (§11.2).
6. DAG executor + Scheduler/GpuBudget.
   - Tests: independent subtasks overlap in time; blocked dependants are SKIPPED, not dropped; `max_parallel_llm=1` serialises; cancel stops within one subtask (§11.11).
7. Cascade + Critic deterministic layer.
   - Tests: a degraded output never PASSes (§11.5); a failed tool returns `succeeded=False` (§11.7); an escalation event is emitted; budget exhaustion → human review.
8. Critic LLM pass + task evaluation + scorecard rewire.
   - Tests: an injected UNSUPPORTED claim → NEEDS_REVISION; `cross_family` recorded.
9. Typed SSE + legacy adapter.
   - Test: a token containing `[DONE]` doesn't terminate the stream.
10. **Wiring test** (pitfall §11.6): on the RCA fixture task, spies assert that router, scheduler, critic, injection guard, audit and the context manager are each invoked ≥1 time. On cpu_lite, Correlation is reported as `unavailable`, not invoked.
11. Bench repointing: B4 imports the real `classify_intent`/planner instead of a regex copy (`bench/b4_router_accuracy.py:44-78`); B1 results populate `latency_profile` with a `bench_run_id`.

**Not tested yet / cannot be tested on this machine:**
- all `gpu_*` and `apple_full` runtime behaviour (only the probe is unit-tested with mocks)
- vLLM
- ColQwen2 on GPU
- tool-calling parity of quantized models (Phase 2.3)

The swimlane timings in §10.3 are illustrative, not measurements.

---

## 13. Decisions this design needs from the user

1. **C1:** local-only (the `hf` block stays empty) or a dual profile with a hosted dev block.
2. **PLAN §12.7:** the embedding model lock (recommendation: bge-m3 everywhere; nomic-embed-text until then, which means re-embedding once).
3. **Mac policy:** "full quality" scales by unified memory (recommended), or always uses the largest models.
4. **cpu_lite Coding agent:** off by default (recommended), or on with long timeouts.
5. **Tier override in the UI** (ADMIN only), or env var only.
6. **Licences:** approval of Qwen / Gemma / IndicTrans2 / ColQwen2 terms for the target deployment.
7. **The 24 GB GPU MVP:** confirm the actual card (the arithmetic in §8 assumes 24 GB usable at 90%).
8. **ADR-0005 / ADR-0007 acceptance:** they add new registry fields, SubTask fields, AgentMessage fields and audit event types.
