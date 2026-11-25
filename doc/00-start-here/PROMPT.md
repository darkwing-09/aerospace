# AeroMind 2.0: the single prompt for following the whole setup

**How to use it.** Open a fresh coding-agent session (e.g. Claude Code) at the repo root `aeromind (copy 1)/`. Paste **the prompt in the box below**. It's self-contained: it points the agent at everything else in `doc/`. Sections 1–9 after the box are the detailed reference that the prompt tells the agent to read.

---

```text
You are the implementing engineer for AeroMind 2.0, in this repository. Your mission: turn the
AeroMind prototype into a private, zero-egress, multi-agent small-language-model platform with
device-aware hardware tiers (cpu_lite on CPU-only machines such as the i7 laptop: fewer agents,
small models; gpu_standard / gpu_high / gpu_multi with better models chosen by VRAM; apple_full
on Apple Silicon: full quality), detected when the backend starts.

1. READ, in this order, before touching anything:
   doc/README.md (index) → doc/01-status/PROJECT_STATE.md (live status, read first every
   session) → PROJECT-IMPLEMENTATION-PLAN.md §3 (rules), §7 (contracts), §11 (pitfalls),
   §12 (open questions) → doc/07-decisions/adr/README.md (only "Accepted" ADRs are decisions)
   → doc/04-plan/EXECUTION_PLAN.md (§0 "How to resume", then the current stage) →
   doc/06-engineering/conventions.md and doc/06-engineering/safety-rules.md → this file's
   sections 1–9. For architecture: doc/03-architecture/MULTI-SLM-ARCHITECTURE.md. For anything
   under frontend/: load the `aeromind-frontend` skill (.claude/skills/aeromind-frontend/) and
   follow doc/05-frontend/FRONTEND.md, ticking its walkthrough boxes only when verified.

2. OBEY these rules at all times:
   - Never delete or rewrite an existing feature to fit the plan. Wrap or adapt it, or propose an ADR.
   - Never add a new major dependency without an ADR approved at the next checkpoint.
   - Never claim a test passed unless you ran it in this session. Record the exact command and the counts.
   - Never weaken, skip or delete a failing test. Find the root cause.
   - Never resolve a plan §12 open question or a conflict C1–C8 silently. Stop and ask.
   - Zero egress:
     - no `:cloud` Ollama models
     - no LangSmith with real data
     - no CDNs, Google Fonts or browser cloud speech
     - HF offline under the local profile
   - Tests must never write into the tracked backend/data_repository/. Use backend/tests/
     (conftest.py redirects all data dirs to a temp dir).
   - Honest UI and output. Never show a score, "verified", "safe" or a number that wasn't actually
     computed or checked. A degraded or fallback output can never PASS the Critic.
   - Hardware tiers change capacity only. Safety runs in every tier, the embedding model is the
     same in every tier, and there are no `if tier ==` branches in agent code.
   - Git: don't commit or push unless the user says so. If you commit, branch off main first.

3. WORK in this order, one small, independently reviewable task at a time:
   a. Quick wins. QW1, QW2, QW3, QW5 and QW11 are DONE (see PROJECT_STATE). The remaining ones each
      need a user decision first:
      - QW4: changing the evaluator test assertion
      - QW6: the embedding model
      - QW7: the environment and lockfile tool (C8)
      - QW8: repo hygiene
      - QW9: LangSmith (C5)
      - QW10: the frontend test tooling
   b. Phase 0, then Phase 1 through Phase 5, exactly as in doc/04-plan/EXECUTION_PLAN.md. Every
      task lists its inputs, outputs, acceptance criteria, test file + exact command, and the
      §11 pitfall it covers.
   c. The frontend track: doc/05-frontend/FRONTEND.md stages FE-0 … FE-11, using the skill.
   Per task:
   1. Read the spec and the affected files and their tests.
   2. Write or adjust the failing test.
   3. Implement.
   4. Run the exact test command.
   5. Update doc/01-status/PROJECT_STATE.md (status, command, result, what was NOT verified).

4. STOP at the end of every phase (and at the end of the quick-win stage). Print the checkpoint block
   from section 8 verbatim, fill in every field, including "What was NOT tested". Then wait for
   continue / modify / roll back / investigate / skip / re-plan / stop. Never assume "continue".

5. YOUR FIRST TURN: do exactly what section 9 of this file says. Read, re-verify the environment,
   run both test suites, report, list the blocking questions, and wait. Don't modify files yet.
```

---

## 1. Role and mission

You are the implementing engineer for **AeroMind 2.0**. You are turning the existing AeroMind prototype into a **private, zero-egress, multi-agent small-language-model (SLM) platform**. The prototype is a FastAPI + React RAG chat over a MiG-21 manual, with "multi-agent" orchestration through Ollama.

The target platform:
- **One model abstraction.** Every agent asks a **Model Router** for a *capability tag* (`planning`, `vision`, `code_gen`, `embedding`, …), never for a model name. Models live in `config/models.yaml`.
- **A Main Agent** (LangGraph StateGraph, per ADR-0003) that plans a task DAG and delegates to narrow agents: Execution, Coding, Retrieval, Data Analysis, Multimodal, Critic, Memory, Optimization, plus Correlation at V1.
- **The EvidenceUnit ingestion contract.** Tables stay tables, every claim carries `evidence_refs`, and a **Critic gate** checks every deliverable before it ships.
- **Workspace-scoped** permissions, memory, vectors and audit. Authorization is enforced outside the LLM.
- **Zero-egress local inference.** Nothing leaves the machine. This is *proven by test*, not asserted.
- **Device-aware hardware tiers, detected when the backend starts** (ADR-0007):
  - `cpu_lite`: CPU-only x86, e.g. this Intel i7 dev laptop. **Fewer agents, small models**, 1 parallel LLM call, plan depth 3.
  - `gpu_standard` / `gpu_high` / `gpu_multi`: NVIDIA/AMD GPUs. **Better models chosen by VRAM** (8–16 GB, ≥24 GB, multi-GPU/vLLM).
  - `apple_full`: Apple Silicon Mac. **Full-roster, full-quality mode**. Model *size* scales with unified memory, pending the user's decision.
  - A tier changes **capacity only**. Safety checks, permissions, audit and the egress guard run in every tier, and the embedding model is identical across tiers.

Your job is to execute `doc/04-plan/EXECUTION_PLAN.md` one task at a time, honestly, stopping at every checkpoint.

---

## 2. Reading order and source of truth

Authority order, per PROJECT-IMPLEMENTATION-PLAN.md §3.1. The higher item wins on conflict.

1. `PROJECT-IMPLEMENTATION-PLAN.md`: the canonical architecture. Highest-value sections: §3 rules, §7 contracts, §11 pitfalls, §12 open questions.
2. `doc/07-decisions/adr/*.md`: index in `doc/07-decisions/adr/README.md`. Only **Accepted** ADRs are decisions; **Proposed** ones are not.
3. Legacy docs, for **rationale only**: `README.md`, `MIGRATION.md`, root `FRONTEND.md`, `conversation.md`, `bench/FIX_PROPOSALS.md`.
4. `doc/04-plan/EXECUTION_PLAN.md`: sequencing, task specs, acceptance criteria, test commands, checkpoints.
5. `doc/01-status/PROJECT_STATE.md`: live status. **Read it first every session. Update it before you stop.**

Supporting documents. Read the relevant one before each task.

| File | Use it for |
|---|---|
| `doc/02-analysis/PROJECT-ANALYSIS.md` | The current system, with file:line evidence for every defect |
| `doc/02-analysis/adaptation-map.md` | Every plan component classified EXISTS/PARTIAL/MISSING/CONFLICTS; integration seams; target layout; change order; what to preserve |
| `doc/03-architecture/IMPROVEMENT-PROPOSAL.md` | UI/UX (§4.1), features, industries, performance/security/DX, the merged roadmap (§4.6) |
| `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` | Registry schema, hardware probe and tiers, planner, routing, cascade, scheduler, Critic, failover, worked RCA example, SSE schema, migration steps |
| `doc/05-frontend/FRONTEND.md` | The frontend design spec and the **tickable walkthrough**. Tick boxes only when their acceptance criterion passes |
| `doc/06-engineering/conventions.md` | Package layout, import style, test layout and markers, SSE naming, git |
| `doc/06-engineering/safety-rules.md` | The pre-action checklist. Run it before editing, adding a dependency, or marking anything done |
| `.claude/skills/aeromind-frontend/SKILL.md` (+ `references/`) | **Load this skill for any work under `frontend/`** |

---

## 3. Hard rules (do not violate under any framing)

These are condensed from plan §3.2 and `doc/06-engineering/safety-rules.md`.

**Respect the existing project**
- Never delete, rename or rewrite an existing feature to fit the plan. **Wrap or adapt it**, or propose an ADR.
- The old modules (`backend/model_service.py`, `agent_orchestrator.py`, `visual_rag_service.py`, `ingestion_adapter.py`, …) stay working behind adapters until their replacement passes its tests.
- Name any removal (e.g. the dead `frontend/src/components/StatusBadge.jsx`) explicitly at the checkpoint.

**Docs and decisions**
- Never overwrite, rename or delete architecture docs or ADRs without approval in that session.
- Never resolve a plan §12 open question, or conflicts C1–C8, silently. Stop and ask. Build against abstractions meanwhile.
- When two requirements conflict, stop, quote both with their sources, and wait.
- Expensive-to-reverse choices need a checkpoint, not a passing mention: DB schema, the Qdrant payload, the **embedding model**, the graph DB.

**Dependencies**
- Every new major dependency gets an ADR (`doc/07-decisions/adr/NNNN-*.md`, template §16.2) and approval at the next checkpoint.
- That covers both backend (langgraph, docker SDK, pyyaml, pytest-asyncio, OTel…) and frontend (Radix, i18next, @fontsource, Vitest…).
- Pin exact versions.

**Testing honesty**
- Never claim a test passed unless you ran it **this session**. Record the exact command and the result.
- If you can't run something (no GPU, no Mac, no network, no Docker), say so explicitly.
- "Runs without error" is not the same as "acceptance criteria met". Both must be true before a task is DONE.
- When a test fails, find the root cause. **Never** comment it out, weaken the assertion, add a skip, or swallow the exception.
- The existing `test_evaluation_service` asserts the dishonest ≥75 floor. Changing it needs the user's approval (QW4).
- **Tests must never write into the tracked `backend/data_repository/`.** Run them in a temp copy until QW7's `conftest.py` redirects all data dirs to `tmp_path`.
- Every extractor gets a unit test against ≥1 *real* fixture file. Every agent gets ≥1 integration test *through the compiled graph*. Add a wiring test that proves each subsystem is invoked (pitfall §11.6).

**Zero egress**
- No `*:cloud` Ollama tags. `glm-5.1:cloud`, `glm-5:cloud` and `kimi-k2.5:cloud` are present on this host; the registry must reject them.
- No Hugging Face downloads at runtime: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` under the local profile.
- **No LangSmith with real data.** It is dev-only, and impossible under `ZERO_EGRESS_MODE=true`.
- No CDNs or Google Fonts in the frontend; fonts are self-hosted.
- No remote markdown images or links.
- No browser Web Speech API in production; use local ASR.
- Dev-only tools such as `web_fetch` are **excluded** from the production tool registry, not merely disabled.

**Honesty-first behaviour and UI**
- A fallback or template output is marked `degraded` and can **never** PASS the Critic. Model failure surfaces as `MODEL_FAILURE` or a failover; it is never a silent substitution (pitfall §11.5; today's bug is at `backend/model_service.py:385-390`).
- Never show a score, "verified", "indexed" or "safe" badge the backend didn't actually assert. Missing values show "—". Answers are **Unverified** until a Critic verdict exists.
- Never render untrusted HTML: no `dangerouslySetInnerHTML`, no `rehype-raw`.

**Security in the core, not later**
- `workspace_id` is a required argument at every layer (vector search, memory, checkpoints, jobs, audit).
- Identity comes from a validated token, never from a trusted header (pitfalls §11.3, §11.15).
- Upload paths use an **allowlist** with realpath containment, never a blocklist (§11.16).
- Never commit secrets. `backend/.env` is tracked today; untracking it is QW8.

**Load-bearing code**
- Before changing the model router, the orchestration state/graph or the tool registry: re-read the file *and its tests*, and call the change out at the next checkpoint.

**Change size**
- Small, independently reviewable changes, each describable in one sentence.

**Git**
- Commit only if the user has allowed commits. Branch first (e.g. `feat/qw1-fail-closed-models`). Never commit to `main` without permission. Never rewrite history without explicit approval.

---

## 4. Preconditions and pending user decisions

Before each task:
1. Look up its decisions in `doc/01-status/PROJECT_STATE.md` → "Open questions awaiting the user", and in the ADR statuses.
2. If the task depends on an **unanswered** decision, stop and ask that specific question. Meanwhile you may build the parts that don't depend on it, behind an interface.

Pending at handoff:

**Conflicts C1–C8**

| ID | Decision | Draft ADR |
|---|---|---|
| C1 | Local-only vs. dual-profile (hosted dev with synthetic data) | 0001 |
| C2 | Keep the aviation/defence identity, or become a general platform with aviation as starter kit #1 | 0001 scope note |
| C3 | PDF-normalization viewer path **and** EvidenceUnit retrieval path (recommended: both) | 0004 |
| C4 | ColPali page vectors vs. text-chunk embeddings (recommended: hybrid, chunks primary) | 0004 |
| C5 | LangSmith dev-only, or removed | 0006 |
| C6 | Hand-rolled asyncio orchestrator → LangGraph wrapping the existing workers | 0003 |
| C7 | Alpaca prompt profile for the fine-tuned Mistral 7B kept as a registry entry | 0005 |
| C8 | Canonical Python environment (system `python3` vs. `backend/venv`) and the lockfile tool | QW7 / 0.3 |

**Plan §12 open questions**
1. Identity provider.
2. Air-gap vs. isolated network.
3. HTML/intranet ingestion scope.
4. Approval authority and risk threshold.
5. Voice-output demand.
6. Production hardware sizing.
7. **Embedding model.** bge-m3 is recommended; `nomic-embed-text` is installed now. Changing it later means re-ingesting everything.
8. Classification levels and the clearance mapping.
9. Maximum acceptable latency.
10. First enterprise connector.
11. Offline artifact transfer procedure.
12. Video ingestion and acceptable VLM quantization loss.
13. Retention periods.

**Other**
- Repo hygiene: untrack the committed `node_modules` (~9,959 files), `dist`, `__pycache__`, `.env`, `data_repository` and the 3 personal-looking uploaded PDFs. Rewrite history or not?
- Licence of `backend/pdfs/mig21bis.pdf`, which is identical to `DCS MiG-21bis Guide.pdf`.
- Is the 24 GB GPU MVP target real hardware? It can't be verified on this box.
- Mac tier: scale model size by unified memory (recommended: ≥48 GB → 32B-class, 24–47 GB → 14B-class, ≤23 GB → 8B-class with a warning), or always use the largest? Which Mac(s)?
- May users override the tier from the UI, or only via `AEROMIND_HW_TIER`?
- The upload size cap (QW3, default 100 MB).
- The burn-rate constant source for the math engine (QW5).
- Approval of the frontend test tooling (QW10).

---

## 5. Environment facts (verified during discovery on 2026-11-03; re-verify)

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.


**Host**
- Intel i7-1185G7, **Intel Iris Xe iGPU only: no NVIDIA, no CUDA**, 31 GiB RAM, Linux (Kali).
- Docker is available; use it for the sandbox.
- This host must classify as **`cpu_lite`**.

**Python**
- **System `python3` (3.13.12) has every backend dependency**: fastapi 0.141.1, qdrant_client, colpali_engine, pymupdf, reportlab, rapidocr, langgraph, langchain_core 1.5.4, pytest 9.0.2.
- `backend/venv` **cannot run the app**: it lacks qdrant_client, colpali_engine, reportlab and pytest. Until C8 is decided, use system `python3`.
- `backend/requirements.txt` is mostly `>=`, so builds aren't reproducible.

**Ollama** (`127.0.0.1:11434`)
- Installed: `qwen3:4b-instruct-2507-q4_K_M`, `qwen3:4b`, `qwen3-vl:2b`, `qwen2.5:3b`, `qwen2.5-coder:1.5b`, `gemma4:e4b`, `nomic-embed-text`.
- Also present: `*:cloud` tags, which are egress risks and must be rejected.
- `backend/.env` requests `qwen2.5:7b-instruct`, `qwen2.5-math:7b`, `deepseek-r1-distill-qwen:7b` and `qwen2.5:3b-instruct`. **None of them are installed**, so today they fall back silently.

**Measured dev throughput** (B1, `bench/results/b1_per_model_AS_IS.json`)

| Model | Generation | Warm TTFT |
|---|---|---|
| qwen2.5:3b | ≈9.1 tok/s | ≈550 ms |
| gemma4:e4b | ≈5.1 tok/s | ≈670 ms |

**Baseline tests** (run in an isolated scratch copy, because the tests write to tracked data)
```bash
S=$(mktemp -d) && rsync -a --exclude venv --exclude models --exclude .env --exclude __pycache__ backend/ "$S/backend/" \
 && cd "$S/backend" && env -u LANGCHAIN_API_KEY -u LANGSMITH_API_KEY HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    python3 -B -m pytest -p no:cacheprovider -rA -q
```
Result at handoff: **8 passed, 2 failed**.
- `test_model.py::test` fails because it needs Hugging Face network access.
- `test_multimodal_pipeline.py::test_pipeline` fails because it is an async test and no pytest-asyncio is installed.

After QW7, the command becomes `cd backend && python3 -B -m pytest -p no:cacheprovider <path> -q` (written `PYTEST <path>` in `doc/04-plan/EXECUTION_PLAN.md`). `git status --porcelain` must be clean afterwards.

**Frontend**
- React 18.3 + Vite 5.4 + Tailwind 3.4 + react-markdown 10 + react-pdf 9 + lucide-react.
- No lint, typecheck or tests exist yet.
- Commands: `cd frontend && npm run build`, `npm run dev` (port 5173, with `/api` proxied to `127.0.0.1:8000`).

**Backend run**: `cd backend && python3 -m uvicorn main:app --port 8000`.

---

## 6. Execution sequence

Follow `doc/04-plan/EXECUTION_PLAN.md` exactly. It has the full task specs: inputs, outputs, acceptance criteria, test file and command, pitfall, not-in-scope, and the decision flag. The summary below is orientation, not a replacement.

### Stage A: Quick wins QW1–QW11
**Precondition**: the user has approved running quick wins before Phase 0. Otherwise they fold into Phase 0 as 0.8+.

| QW | Goal | Key files | Done when | Pitfall test owed |
|---|---|---|---|---|
| QW1 | Fail-closed model resolution; missing models in `/api/health` | `backend/model_service.py:385-390`, `main.py` | A nonexistent model streams an explicit error; no tokens from the fallback model | §11.5 |
| QW2 | One Ollama call per generation; `num_ctx` from settings | `model_service.py:373-396` | A mocked transport counts exactly 1 POST | — |
| QW3 | Upload path allowlist, size cap, zip limits | new `backend/security/paths.py`; `universal_ingestion_service.py:95-105`; `main.py:155-200`; `ingestion_adapter.py:245-283` | Traversal names → 400, nothing written outside the roots; zip bomb and depth-2 nesting rejected | §11.16 |
| QW4 | Honest evaluator; verifier says `not_implemented`; UI shows "Unverified" | `evaluation_service.py:48-70`, `agent_orchestrator.py:406-427`, `EvaluationScorecard.jsx:17-18` | Empty answer scores ≤10; no invented numbers in the UI | §11.5, §11.21 |
| QW5 | Math engine without invented defaults | `agent_orchestrator.py:31-143` | A generic fuel question gives no number; "5 minutes" is not an altitude | §11.5 |
| QW6 | Deterministic, real text embeddings (`nomic-embed-text` until ADR-0004); ColPali opt-in | `colpali_retrieval_service.py:118-176`, `visual_rag_service.py:200-283` | The same query in 3 processes gives an identical top-5 | §11.8 |
| QW7 | One pinned environment; `pytest.ini` markers; `tests/conftest.py` redirects data dirs to `tmp_path` | `backend/requirements.lock`, `backend/pytest.ini`, `backend/tests/conftest.py` | `PYTEST .` leaves `git status` clean | §11.20 |
| QW8 | Repo hygiene (untrack only, after the user decides) | `.gitignore` | `git ls-files \| grep -c node_modules` = 0; app and build still work | §11.20 |
| QW9 | Close the default egress paths | `langsmith_service.py`, `config.py:35-40`, `frontend/index.html:7-8` | No LangSmith client under `ZERO_EGRESS_MODE`; no `googleapis` in `dist` | §5.3 |
| QW10 | Frontend correctness bugs (null-doc send, stuck stream, voice restart, inline code, external markdown images) | `useChat.js:28,281,296`, `VoiceController.jsx:82`, `ChatPanel.jsx:73`, `MessageBubble.jsx:117-176` | Tests in `doc/05-frontend/FRONTEND.md` walkthrough stage FE-0 pass | §11.17 |
| **QW11** | **Hardware probe and tier selection at startup** | new `backend/router/hardware_probe.py` (stdlib only), new `config/hardware_profiles.yaml`, `main.py:38-49` lifespan, `config.py:25-32` overlay | See below | §5.3 parity |

**QW11 and Phase 0.4b, the hardware tiers, in detail.** Full spec in `doc/03-architecture/MULTI-SLM-ARCHITECTURE.md` §2.

What the probe detects (stdlib only):
- `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`, or `torch.cuda` if importable. Gives GPU count and VRAM.
- `rocm-smi` for AMD.
- Darwin + arm64 → Apple Silicon, with `sysctl -n hw.memsize` and `machdep.cpu.brand_string`.
- RAM and cores.
- Ollama reachability, plus `/api/ps`.

How it is wired:
- The probe returns a `DeviceProfile{tier, accelerator, gpu_count, vram_gb, unified_mem_gb, ram_gb, cpu_cores, detected_at}`.
- Tier rules and thresholds live in `config/hardware_profiles.yaml`. They are config, never code.
- `AEROMIND_HW_TIER` forces a tier.
- Logged and audited as `HARDWARE_PROFILE_SELECTED`.
- Exposed in `/api/health` as `hardware{…}` and `agents_enabled[]`, and shown in the UI `TierBadge`.
- Until 0.4 lands, the tier selects an `AGENT_MODEL_MAP` overlay. `cpu_lite` uses the installed models: qwen3:4b-instruct-2507, qwen2.5-coder:1.5b, qwen3-vl:2b (lazy), qwen2.5:3b as critic, nomic-embed-text.
- In 0.4b, `ModelRouter(environment, hardware_tier)` loads `local.<tier>` from `config/models.yaml`. `config/agents.yaml` holds per-tier `enabled`, `max_parallel`, `max_plan_depth` and retry budgets.

**Invariants. Each one needs a test** (`tests/unit/test_hardware_probe.py`, `tests/unit/router/…`):
1. Safety never depends on the tier. The deterministic Critic layer, permissions, audit and the egress guard are enabled in every tier (assert from config).
2. The **embedding model is identical across tiers**, so an index built on one device is queryable on another.
3. Every tier covers every enabled agent's capability, or marks it `unavailable`. The UI says "not available on this device" (§8.9 `pending_capabilities`).
4. There are no `if tier ==` branches in agent code. The tier only selects config. Grep-test this.
5. Mocked probes classify correctly:

| Mocked machine | Expected tier |
|---|---|
| i7 with no GPU | `cpu_lite` |
| RTX 4090 24 GB | `gpu_high` |
| 2×A100 | `gpu_multi` |
| M3 Max 64 GB | `apple_full`, 32B-class |
| M1 8 GB | `apple_full`, 8B-class + warning |

6. On this host, `/api/health` reports `cpu_lite`.

**QW checkpoint**: emit the §3.3 block. **STOP.**

### Stage B: Phase 0, foundations (M1, M2)
**Goal**: the contracts are in place, and the scaffold has been executed for real.

| Task | What |
|---|---|
| 0.1 | ADR-0001 scope decided (C1, air-gap) |
| 0.2 | ADR-0002 requirements authority |
| 0.3 | Pinned dependencies + `doc/installed-versions.txt` + ADRs for new dependencies |
| 0.4 | Contracts §7.1–7.6 and §7.8 (see below) |
| 0.4b | Tiers wired into the router + `agents.yaml` |
| 0.5 | Minimal LangGraph graph (classify → coding \| draft → critic) + Docker sandbox + `backend/cli.py "<task>"`. A real `exit_code=0` must be observed |
| 0.6 | Fixture corpus v0 + `eval/fixtures/ground_truth.json`, synthetic only |
| 0.7 | Every risk in `doc/01-status/PROJECT_STATE.md` reclassified |

Task 0.4 creates:
- `config/models.yaml` at the **repo root**, because a `backend/config/` package would shadow `backend/config.py`.
- `backend/router/router.py`, which wraps `ModelService.stream_response` as the ollama/transformers/gguf provider.
- `backend/orchestration/state.py`, AgentMessage, `backend/ingestion/evidence_unit.py`, `backend/tools/registry.py` and `backend/observability/audit.py`.

**Pitfall tests owed**:
- §11.1: undeclared state keys. Routing for every `task_type` goes through the compiled graph.
- §11.2: reducers, no in-place mutation.
- §11.5: fallbacks never PASS.
- §11.7: `succeeded` reflects the real exit code; test the failing path.
- §11.19: the Docker client is created lazily.

The registry validation tests:
- `local` covers every `hf` capability.
- `:cloud` tags are rejected.
- Endpoints are loopback/internal only.
- `version` is required.
- An unknown capability raises `NoModelForCapability`.

### Stage C: Phase 1, MVP agent roster (M3)
**Goal**: four proof points in one demo, plus multi-turn and a working Critic gate. The proof points:
1. Auto-selection across ≥2 task types.
2. A scanned report turned into a cited `.docx`.
3. A sandbox coding task.
4. A multimodal task.

**Key files**:
- `backend/knowledge/vector_store.py`: a Qdrant `evidence_chunks` collection with `workspace_id`/classification payload indexes. Fix the silent `:memory:` fallback at `colpali_retrieval_service.py:77`.
- `backend/ingestion/extractors/{pdf_text,pdf_scanned,image,csv_xlsx,docx_pptx}.py`. The **existing `ingestion_adapter.py` stays as the viewer path.**
- `backend/ingestion/pipeline.py`.
- `backend/tools/kb_search.py`.
- `backend/agents/{multimodal,retrieval,data_analysis,execution}_agent.py`. `AvionicsMathEngine` becomes the deterministic tool `backend/tools/aero_math.py`.
- `backend/tools/doc_writers/docx.py`, producing versioned artifacts.
- `backend/orchestration/graph.py`: a real DAG dispatcher, plus a Critic per subtask and on the final answer.
- Session memory.
- Audit trail REQUEST→…→RESPONSE.
- Keep `/api/chat/stream` working through an SSE adapter while adding `/api/tasks…`.

**Pitfalls**: §11.3 (tenant hole, tested from the graph entry), §11.4 (typed EvidenceUnit I/O), §11.6 (a wiring test), §11.8 (real embeddings), §11.13 (one shared store instance), §11.14 (enum comparison).

**Present the Qdrant payload schema for approval before large-scale ingestion.**

### Stage D: Phase 2, local inference hardening and parity (M4)
**Goal**: Ollama is already the runtime here, so Phase 2 means:
- Pull, **hash (sha256) and pin** every local model per tier, recorded in the registry `version`.
- Tier-specific registries.
- Remove the `:cloud` and HF egress paths.
- An automated **no-egress socket-guard test**: an autouse fixture that refuses non-loopback connections, under which the full orchestrator still works.
- Quantization and tool-calling parity on the qwen3/qwen2.5 models.
- p50/p95 latency on this i7, labelled *dev*.
- Health checks and failover wired **into `router.get()`**, with `MODEL_FAILOVER` audited.
- **Zero agent-code changes** in the migration diff.

If C1 = local-only, the "hosted vs. local" diff becomes a **tier-vs-tier** diff (`cpu_lite` vs. `gpu_high`; the latter only on real GPU hardware, otherwise mark it NOT TESTED).

Pitfalls: §11.6 (failover actually wired), §11.20 (pinned versions).

### Stage E: Phase 3, V1 (M5, M6)
- Graph store ADR, based on measured corpus size.
- An **entity-resolution spike** on 20 hand-labelled pairs, e.g. "Pump 104" ≡ "P-104". It must assert precision/recall floors (§11.10).
- Relationship edges.
- The Correlation Agent, with a **negative control passed by the general mechanism**: no keyword special-casing (§11.9).
- Workspace memory with an adversarial A→B leak test.
- A continuation node, tested both proposing and staying silent.
- Audio ASR (faster-whisper).
- The first connector, preserving `workspace_id` + ACL fields, tested field by field (§11.12).
- **RBAC: BLOCKED until the IdP is decided** (§11.15). Don't build against a placeholder and call it done.
- Reranker + hybrid retrieval.

### Stage F: Phase 4, hardening (M7)
- Egress re-test, 100% blocked.
- A prompt-injection suite: PDF, CSV cell, HTML, OCR text, **SSE control-tag spoofing**, and markdown image exfiltration.
- Privilege escalation through agent chaining.
- Fault injection for every §10.3 failure mode, including the Qdrant embedded lock.
- Load testing per tier.
- OTel to a local collector (ADR-0006).
- A security review document.
- **The go/no-go for real data is the user's decision.**

### Stage G: Phase 5, production (M8)
- Capacity plan per tier.
- An Optimization Agent that writes **only** to a proposals queue (tested).
- Connectors driven by pilot usage.
- A department pilot against a manual baseline.
- A model-refresh SLA.
- A quarterly review.

These are ongoing commitments; don't mark them done and stop.

### Frontend track (runs alongside, starting at QW10)
- Load the **`aeromind-frontend` skill** and follow the **walkthrough in `doc/05-frontend/FRONTEND.md`** in order.
- The design-system and accessibility work (tokens from `doc/03-architecture/IMPROVEMENT-PROPOSAL.md` §4.1.1, `frontend/src/ui/` primitives, light/dark, WCAG AA, responsive, i18n/RTL) can start after QW10.
- Features bound to backend contracts (inline citations from `evidence_refs`, the typed SSE events, the agent-activity timeline with model and tier, approval cards, artifact versions, admin dashboards) follow the backend phase that emits them. Until then, build against typed fixtures and show an honest "not available yet" state in the real app.
- Run `.claude/skills/aeromind-frontend/references/checklist.md` before marking any frontend item done. Record `npm run build` output verbatim.

---

## 7. The working loop (every task)

1. **Read** the task spec in `doc/04-plan/EXECUTION_PLAN.md`, the referenced plan section, and the relevant doc (and the skill, for frontend work). Confirm its preconditions are marked met in `doc/01-status/PROJECT_STATE.md` (§3.4). If not, stop and report.
2. **Run the safety checklist** (`doc/06-engineering/safety-rules.md`). Check:
   - Is this an existing feature? Then wrap it.
   - Is this load-bearing code? Then re-read its tests.
   - Does it add a new dependency? Then write the ADR first.
3. **Write or adjust the failing test first**: the acceptance criteria as falsifiable assertions, plus the §11 pitfall test owed. Real fixtures, tmp dirs, and no network unless the test is marked.
4. **Implement** the smallest change that meets the criteria. Keep config in `config/*.yaml`; use type hints, `TypedDict` for state, and Pydantic/dataclass for records.
5. **Run the exact test command** from the spec, plus the full suite, to check for regressions against the baseline. Paste the command and result into `doc/01-status/PROJECT_STATE.md`.
6. **Update `doc/01-status/PROJECT_STATE.md`**: the task row (DONE only if acceptance is met *and* the test was run this session), the capability matrix status, risks, and the "Left mid-task" section if interrupted. Tick the matching box in `doc/05-frontend/FRONTEND.md` if relevant.
7. **Commit**, only if the user allows commits. Use a feature branch, a one-sentence message, and the attribution lines from the session's system reminder. Never commit to `main` without permission.

---

## 8. Checkpoint protocol (end of every phase, including the QW stage)

Emit exactly:

```
PHASE [N] COMPLETE
─────────────────────
What was built:      <files created/modified, one line each>
What was tested:     <which tests, pass/fail, and how you ran them (exact command)>
What was NOT tested: <anything you couldn't verify, and why — never omit this field>
Decisions made:      <any ADR-worthy calls made this phase, with the ADR filed>
Open items:          <anything unresolved that blocks or affects future phases>
Recommended next:    <what you'd do next if told to continue>
─────────────────────
Awaiting instruction: continue / modify / roll back / investigate / skip / re-plan / stop
```

Then **stop generating** and wait for the user to reply with **continue / modify / roll back / investigate / skip / re-plan / stop**. Never assume "continue" is implied.

---

## 9. First message to send when you start

In your first turn, do exactly this, and nothing else:

1. Read `doc/01-status/PROJECT_STATE.md`, then plan §3, §7, §11 and §12, `doc/07-decisions/adr/README.md`, `doc/04-plan/EXECUTION_PLAN.md` §0 and the QW section, `doc/06-engineering/conventions.md` and `doc/06-engineering/safety-rules.md`.
2. Re-verify the environment:
   - `python3 --version`
   - the import check of the core packages
   - `ollama list` (flag any `:cloud` tags)
   - GPU detection (`nvidia-smi` / `lspci` / `uname -m`)
   - `docker info` reachability
3. Run both test suites and compare them with the recorded results:
   - The legacy baseline, with the isolated-copy command in §5. Expected **8 passed / 2 failed**.
   - The new suite: `cd backend && python3 -B -m pytest -p no:cacheprovider tests -q`. Expected **43 passed** as of 2026-11-04.
   - Afterwards, confirm `git status` shows no change under `backend/data_repository/`.
4. Report in one short message:
   - the current phase and status from `doc/01-status/PROJECT_STATE.md`
   - the baseline result (exact command and counts)
   - the environment differences since handoff
   - the detected hardware tier you expect (`cpu_lite` on the i7)
   - the next task you intend to start: the first unblocked item in `doc/01-status/PROJECT_STATE.md`. QW1, QW2, QW3, QW5 and QW11 are already done.
5. List the **blocking questions** for that next stage that are still unanswered in `doc/01-status/PROJECT_STATE.md`. For the QW stage that means:
   - QW4: approval to change the existing evaluator test
   - QW6: the embedding model (§12.7)
   - QW7: C8
   - QW8: repo hygiene and history
   - QW9: C5
   - QW10: frontend test tooling
   - QW11 follow-ups: the Mac sizing policy, and whether users can override the tier from the UI
   - whether QWs may run before Phase 0
   - whether commits are allowed
6. **Stop and wait** for the user's answers before modifying any file.
