# doc/04-plan/EXECUTION_PLAN.md — AeroMind 2.0 → Private Multi-Agent Platform

> This file sets the order of the work and the checkpoints. It adapts PROJECT-IMPLEMENTATION-PLAN.md §9 to this repository. The plan itself is canonical (ADR-0001, Proposed). Where they differ, the plan wins unless an Accepted ADR says otherwise.
> Every phase ends with the §3.3 checkpoint. **Stop there and wait for the user.** Never assume "continue".

---

## 0. How to resume (fresh agent session)

1. Read `doc/01-status/PROJECT_STATE.md` first. It is the only live status source.
2. Re-read PROJECT-IMPLEMENTATION-PLAN.md §3 (rules), §7 (contracts) and §11 (pitfalls).
3. Read `doc/07-decisions/adr/*.md`. Only **Accepted** ADRs are decisions; **Proposed** ones are not.
4. Read `doc/06-engineering/conventions.md` and `doc/06-engineering/safety-rules.md`.
5. Find the current phase and its preconditions in this file. If a precondition is not marked met in `doc/01-status/PROJECT_STATE.md`, stop and report it (§3.4).
6. Set up the environment:
   - Until C8 is resolved, the only interpreter that imports the app is system `python3` (3.13). `backend/venv` is missing qdrant_client, colpali_engine, reportlab and pytest.
   - Ollama runs on `127.0.0.1:11434`.
   - Docker is available for the sandbox.
7. Run the test suite **in a temp copy, or with `AEROMIND_DATA_DIR` pointing at a tmp dir once QW7 lands**. Never run it against the tracked `backend/data_repository/`. Compare the result with the baseline: 8 passed / 2 failed.
8. Before stopping, update `doc/01-status/PROJECT_STATE.md`: task rows, any test you ran this session (exact command and result), and the "Left mid-task" section.

---

## 1. Conventions used in this file

- **Paths** are relative to the repo root.
  - New Python packages go under `backend/` (see `doc/06-engineering/conventions.md`).
  - Config goes in the repo-root `config/`. A `backend/config/` directory would shadow the existing `backend/config.py`.
- **Test command form**, used throughout:
  `cd backend && python3 -B -m pytest -p no:cacheprovider <path> -q`
  This is written below as **`PYTEST <path>`**.
- **"Wrap"** means the existing module stays and keeps working. New code calls it or sits in front of it. Nothing is deleted or rewritten without an ADR (§3.2).
- **Pitfall** refers to PLAN §11.N, the test you owe.
- **Decision** means an ADR or user answer is required before or at the checkpoint.

### Milestones → phases

| Milestone | Delivered by | Definition of done (adapted) |
|---|---|---|
| M1 Router + registry validated | 0.4, 0.4b | Capability resolution tests pass against the real `config/models.yaml` on this host's tier |
| M2 Single-agent task loop | 0.5 | Coding task end-to-end through the graph; sandbox `exit_code=0` observed |
| M3 Multi-agent MVP | Phase 1 | All four MVP proof points pass in one demo against the real KB |
| M4 Local inference parity | Phase 2 | Fixture pass-rate diff is recorded (hosted→local, or tier-vs-tier if C1 = local-only); no-egress test passes |
| M5 Correlation + memory | 3.1–3.6 | Positive fixture correlates; the negative control returns `NO_RELIABLE_CONNECTION` |
| M6 Conversational continuation | 3.7, 3.11 | Follow-up relevance is above the agreed threshold |
| M7 Security hardening | Phase 4 | Every §8.13 threat is mitigated by a passing test |
| M8 Production launch | Phase 5 | Review passed; the pilot shows measured time savings |

### Checkpoint template (emit verbatim at the end of each phase)

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

---

## PHASE −1 — Discovery and adaptation mapping (DONE, awaiting approval)

**Outputs**:
- `doc/02-analysis/PROJECT-ANALYSIS.md`
- `doc/02-analysis/adaptation-map.md`
- `doc/03-architecture/IMPROVEMENT-PROPOSAL.md`
- `doc/01-status/PROJECT_STATE.md` (with the baseline)
- this file
- `doc/06-engineering/conventions.md`, `doc/06-engineering/safety-rules.md`
- `doc/07-decisions/adr/0001…0007` (all Proposed)

**Acceptance (§4.2)**:
- Every §8 component is classified.
- The baseline is recorded verbatim.
- Every CONFLICTS item (C1–C8) has a draft ADR or a user question.
- The governance files exist.

**Checkpoint**: emit the template. **STOP.**

---

## QUICK WINS (QW) — small, safe, independently reviewable

**Preconditions**:
- The Phase −1 checkpoint is approved.
- The user has said that quick wins may run before Phase 0. Otherwise they fold into Phase 0 as 0.8+.

Each QW is a single-sentence change. None of them deletes a feature.

### QW1 — Fail-closed model resolution
- **Inputs**:
  - `backend/model_service.py:385-390`: a silent 404 fallback to `OLLAMA_MODEL`.
  - `bench/FIX_PROPOSALS.md` (a).
- **Change**:
  - On a 404, stop generating and emit an explicit error event naming the requested model.
  - At startup, validate every `AGENT_MODEL_MAP` value against `GET /api/tags` and report missing models in `/api/health`.
- **Outputs**: modified `backend/model_service.py`, `backend/main.py` (health field `missing_models`).
- **Depends on**: none.
- **Acceptance**:
  - With `MATH_MODEL=nonexistent:1b`, a math query streams an error containing `nonexistent:1b`.
  - No tokens from `qwen2.5:3b` are produced for that node.
  - `/api/health` lists the missing model.
- **Test**: `backend/tests/unit/test_model_resolution.py`, which mocks httpx for 404 and 200. Run with `PYTEST tests/unit/test_model_resolution.py`.
- **Pitfall**: §11.5.
- **Not in scope**: the new router (0.4).
- **Decision**: none.

### QW2 — Remove the double generation on the Ollama path
- **Inputs**: `backend/model_service.py:380-396`. A `client.post` with `stream:true` reads the full body, and then `client.stream` generates again.
- **Change**: one `client.stream` call; handle the 404 from `response.status_code` inside the stream context.
- **Acceptance**:
  - With a mocked transport counting requests, exactly 1 POST to `/api/generate` is made per call.
  - Measured wall time on `qwen2.5:3b` (dev i7) is recorded before and after in `doc/01-status/PROJECT_STATE.md`, labelled dev.
- **Test**: `PYTEST tests/unit/test_ollama_single_call.py`.
- **Pitfall**: none directly (performance). It also stops `num_ctx: 2048` (`:373`) being hard-coded. Make it `settings.N_CTX`, with the value recorded.
- **Decision**: none.

### QW3 — Upload path allowlist, size limits, ZIP limits
- **Inputs**:
  - `backend/universal_ingestion_service.py:95-105`
  - `backend/main.py:155-200`
  - `backend/ingestion_adapter.py:245-283`
- **Change**:
  - A new `backend/security/paths.py` with `safe_join(root, name) -> Path`. It sanitises the basename, resolves the realpath and asserts it is inside `root`, otherwise raises.
  - Max upload size from config.
  - ZIP: a cap on member count and total uncompressed size, nesting depth ≤ 1, and links rejected.
- **Acceptance**:
  - The filenames `../../x.pdf`, `..%2f..%2fx`, `/etc/passwd` and `a/../../b` all return HTTP 400, and nothing is written outside `UPLOADS_DIR`/`PDF_DIR`.
  - A 1 GB-expanding zip bomb fixture is rejected.
  - A nested zip at depth 2 is rejected.
- **Test**: `PYTEST tests/adversarial/test_upload_paths.py`. It uses a tmp `UPLOADS_DIR` and the FastAPI `TestClient`.
- **Pitfall**: §11.16.
- **Decision**: the upload size cap value (default 100 MB; user may change).

### QW4 — Honest evaluator and verifier labelling
- **Inputs**:
  - `backend/evaluation_service.py:48-50` (the `max(78, …)` floor) and `:70` ("VERIFIED_SAFE")
  - `backend/agent_orchestrator.py:406-427` (the canned verifier)
  - `frontend/src/components/EvaluationScorecard.jsx:17-18` (invented defaults of 85/95)
- **Change**:
  - Remove the floor and offset, and return the raw ratio.
  - Rename the outputs to `heuristic_*`.
  - The verifier node emits `status: "not_implemented"` until the 1.10 Critic exists.
  - The UI shows "Unverified (heuristic)" and no invented numbers.
- **Acceptance**:
  - An empty response scores ≤ 10 faithfulness and does not show "VERIFIED_SAFE".
  - Nonsense against an unrelated context scores < 30.
  - The UI shows no score when the backend omits it.
- **Test**: `PYTEST tests/unit/test_evaluation_honesty.py`. The existing `test_evaluation_service` must still pass, or be diagnosed. Its assertion `>= 75` encodes the floor, so the user must approve changing it. Never weaken a test silently.
- **Pitfall**: §11.5, §11.21.
- **Decision**: yes. The user must approve changing the existing test's assertion.

### QW5 — Math engine without invented defaults
- **Inputs**:
  - `backend/agent_orchestrator.py:31-143`: defaults `fuel_kg=2800` and `burn 58/280`; altitude regex `(\d+)\s*(?:m|meters|meter)` matches "5 minutes".
- **Change**:
  - Missing inputs produce `None` plus `missing_inputs: [...]`.
  - Burn rates come from a cited source (config, with a doc reference), never from literals.
  - Use a unit-aware regex (`\bm\b|meters?`).
- **Acceptance**:
  - "what is the fuel consumption of the engine" returns no endurance number.
  - "mach 2 for 5 minutes" does not set altitude = 5.
  - The existing `test_avionics_math` still passes.
- **Test**: `PYTEST tests/unit/test_math_engine.py tests/../test_multiagent_system.py::test_avionics_math`.
- **Pitfall**: §11.5 (a fabricated value presented as deterministic).
- **Decision**: the source for burn-rate constants (the user or the manual page).

### QW6 — Real text embeddings; ColPali opt-in
- **Inputs**:
  - `backend/colpali_retrieval_service.py:118, 136-176` (the random/`hash()` fallback)
  - `backend/visual_rag_service.py:200-283`
- **Change**:
  - Add a text-chunk collection embedded through Ollama `/api/embed`. Use `nomic-embed-text` now, because it is installed; bge-m3 waits for the ADR-0004 / §12.7 answer.
  - Make the fallback vectors deterministic with `hashlib` if they are kept, or drop them.
  - If neither ColQwen2 nor embeddings are available, return "retrieval unavailable" honestly.
- **Acceptance**:
  - The same query in 3 separate processes returns an identical top-5 (today it returns 3 different sets; see PROJECT_STATE).
  - Known-answer queries on the `mig21bis` fixture return the correct page in the top-3 (ground truth from 0.6).
- **Test**: `PYTEST tests/integration/test_retrieval_determinism.py`. It spawns subprocesses and uses a tmp Qdrant path.
- **Pitfall**: §11.8.
- **Decision**: **yes**. This is the embedding model choice (§12.7, ADR-0004), and it is expensive to reverse.

### QW7 — A single pinned environment and pytest config
- **Inputs**:
  - `backend/requirements.txt` (`>=` pins)
  - `backend/venv` (incomplete)
  - The tests write to the tracked `data_repository/`.
- **Change**:
  - Build `backend/requirements.lock` from the working interpreter.
  - Add `backend/pytest.ini` with markers: `needs_ollama`, `needs_network`, `needs_gpu`, `needs_docker`, `slow`.
  - Add `backend/tests/conftest.py`. It redirects `DATA_DIR`, `UPLOADS_DIR`, `PAGE_IMAGES_DIR`, `TRACES_DIR` and `QDRANT_PATH` to `tmp_path` through env overrides; `config.py` keeps its defaults.
  - Add `pytest-asyncio` as a dev dependency.
- **Acceptance**:
  - `PYTEST .` leaves `git status` clean.
  - `test_pipeline` runs; it passes or fails for a real reason, recorded.
  - `pip install -r requirements.lock` in a fresh venv imports every module.
- **Test**: `PYTEST . -q && git status --porcelain` (expected empty).
- **Decision**: **yes (C8)**. Pick the lockfile tool (pip-compile/uv/plain freeze) and decide whether the venv is canonical. Markers select tests; they never skip a failing one.

### QW8 — Repo hygiene
- **Change**:
  - Extend `.gitignore` to cover node_modules, dist, `__pycache__`, `.env`, `backend/data_repository/{uploads,traces,qdrant_db,page_images,adapter_scratch}`.
  - Run `git rm --cached` on the tracked copies.
- **Acceptance**:
  - `git ls-files | grep -c node_modules` returns 0.
  - The app still starts.
  - `frontend` `npm ci && npm run build` succeeds.
- **Decision**: **yes**. Untrack only, or also rewrite history? And what to do with the 3 personal-looking PDFs and the DCS manual licence?

### QW9 — Close the default egress paths
- **Inputs**:
  - `backend/langsmith_service.py:19-25, 89-100`
  - `backend/config.py:35-40`
  - `frontend/index.html:7-8` (Google Fonts)
- **Change**:
  - LangSmith is enabled only when `AEROMIND_ENV=dev` **and** a key is set. With `ZERO_EGRESS_MODE=true` it is impossible (the client is never constructed).
  - Self-host the Inter and JetBrains Mono woff2 files under `frontend/public/fonts`.
- **Acceptance**:
  - Under `ZERO_EGRESS_MODE=true` with a fake key set, no `langsmith.Client` is constructed (spy).
  - The built `dist/index.html` contains no `googleapis`.
- **Test**: `PYTEST tests/adversarial/test_no_cloud_tracing.py`, plus `grep -c googleapis frontend/dist/index.html` returning 0.
- **Pitfall**: §5.3 local-ready.
- **Decision**: C5 (ADR-0006).

### QW10 — Frontend correctness bugs
- **Inputs**:
  - `frontend/src/hooks/useChat.js:28` (no-op when `aircraftId` is null), `:281` (abort placeholder), `:296` (a stream ending with no `[DONE]` locks the input)
  - `frontend/src/components/VoiceController.jsx:82` (the recogniser restarts every render)
  - `frontend/src/components/ChatPanel.jsx:73`
  - `frontend/src/components/MessageBubble.jsx:164-172` (inline code)
  - `:117-176` (add `img`/`a` overrides that block external URLs)
- **Acceptance**:
  - Sending with no document selected either queries general chat or shows a visible prompt, and the input is not cleared.
  - Closing the stream without `[DONE]` unlocks the input.
  - Dictation survives typing.
  - `![x](https://evil/a.png)` renders as inert text.
- **Test**: `frontend/src/**/*.test.jsx` with Vitest + Testing Library. These are new dev dependencies, so they need ADR approval. Run with `cd frontend && npx vitest run`.
- **Pitfall**: §11.17.
- **Decision**: approve the frontend test tooling.

### QW11 — Hardware probe and tier selection at startup
- **Inputs**:
  - `backend/main.py:38-49` (lifespan)
  - `backend/config.py:25-32` (`AGENT_MODEL_MAP`)
- **Change**:
  - A new `backend/router/hardware_probe.py`, stdlib only. It detects `nvidia-smi`, `rocm-smi`, Darwin/arm64 with `sysctl hw.memsize`, RAM and cores, and returns a `DeviceProfile`.
  - A new `config/hardware_profiles.yaml` with the tiers `cpu_lite`, `gpu_standard`, `gpu_high`, `gpu_multi` and `apple_full`.
  - The `AEROMIND_HW_TIER` override.
  - The tier is reported in `/api/health`.
  - Until 0.4 lands, the tier selects an `AGENT_MODEL_MAP` overlay. `cpu_lite` = models installed today: qwen3:4b-instruct-2507, qwen2.5-coder:1.5b, qwen3-vl:2b, qwen2.5:3b.
- **Acceptance**:
  - Mocked probes classify correctly: i7 with no GPU gives `cpu_lite`; RTX 4090 24 GB gives `gpu_high`; 2×A100 gives `gpu_multi`; M3 Max 64 GB gives `apple_full` (32B class); M1 8 GB gives `apple_full` with the 8B class and a warning.
  - On this host, `/api/health` shows `cpu_lite`.
  - Safety components are enabled in every tier (assert from config).
- **Test**: `PYTEST tests/unit/test_hardware_probe.py`.
- **Pitfall**: §5.3 code parity (no `if tier ==` in agent code).
- **Decision**: ADR-0007. Also the Mac sizing policy and whether the UI can override the tier.

**QW checkpoint**: emit the template. **STOP.**

---

## PHASE 0 — Foundations and closing the verification gap

**Objective**:
- Get the §7 contracts in place.
- Run the minimal graph for real.
- Start the fixture corpus.

**Preconditions**:
- The Phase −1 checkpoint is approved.
- The QWs are approved (or folded in).
- ADR-0001 and ADR-0002 decisions are requested.

### 0.1 — Scope decisions → ADR-0001
- **Inputs**: `doc/07-decisions/adr/0001-canonical-source-of-truth.md` (Proposed); C1; §12.2.
- **Output**: ADR-0001 status set to Accepted, with the user's answers. These are: local-only vs dual-profile (`hf` dev with synthetic data only), air-gap vs isolated network, and whether hardware tiers (ADR-0007) are part of the profile rule.
- **Depends on**: the user.
- **Acceptance**: the ADR status field is updated, and the answers are quoted with the date.
- **Test**: none (doc).
- **Decision**: **user**.

### 0.2 — Requirements authority → ADR-0002
- **Output**: `doc/07-decisions/adr/0002-requirements-authority.md` Accepted. The plan plus this file's acceptance criteria are the spec. `MIGRATION.md` and `FRONTEND.md` are kept as rationale only, and no new PRD is written.
- **Acceptance**: the ADR is Accepted.
- **Decision**: **user**.

### 0.3 — Pinned dependencies
- **Inputs**: QW7 output; `backend/requirements.txt`.
- **Output**:
  - `backend/requirements.lock`
  - `doc/installed-versions.txt` (`pip freeze`)
  - New dependencies, each with an ADR: `langgraph`, `langchain-core`, `langchain-ollama`, `docker`, `pyyaml`, `pytest-asyncio`. langgraph and langchain_core are already importable in system python3; record their versions.
- **Depends on**: C8.
- **Acceptance**:
  - `python3 -c "import fastapi, qdrant_client, fitz, langgraph, langchain_core, docker, yaml"` exits 0 in the chosen environment.
  - The freeze is recorded.
- **Test**: the import check command above, recorded verbatim.
- **Pitfall**: §11.20.
- **Decision**: ADR-0003 (LangGraph) and ADR-0004 (Qdrant + extractor libraries).

### 0.4 — Core contracts (§7.1–7.6, §7.8)
- **Outputs**:
  - `config/models.yaml`. Generated from today's `AGENT_MODEL_MAP` plus `ollama list`. It has a `local:` block per hardware tier, plus `hf:` only if C1 allows it. Role names map to capability tags: `orchestrator→planning`, `synthesis→drafting`, `vision_table→vision`, `math→math`, `reasoning→general_reasoning`, `verification→evaluation`.
  - `backend/router/router.py` (`ModelRouter`, `NoModelForCapability`). It **wraps** `backend/model_service.py`. `ModelService.stream_response(capability=…)` keeps its signature and resolves through the router internally.
  - `backend/orchestration/state.py` (`WorkbenchState`, `EvidenceRef`, `ToolCallRecord`, `AgentMessage`).
  - `backend/ingestion/evidence_unit.py` (§7.5, every class with `to_dict`).
  - `backend/tools/registry.py` (`ToolSpec`, `_ALL_TOOLS`, `get_tools_for`).
  - `backend/observability/audit.py` (`AuditEvent`, `FailureCategory`, `scrub_secrets`, JSONL sink).
- **Depends on**: 0.3.
- **Acceptance**:
  - Default resolution returns the `default: true` entry.
  - `code_gen` and `general_reasoning` resolve to different entries.
  - An unknown capability raises `NoModelForCapability` with the valid tags listed.
  - The invariant "every `hf` capability is in `local`" holds, if `hf` exists.
  - Every tier covers every enabled agent's capability, or marks it unavailable.
  - A `:cloud` model or a non-loopback endpoint in `local` raises at load time.
  - `EvidenceUnit.to_dict()` round-trips.
  - `scrub_secrets` redacts `sk-`, `Bearer`, `AKIA`, `token=` nested.
- **Test**: `PYTEST tests/unit/test_router.py tests/unit/test_evidence_unit.py tests/unit/test_tool_registry.py tests/unit/test_audit.py`.
- **Pitfall**: §11.1 (declare `task_type`), §11.20.
- **Decision**: ADR-0005 (models.yaml fields), a load-bearing abstraction. Call it out at the checkpoint.

### 0.4b — Hardware tiers wired into the router
- **Inputs**: QW11 probe; `config/hardware_profiles.yaml`; `config/agents.yaml` (new; per-tier `enabled`, `max_parallel`, `max_plan_depth`).
- **Output**: `ModelRouter(environment, hardware_tier)` loads `local.<tier>`. An `AuditEvent(event_type="HARDWARE_PROFILE_SELECTED")` is emitted at startup.
- **Depends on**: 0.4, QW11.
- **Acceptance**:
  - With `AEROMIND_HW_TIER=cpu_lite`, `router.resolve("vision")` returns `qwen3-vl:2b`.
  - With `gpu_high`, it returns the gpu_high vision entry.
  - The embedding entry is identical across all tiers.
  - The Critic deterministic layer is enabled in all tiers.
  - Disabled agents report `pending_capabilities`.
- **Test**: `PYTEST tests/unit/test_hardware_tiers.py`.
- **Decision**: ADR-0007.

### 0.5 — Minimal graph + CLI
- **Outputs**:
  - `backend/orchestration/graph.py`: LangGraph `StateGraph` with `classify → (coding | draft → critic) → END` and a retry loop.
  - `backend/agents/coding_agent.py`
  - `backend/agents/execution_agent.py` (draft only)
  - `backend/agents/critic_agent.py` (deterministic layer plus one LLM pass)
  - `backend/tools/sandbox_exec.py` (Docker with `network_disabled`, `read_only`, `mem_limit=512m`, `pids_limit=64`, a 15 s timeout, and a lazy client)
  - `backend/cli.py "<task>"`
- **Existing code**: `agent_orchestrator.py` stays and keeps serving `/api/chat/stream`. The graph is mounted alongside it, with no rewrite.
- **Depends on**: 0.4, Docker.
- **Acceptance**:
  - `python3 cli.py "write a function that checks if a number is prime, and test it"` completes, and the output shows a real `exit_code=0` from the container.
  - `python3 cli.py "draft a short note summarizing last week's uptime"` either passes the Critic or is flagged `needs_human_review` (there is no evidence, so a FAIL is expected).
  - The output is captured verbatim in `doc/01-status/PROJECT_STATE.md`.
  - The coding agent returns `succeeded=False` on a forced failing test.
- **Test**: `PYTEST tests/integration/test_minimal_graph.py -m needs_docker` (asserts the node trace), plus the two CLI commands.
- **Pitfall**: §11.1, 11.2, 11.6, 11.7.
- **Decision**: ADR-0003 must be Accepted before this task.

### 0.6 — Fixture corpus v0
- **Outputs**: `backend/tests/fixtures/` and `eval/fixtures/ground_truth.json`. Contents, all synthetic or sanitised:
  - 1 text PDF (a generated maintenance SOP)
  - 1 scanned PDF/image (a rasterised page with known text)
  - 1 messy XLSX (merged cells, units, blank rows)
  - 1 short audio note (TTS-generated offline, for later)
  - 1 diagram PNG
  - plus 20 hand-verified Q/A pairs from `mig21bis.pdf`, **only if the licence is cleared**; otherwise from the synthetic SOP
- **Also**: migrate `bench/gold.jsonl` entries to `verified: true` only after human verification.
- **Acceptance**: every fixture has a ground-truth record; no real sensitive data.
- **Test**: `PYTEST tests/unit/test_fixtures_manifest.py` (files exist, sha256 matches the manifest).
- **Decision**: the DCS manual licence.

### 0.7 — Reclassify risks
- **Output**: in `doc/01-status/PROJECT_STATE.md`, each "Known risks" row becomes one of: verified working / confirmed broken (with an issue) / still unknown (with a reason).
- **Acceptance**: no row is left unclassified.

**DoD**:
- The scaffold has run against real infrastructure (Ollama, Docker) with observed output.
- The known risks are explicitly accepted or cleared.

**Risks**:
- Docker sandbox permission issues on this host.
- qwen2.5-coder:1.5b code quality may be too weak in `cpu_lite`. Record it, and don't hide it.

**Checkpoint**: emit the template. **STOP.**

---

## PHASE 1 — MVP agent roster

**Objective**:
- The Multimodal (PDF + image), Retrieval, Data Analysis and Execution agents.
- Qdrant behind `search_knowledge_base`.
- The DAG is executed, and the Critic gate is wired.

**Preconditions**: Phase 0 passed; ADR-0003 and ADR-0004 Accepted.

| ID | Inputs (AeroMind) | Outputs | Depends | Acceptance criteria | Test (`PYTEST …`) | Pitfall | Decision |
|---|---|---|---|---|---|---|---|
| 1.1 | `backend/colpali_retrieval_service.py:52-79` (embedded Qdrant; silent `:memory:` fallback at `:77`) | `backend/knowledge/vector_store.py`: collection `evidence_chunks`, COSINE, payload indexes on `workspace_id`, `classification_level`, `source_type`; point id = hash(unit_id, chunk_idx); a lock failure **raises** | 0.4 | Collection created with indexes; the payload schema is shown to the user **before large ingestion** | `tests/unit/test_vector_store.py` | §11.3 | **User approves the payload schema** (expensive to reverse) |
| 1.2 | `visual_rag_service.py:82-198` (page text, headings) | `backend/ingestion/extractors/pdf_text.py` → one EU per page `{doc}_p{n}`, headings, `source_ref=path#page=n` | 0.4 | Fixture PDF has the correct page count, headings and refs; a corrupted file gives `Document(status=FAILED)` with no exception | `tests/unit/test_pdf_text_extractor.py` | §11.4 | — |
| 1.3 | RapidOCR path (`visual_rag_service.py:113-125`) | `extractors/pdf_scanned.py`, `extractors/image.py`: OCR plus a VLM fallback (vision tag); low confidence tagged `uncertain`; placeholder text forbidden (replaces `ingestion_adapter.py:241`) | 1.2 | Fixture scan text matches the ground truth within the agreed CER; no-OCR returns PARTIAL + UNCERTAIN | `tests/unit/test_ocr_extractor.py` | §8.3 stub rule | OCR engine ADR (RapidOCR is existing; PaddleOCR is an option) |
| 1.4 | `ingestion_adapter.py` (kept as the **viewer** path) | `backend/ingestion/pipeline.py`: path allowlist (QW3), then scan, detect, extract, stamp workspace/classification, injection guard, chunk (800/150 with **real** overlap), embed through the router, upsert. Plus `extractors/csv_xlsx.py` with 20-row units (fixes the 15-row loss at `ingestion_adapter.py:180`) | 1.1–1.3 | E2E on the fixtures: every point has `workspace_id` and `classification_level`; all CSV rows are indexed | `tests/integration/test_ingestion_pipeline.py` | §11.14, 11.16, 11.19 | ADR-0004 (C3: both paths) |
| 1.5 | `universal_ingestion_service.py:193-253` | `backend/tools/kb_search.py` `search_knowledge_base(query, top_k, workspace_id, user_ctx)`; `workspace_id` required at every layer | 1.4 | The known query has the correct chunk in the top-3; a workspace-B query never returns A's units | `tests/adversarial/test_vector_isolation.py` | §11.3 | — |
| 1.6 | `visual_rag_service.get_page_image_base64` | `backend/agents/multimodal_agent.py` (vision tag; consumes `EvidenceUnit` objects) | 1.3, 0.5 | Integration through the graph on a fixture image works with non-empty evidence | `tests/integration/test_multimodal_agent.py` | §11.4 | VLM quantization acceptance (§12.12) |
| 1.7 | — | `backend/agents/retrieval_agent.py`: ≤2 reformulations, `sufficient`, `missing_information` | 1.5 | An unanswerable query gives `INSUFFICIENT_EVIDENCE`, with no fabricated answer | `tests/integration/test_retrieval_agent.py` | §11.3 | — |
| 1.8 | `AvionicsMathEngine` (`agent_orchestrator.py:31-143`) becomes the deterministic tool `tools/aero_math.py` | `backend/agents/data_analysis_agent.py`: sandboxed pandas plus `render_chart` | 0.5, 1.4 | Fixture spreadsheet question: correct number plus a citation to its row range | `tests/integration/test_data_analysis_agent.py` | §11.7 | — |
| 1.9 | — | `backend/tools/doc_writers/docx.py` (python-docx, already installed), versioned artifacts plus provenance | 1.10 | An artifact is produced only after a PASS; regenerating gives v2 and keeps v1 | `tests/integration/test_artifact_versioning.py` | §11.6 | xlsx/pptx libraries (ADR) |
| 1.10 | `orchestrator_planner.py` (heuristic kept as the deterministic-first classifier) | `orchestration/graph.py`: planner, **DAG dispatcher** (honours `depends_on`, parallel), Critic per subtask plus final, synthesise; tools via the registry with the user's scope; SSE adapter so `/api/chat/stream` can run the graph behind a flag `ENABLE_GRAPH=true` | 1.6–1.8 | Node-trace assertions pass for a simple lookup, a multi-step task, an ambiguous one (goes to clarify) and an injected mid-task failure. A wiring test spies that the Critic, context manager and injection guard are each invoked | `tests/integration/test_graph_scenarios.py tests/integration/test_wiring.py` | §11.1, 11.5, 11.6 | Load-bearing: call it out at the checkpoint |
| 1.11 | `ChatRequest.messages` (`main.py:74-78`) | Session memory in graph state (server-side, keyed by conversation) | 1.10 | The second turn references the first turn's result | `tests/integration/test_session_memory.py` | §11.2 | — |
| 1.12 | `langsmith_service.create_run_trace` (kept for dev) | Audit events for every model and tool call (`observability/audit.py`) | 0.4 | The trail REQUEST→PLAN→AGENT_DISPATCH→MODEL_CALL→TOOL_CALL→EVALUATION→RESPONSE can be reconstructed for one fixture task; no raw text in the details | `tests/integration/test_audit_trail.py` | §11.19 | ADR-0006 |

**DoD**: all four MVP proof points pass in one demo, plus multi-turn and a working Critic gate. The four proof points:
1. Auto-selection across ≥2 task types.
2. A scanned report turned into a cited `.docx`.
3. A sandbox coding task.
4. A multimodal task.

**Checkpoint**: emit the template, including observed retrieval quality and the Qdrant schema for review. **STOP.**

---

## PHASE 2 — Local inference hardening and parity (AeroMind-specific)

**Context**:
- AeroMind is already local-first: Ollama is the only runtime used by `model_service.py`.
- So Phase 2 is not a hosted→local migration of code. It **proves** zero egress, pins and hashes every model, makes the hardware tiers real, and measures the quality and latency tradeoffs.
- **If C1 = local-only**, the "hosted vs local" diff is replaced by a **tier-vs-tier diff**: `cpu_lite` (this i7) against `gpu_high` (or `apple_full`), on the same fixtures.
- **Zero agent-code changes are allowed in this phase's diff.** Only `config/*.yaml`, `deploy/*`, `router/health.py` and the tests change.

**Preconditions**:
- Phase 1 has passed.
- §12.2 (air-gap vs isolated) is answered.
- ADR-0007 is Accepted.
- Access to the GPU or Mac host is confirmed by the user. This dev host has no GPU, so the GPU rows are **BLOCKED** until that hardware exists.

### 2.1 — Pull, hash and pin every local model, per tier
- **Inputs**: `ollama list` (today: qwen3:4b-instruct-2507, qwen3:4b, qwen3-vl:2b, qwen2.5:3b, qwen2.5-coder:1.5b, gemma4:e4b, nomic-embed-text, plus `*:cloud`).
- **Outputs**:
  - `config/models.yaml`, where every `local.<tier>` entry has a `version` = sha256 of the Ollama manifest digest (`ollama show --modelfile` / `/api/show` digest). The fine-tuned Mistral-7B in `backend/models/` (provider `transformers` or `gguf`) gets the sha256 of the safetensors index plus shards.
  - `deploy/models.lock.json` listing name, tag, digest, size, tier and licence.
  - `scripts/verify_models.py`, which fails if any digest differs.
- **Acceptance**:
  - Every `local` entry answers a smoke prompt.
  - `verify_models.py` exits 0.
  - Tampering one digest in the lock makes it exit non-zero.
- **Test**: `PYTEST tests/integration/test_model_manifest.py -m needs_ollama`.
- **Pitfall**: §11.20 (`ollama:latest` unpinned).
- **Decision**: model licences, which the user reviews (Gemma licence terms, the Qwen licence, and the Mistral fine-tune's provenance mismatch).

### 2.2 — Tier-specific registries and the parity run
- **Inputs**: the Phase 1 fixture suite plus the `eval/` harness.
- **Process**:
  - Run the suite with `AEROMIND_HW_TIER=cpu_lite` on this i7.
  - Run it with `gpu_high` or `apple_full` on the target host.
  - If C1 allows `hf`, also run the `hf` profile with synthetic data only.
- **Output**: `doc/phase2-parity.md`, a diff table of pass rate per task type and per agent, with each regression root-caused (model size, quantization, context length, tool-call format).
- **Acceptance**: the diff table is recorded, and every regression has a written root cause. No regression is "accepted" without a user decision.
- **Test**: `cd eval && python3 harness.py --tier cpu_lite --out results/cpu_lite.json`, then the same with `--tier gpu_high`, then `python3 harness.py --diff results/cpu_lite.json results/gpu_high.json`.
- **Decision**: **user**. Accept the quality tradeoff, use bigger models, or go hybrid.

### 2.3 — Quantization and tool-calling parity
- **Inputs**: the tool-using agents (Coding, Data Analysis, Execution); models qwen3:4b-instruct-2507 (Q4_K_M), qwen2.5-coder:1.5b and qwen2.5:3b, plus the gpu-tier equivalents.
- **Process**:
  - Run each agent's tool-call integration test per tier.
  - Record the tool-calling mode in the registry: `tool_calling: native | json_mode | none`.
  - Where native fails, the router serves the JSON-mode adapter. This is config only, with no agent code change.
- **Acceptance**:
  - Each tool-using agent passes its tool-call test on every tier where it is enabled.
  - Schema validation failures are counted and reported per model.
  - The VLM (qwen3-vl:2b vs the gpu VL model) is re-validated on the OCR/diagram fixtures, with CER and caption accuracy recorded.
- **Test**: `PYTEST tests/integration/test_tool_call_parity.py -m needs_ollama --tier cpu_lite`, and the same for the target tier.
- **Pitfall**: §8.19 (tool-calling parity after quantization is the most likely surprise).
- **Decision**: §12.12 (VLM quantization loss).

### 2.4 — Latency and throughput
- **Inputs**:
  - `bench/b1_per_model.py`. Fix its p95 (`:180`, which actually takes the 4th of 5 samples) and its single-sample warm TTFT (`:151-168`) first, under its own task.
  - `bench/b2_model_switch.py`.
- **Output**: in `doc/01-status/PROJECT_STATE.md` and `doc/phase2-parity.md`, p50/p95 of TTFT and total time per task type and per tier.
- **Labelling**: the i7 numbers are labelled **"dev hardware (i7-1185G7, CPU only), not representative"**. The baseline B1 values (qwen2.5:3b 9.11 tok/s, gemma4:e4b 5.06 tok/s) are carried as the reference.
- **Acceptance**:
  - At least 20 samples per cell.
  - The percentile computation is unit-tested.
  - Cold-load and model-swap times are recorded for the `cpu_lite` hot/cold set.
- **Test**: `python3 bench/b1_per_model.py --samples 20 && PYTEST ../bench/tests/test_percentiles.py`.
- **Decision**: §12.9 (latency ceiling).

### 2.5 — Remove egress paths and add the automated no-egress gate
- **Inputs** (egress paths):
  - The `:cloud` Ollama models.
  - HF downloads in `model_service.py:109-147` (`from_pretrained` with a token), `colpali_retrieval_service.py:118-129` and `download_model.py`.
  - LangSmith (QW9).
  - Frontend Google Fonts and the Web Speech API.
- **Outputs**:
  - **Registry guard**: `local` entries reject `:cloud` tags and non-loopback/non-allowlisted hosts at load time.
  - **Startup guard**: under `ZERO_EGRESS_MODE=true`, the app refuses to start if Ollama's `/api/tags` lists a `:cloud` model that is referenced, and warns about any present.
  - **Offline flags**: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and `ENABLE_COLPALI_DOWNLOAD=false` are enforced under the local profile.
  - **`deploy/zero_egress.env`** (§14.2).
  - **`backend/tests/adversarial/test_no_egress.py`**: an autouse fixture monkeypatches `socket.socket.connect` to refuse non-loopback. Under it, ingestion, retrieval, graph, router and memory all still work.
  - **`deploy/docker-compose.yml`**: an `internal: true` network for Ollama, Qdrant and the worker, plus a separate ingress network for the API only (§11.20).
  - **Voice**: Web Speech is replaced by a local `asr` capability (faster-whisper, ADR) or disabled under zero-egress, with a visible notice.
- **Acceptance**:
  - The no-egress test passes in CI and in the isolated container network.
  - B10 is rewritten to observe a real query cycle, filtered to the app's PIDs, with **no hard-coded verdict**, and it reports 0 external connections.
  - A deliberately added `kimi-k2.5:cloud` registry entry fails validation.
- **Test**: `PYTEST tests/adversarial/test_no_egress.py tests/unit/test_registry_egress_guard.py && python3 ../bench/b10_sovereignty.py --run-query`.
- **Pitfall**: §2 "exclude, don't disable", §11.20.
- **Decision**: §12.2 and §12.11 (offline transfer procedure).

### 2.6 — Health checks and failover wired into `router.get()`
- **Outputs**:
  - `backend/router/health.py`: HEAD then GET with a 2 s timeout, and a circuit breaker (N=3, 60 s cooldown, both from `config/thresholds.yaml`).
  - `router.get()` serves the next-ranked model on the same tag and emits a `MODEL_FAILOVER` audit event.
  - If no candidate is left, it fails loud and honest (`MODEL_FAILURE`). It must never fall back to an unrelated model, as QW1 removed.
- **Acceptance**:
  - **Fault test**: with the primary Ollama model unloaded or its port blocked, the next-ranked model is served and `MODEL_FAILOVER` is audited.
  - With all candidates down, the user sees an honest error, and the Critic never PASSes a degraded output.
- **Test**: `PYTEST tests/integration/test_router_failover.py tests/adversarial/test_fault_injection.py::test_model_timeout`.
- **Pitfall**: §11.5 and §11.6 (health checker built but not wired).

**DoD**:
- Every §8.19 re-validation item is explicitly checked and recorded: tool calls, latency and quality.
- There are zero agent-code changes in the phase diff (`git diff --stat` shows only config, deploy, router/health and tests).

**Human approval**: the quality tradeoff per tier.

**Checkpoint**: emit the template, with the tier-vs-tier (or hosted-vs-local) diff, regressions, no-egress result and latency table. **STOP.**

---

## PHASE 3 — V1: correlation, memory, continuation, audio, connectors, RBAC

**Preconditions**: Phase 2 passed. Revise these tasks against the Phase 2 report before starting.

| ID | Outputs (AeroMind) | Depends | Acceptance criteria | Test (`PYTEST …`) | Pitfall | Decision |
|---|---|---|---|---|---|---|
| 3.1 | `doc/07-decisions/adr/00xx-graph-store.md` based on the measured corpus size; `backend/knowledge/graph_store.py` (NetworkX/SQLite MVP) | 1.4 | Decision recorded with data (node and edge counts from the fixtures and the real corpus) | — | — | ADR (Neo4j or not) |
| 3.2 | `backend/knowledge/entity_resolution.py`; spike comparing ≥2 approaches on 20 hand-labelled pairs (e.g. "Pump 104" ≡ "P-104", "Fuel pump No.1" vs "Fuel pump No.2" ≠) | 3.1 | Report gives actual precision/recall numbers; the regression test **asserts floors** (e.g. P ≥ 0.95, R ≥ 0.80, as agreed) | `tests/unit/test_entity_resolution_benchmark.py` | §11.10 | User accepts the false-positive rate |
| 3.3 | Edge computation at ingestion (`references`, `corroborates`, `contradicts`, `co-occurs-in`, `temporally-adjacent-to`) | 3.2 | Edges persisted with confidence and evidence ids | `tests/integration/test_graph_edges.py` | — | — |
| 3.4 | `backend/agents/correlation_agent.py` producing a `CorrelationResult` | 3.3 | Positive fixture is explained correctly **and** the negative control gives `related:false` | `tests/integration/test_correlation.py` | §11.9 | — |
| 3.5 | Negative-control fixtures (similar equipment names and dates, unrelated events) | 3.4 | A second reviewer confirms they are ambiguous-looking; no keyword special-casing (grep the agent for fixture terms → 0) | `tests/unit/test_no_fixture_special_casing.py` | §11.9 | — |
| 3.6 | `backend/memory/store.py`, `scoping.py` (SQLite dev); `backend/agents/memory_agent.py` wired into the graph | 1.11 | Write in A, read from B → empty or denied, every time; a classification downgrade restricts reads immediately | `tests/adversarial/test_memory_scoping.py` | §11.3 | §12.8, §12.13 |
| 3.7 | Continuation node; `config/thresholds.yaml continuation.relevance_threshold` | 3.6 | Q3 analysis + Q4 dataset present → proposes it; no next step → silent; both tested | `tests/integration/test_continuation.py` | — | — |
| 3.8 | `backend/ingestion/extractors/audio.py` (faster-whisper through the `asr` capability) | 0.4 | Fixture transcript within the WER tolerance; `speaker_turn` blocks timed | `tests/unit/test_audio_extractor.py` | — | ASR ADR |
| 3.9 | `backend/connectors/base.py` + the first connector | 1.4 | Reads a real test instance; units carry the correct `workspace_id` **and** ACL fields (field-level asserts); a write action does not run without approval | `tests/integration/test_connector.py` | §11.12 | §12.10 |
| 3.10 | `backend/security/auth.py` (`IdentityProvider` + real binding) | user | **BLOCKED until the IdP is decided.** Never build against a placeholder and call it done | `tests/adversarial/test_privilege_escalation.py` | §11.15 | §12.1 |
| 3.11 | `eval/metrics.py`: correlation relevance, follow-up relevance | 3.4, 3.7 | Metrics computed on the fixtures and reported | `cd eval && python3 harness.py --metrics correlation,followup` | — | — |
| 3.12 | `backend/retrieval/{reranker,hybrid}.py` (bge-reranker-v2-m3; vector + keyword + graph; ColPali optional as a 4th signal on gpu/apple tiers) | 1.5 | Retrieval quality on the fixtures ≥ Phase 1 baseline (numbers recorded) | `tests/integration/test_hybrid_retrieval.py` | — | Reranker ADR |

**DoD**: cross-modal correlation works on real data with a scored explanation, and continuation relevance is above the threshold.

**Checkpoint**: emit the template. **STOP.**

---

## PHASE 4 — Hardening

**Preconditions**: Phase 3 passed; RBAC is live.

| ID | Outputs | Acceptance criteria | Test |
|---|---|---|---|
| 4.1a | Egress re-test including connector paths, inside the isolated environment | **100% of attempted egress blocked**; one success is a release blocker | `PYTEST tests/adversarial/test_no_egress.py` in compose |
| 4.1b | Prompt-injection suite: PDF, CSV cell, HTML, OCR text, plus SSE control-tag spoofing (a model or document emitting `[DONE]` or `[ERROR:`) and markdown image exfiltration | Real task completed; injected action not performed; `SANITIZED_BOUNDARY` audited; write/execute from document content requires approval | `PYTEST tests/adversarial/test_prompt_injection.py` |
| 4.1c | Privilege escalation through agent chaining | Denial logged; honest explanation; no partial result | `PYTEST tests/adversarial/test_privilege_escalation.py` |
| 4.2 | Fault injection: model timeout, connector credential expiry, Critic over budget, corrupted upload, Qdrant down (including an embedded lock held), graph down | Each produces exactly the documented recovery | `PYTEST tests/adversarial/test_fault_injection.py` |
| 4.3 | Load and latency on production-class hardware per tier | p50/p95/p99 recorded under concurrency | `python3 bench/load.py --concurrency 4,8,16` |
| 4.4 | OpenTelemetry to a local collector, dashboards, alerts (ADR-0006) | Live traces are visible; an alert fires on an injected failure | manual + `PYTEST tests/integration/test_otel_export.py` |
| 4.5 | Revisit video and voice with usage data | Decision recorded | — |
| 4.6 | Security review document | Signed off | — |

The red-team list for 4.1–4.2 also includes:
- Path traversal through the workspace id and the upload path.
- Zip Slip on restore, including links.
- XSS in the UI.
- Secret scrubbing.

All of these go in `tests/adversarial/test_red_team.py` and `test_hardening_audit.py`.

**Human approval**: unconditional go/no-go for real data.

**Checkpoint**: emit the template. **STOP.**

---

## PHASE 5 — Production rollout

**Preconditions**: Phase 4 passed with a recorded human "go".

| ID | Outputs | Acceptance criteria |
|---|---|---|
| 5.1 | Capacity plan per tier (`gpu_multi` vLLM allocation) from the Phase 4 data | The plan matches measured load |
| 5.2 | `backend/agents/optimization_agent.py`: weekly batch over audit, eval and feedback, writing to `proposals/` only | ≥1 proposal reviewed and accepted or rejected by a human; a test proves the queue is never bypassed (`PYTEST tests/adversarial/test_optimization_queue_only.py`) |
| 5.3 | Additional connectors, driven by pilot usage | Each passes the 3.9 criteria |
| 5.4 | Single-department pilot (aviation MRO kit if C2 keeps the domain) against a manual baseline | Real before/after timings; zero air-gap violations |
| 5.5 | Model-registry refresh process: onboard → eval → compare → promote/reject within one sprint | Executed once against a real new model release |
| 5.6 | Quarterly architecture review | Held on schedule |

These are ongoing process commitments, so don't mark them done and stop. Each department rollout gets its own mini-checkpoint.
