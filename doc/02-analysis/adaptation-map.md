# Adaptation Map: AeroMind 2.0 against PROJECT-IMPLEMENTATION-PLAN

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.


**Stage 3 deliverable** (PLAN §4.1.3–§4.1.6). Status: **draft, awaiting user decisions on every CONFLICTS row.** Date: 2026-11-03.

**How to read the citations**
- `path:line` refers to this repository.
- `PLAN §x.y` refers to `PROJECT-IMPLEMENTATION-PLAN.md`. The repo-root copy is byte-identical to `/home/darkwing/Desktop/workbench/…`, checked with `diff -q`.
- `§11.n` refers to pitfall *n* in PLAN §11.

**Statuses** (PLAN §4.1.3):

| Status | Meaning |
|---|---|
| EXISTS | Already present; the note says how it differs from the contract. |
| PARTIAL | Present, but breaks a PLAN §2 principle. |
| MISSING | Not present at all. |
| CONFLICTS | AeroMind made a choice that can't coexist with the plan. Each one needs a user decision or an ADR (draft ADRs live in `doc/07-decisions/adr/`, status *Proposed*). |

**Baseline, run this session** (details in `doc/01-status/PROJECT_STATE.md`):
- Command: `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python3 -B -m pytest -p no:cacheprovider -rA -q`, run in an isolated scratch copy of `backend/` with no `.env`.
- Result: **8 passed, 2 failed**. `test_model.py::test` needs network access to Hugging Face. `test_multimodal_pipeline.py::test_pipeline` is an async test and no async plugin is installed.

---

## 1. Mapping table

### 1a. Subsystems (PLAN §8.0–§8.19)

| # | Component | Status | Where in AeroMind | Difference from the contract / principle broken | Pitfall | Action |
|---|---|---|---|---|---|---|
| 8.0 | Target directory layout | MISSING | Every module sits flat in `backend/*.py`; the frontend is in `frontend/src/` | One responsibility per file isn't followed (PLAN §3.6). The agents are classes inside `backend/agent_orchestrator.py:31-459`. There are no `agents/`, `router/`, `orchestration/`, `config/` or `tests/` folders | — | Add packages under `backend/` and `config/` at the repo root (§4). Existing modules stay as adapters |
| 8.1a | Main Agent: intent classification | PARTIAL | `backend/orchestrator_planner.py:137-212` (`_heuristic_dag_fallback`) | It is keyword-only and has no `clarify` outcome. Its output is a template name, not a `task_type`. Its docstring says an SLM plans (`:1-9`, `:224-228`), but the code returns the heuristic (`:229-230`) | §11.1 | Wrap it as the deterministic first stage of `classify_intent` and add the model fallback plus `clarify` |
| 8.1b | Main Agent: planner / DAG | PARTIAL | `backend/orchestrator_planner.py:18-134` (`DEFAULT_DAG_TEMPLATES`) | It always uses one of 4 fixed templates. There are no `SubTask`/`TaskPlan` records (PLAN §7.9) and no plan-depth cap | §11.6 | Reuse the templates as planner seeds and emit a `TaskPlan` |
| 8.1c | Main Agent: dispatcher that actually runs the DAG | PARTIAL | `backend/agent_orchestrator.py:205-270` | The DAG is sent to the UI (`:192`) but never executed. Three hard-coded booleans pick the workers (`:209-211`) and `depends_on` is ignored. `asyncio.gather` gives real parallelism, but only for those three workers (`:266-270`) | §11.6 | Build a DAG executor that honours `depends_on` (PLAN §8.1 node 4) |
| 8.1d | Orchestration state (`WorkbenchState`) | MISSING | — | State is local variables inside one generator (`agent_orchestrator.py:150-456`). There's no TypedDict, no reducers and nothing serializable | §11.1, §11.2 | Add `orchestration/state.py` (PLAN §7.3) |
| 8.1e | Checkpointer, pause/resume, cancel | MISSING | — | No `task_id`, no checkpoint, no cancel route. The only cancel is the client closing the request (`frontend/src/hooks/useChat.js:30-34`) | §11.11 | LangGraph checkpointer (SQLite) keyed by a unique `task_id` (ADR-0003) |
| 8.1f | `approval_gate` (interrupt) | MISSING | — | No action ever needs approval | §11.11 | LangGraph `interrupt` plus `/api/tasks/{id}/approve` |
| 8.1g | `synthesize` node | PARTIAL | `backend/agent_orchestrator.py:326-404` | It joins context blocks as raw text (`:340-381`) and streams one model call (`:395-401`). It has no evidence refs and no per-claim citations. Context is cut by characters (`:356`, `:379`) | §11.4 | Synthesis over `AgentMessage[]` with `evidence_refs` |
| 8.1h | `continuation` node | MISSING | — | — | — | V1 (Phase 3.7) |
| 8.2a | Model Router (capability tag, then model) | PARTIAL | `backend/config.py:25-32` (`AGENT_MODEL_MAP`); `backend/model_service.py:256-265` | It routes by agent *role* (`orchestrator`, `math`, `vision_table`…), not by capability tag. Model names come from env vars, not `config/models.yaml`. There's no `version`, `vram_gb` or `rank`, and no `NoModelForCapability`: unknown roles silently become `synthesis` (`model_service.py:258-261`) | §11.5 | `router/router.py` per PLAN §7.2, seeded from `AGENT_MODEL_MAP` |
| 8.2b | Fail loud when there's no model | PARTIAL (breaks principle 8) | `backend/model_service.py:385-390` | On an Ollama 404 it silently swaps to `OLLAMA_MODEL`. Four of the six roles configured in `backend/.env` (qwen2.5:7b-instruct, qwen2.5-math:7b, deepseek-r1-distill-qwen:7b, qwen2.5:3b-instruct) aren't installed in the local Ollama (`ollama list`, checked this session), so they all quietly run on qwen2.5:3b. Errors come back as ordinary tokens (`:400`, `:418-425`) | §11.5 | QW1: fail-closed resolution with a `MODEL_FAILURE` event (matches `bench/FIX_PROPOSALS.md:8-51`) |
| 8.2c | Capability detection (vision) | PARTIAL | `backend/model_service.py:357`, `:389` | It decides whether a model "supports vision" by substring-matching the model name. The synthesis model is qwen2.5:3b, which is text-only, so the base64 page images attached at `agent_orchestrator.py:384-399` are dropped and no vision model ever runs | §11.6 | Declare `vision` capability in the registry |
| 8.2d | Health check, failover, circuit breaker | PARTIAL | `backend/model_service.py:75-86` (`_load_ollama`) | There's one startup GET with no timeout. It ignores `OLLAMA_HOST` and hard-codes `127.0.0.1:11434` (`:79`). There's no per-call health check, failover or breaker | §11.6 | `router/health.py` wired into `router.get()` (Phase 2.6) |
| 8.2e | Model onboarding catalogue | MISSING | `bench/b1_per_model.py` measures latency and RSS only | There's no `ModelOnboardingSpec` | — | Phase 2; feed B1 numbers into `latency_profile` (ADR-0005) |
| 8.2f | Model-call audit (tag asked for vs. model served) | MISSING | Debug `print` only (`backend/model_service.py:268`) | — | — | Phase 1.12 |
| 8.2g | Inference efficiency | PARTIAL | `backend/model_service.py:380-396` | Each Ollama call runs a **full non-streamed generation** (`client.post` with the streaming payload, `:381-384`) and **then a second, streamed one** (`:392-396`), so it does the work twice. `num_ctx` is hard-coded to 2048 (`:373`) while `N_CTX`=8192 (`config.py:21`), so long prompts are silently truncated | — | QW2 |
| 8.3a | Upload flow: path validation | PARTIAL / unsafe | `backend/universal_ingestion_service.py:95-106`; `backend/main.py:166-176` | The client's filename is joined straight onto the target directory (`self.pdf_dir / filename`, `:100`; `temp_uploads / f"{doc_id}_{file.filename}"`, `main.py:172`), with neither an allowlist nor a blocklist, so the write can escape the upload directory. There are no size limits | §11.16 | QW3: resolve the real path and require it to stay under the upload root |
| 8.3b | Malware / malformed-file scan | MISSING | — | Archives are unpacked with no size, count or depth limits, and nested ZIPs are processed recursively without a bound (`backend/ingestion_adapter.py:253-264`). `zipfile.extractall` strips `..`, but nothing guards against zip bombs | — | `ingestion/scanner.py` (Phase 1.4) |
| 8.3c | Modality detection | PARTIAL | `backend/ingestion_adapter.py:56-76` | Detection is by file extension only, with no MIME sniffing. Unknown types are sent to the text extractor (`:74-76`). There's no check for scanned vs. text PDFs; OCR only triggers when a page has fewer than 30 characters (`backend/visual_rag_service.py:114`) | — | `ingestion/detectors.py` |
| 8.3d | Extractors → `Document` / `EvidenceUnit` | CONFLICTS (C3) | `backend/ingestion_adapter.py:35-312`; `backend/universal_ingestion_service.py:122-186` | Every format is turned into a **PDF** for the page-image viewer, which destroys structure. CSV keeps 15 rows (`ingestion_adapter.py:180`). XLSX keeps 10 rows (`:145`), 8 columns and 30 characters per cell (`:417-421`). Images get placeholder text (`:241`). DOCX via reportlab doesn't escape markup (`:366`). There is no `EvidenceUnit`, and extractors print errors instead of returning a FAILED `Document` | §11.4, §11.14 | ADR-0004 / C3: keep the PDF path for viewing and add native EvidenceUnit extractors alongside it |
| 8.3e | OCR | PARTIAL | `backend/visual_rag_service.py:113-125` (RapidOCR fallback) | RapidOCR is real, but it isn't in `requirements.txt`, so it only works with the system Python. There's no confidence score and no `uncertain` tag | — | Keep it; wrap it as `tools/ocr_extract.py` and emit OCR confidence |
| 8.3f | ASR / audio, video, HTML | MISSING | — | The browser Web Speech API is used for voice input (`frontend/src/components/VoiceController.jsx:20-31`), which sends audio to a cloud service | — | Phase 3.8 (local Whisper). Video and HTML are open questions §12.3 and §12.12 |
| 8.3g | Structure-aware chunker | MISSING | Each page is one unit, cut to 4000 characters (`backend/visual_rag_service.py:155`) | No overlap, no heading path | §11.19 | `ingestion/chunker.py` |
| 8.3h | Ingestion queue / background jobs | PARTIAL | `backend/main.py:44-47` (startup index task), `:110-117` (`BackgroundTasks` model load) | Uploads run indexing inside the request (`main.py:204`, `universal_ingestion_service.py:129`). There's no `BackgroundJob`, progress or cancel | §11.11 | `ingestion/queue.py` thread pool (PLAN §8.3) |
| 8.3i | Stamping `workspace_id` + `classification_level` | MISSING | — | There's no workspace concept anywhere. `session_id` only prefixes `doc_id` (`backend/main.py:166-168`) | §11.3, §11.12 | Phase 1.4 |
| 8.4a | Vector store (Qdrant) | PARTIAL | `backend/colpali_retrieval_service.py:52-109`, `:178-251` | Qdrant runs embedded on disk, which is fine for an MVP. There's one collection **per document** (`:87`), point id = page number (`:226`), and the payload has no `workspace_id`, `classification_level`, `acls` or `evidence_tag`. If the disk lock is held it silently falls back to `:memory:` (`:75-77`) | §11.3, §11.13 | ADR-0004: one collection per vector space, workspace payload index, deterministic point ids |
| 8.4b | Embedding model | CONFLICTS (C4) + PARTIAL | `backend/colpali_retrieval_service.py:111-176` | ColQwen2 only loads when `ENABLE_COLPALI_DOWNLOAD=true` (`:118`), which is off by default. Otherwise vectors are random noise seeded by Python's per-process salted `hash()` (`:142`, `:154`, `:169`). **Checked this session: the same query run in three processes returned three different top-5 page sets.** In practice, retrieval is random | §11.8 | QW6: real text embeddings through the router's `embedding` tag. ColPali becomes an opt-in second vector space (C4) |
| 8.4c | Graph store | MISSING | — | — | — | Phase 3.1 (ADR) |
| 8.4d | Entity resolution | MISSING | — | — | §11.10 | Phase 3.2 spike. Equipment IDs are a key vertical feature |
| 8.4e | Relationship edges | MISSING | — | — | — | Phase 3.3 |
| 8.5a | Retrieval: vector + keyword + graph | PARTIAL | `backend/visual_rag_service.py:200-283`; `backend/universal_ingestion_service.py:193-253` | Only the (fake) vector search runs. The keyword fallback (`visual_rag_service.py:237-252`) only runs if Qdrant returns nothing, which never happens because `query_points` always returns top-k. Table search needs **the whole query** to appear inside a single cell (`universal_ingestion_service.py:232-237`), so in practice it never matches | §11.3 | Phase 1.5 / 3.12 |
| 8.5b | Reranker | MISSING | Planned in `MIGRATION.md:88` | — | — | Phase 3.12 (`bge-reranker-v2-m3`, which MIGRATION.md already suggests) |
| 8.5c | Retrieval Agent (enough evidence? reformulate up to 2 times) | MISSING | — | There's no "insufficient evidence" path. The synthesis model always answers | — | Phase 1.7 |
| 8.6 | Context management (token budget) | PARTIAL | `backend/agent_orchestrator.py:356`, `:379`; `backend/model_service.py:162`, `:173` | Budgets are counted in characters (3000 per page, 400 per row, 400 per earlier turn) instead of tokens. There's no `[TRUNCATED]` marker. The real limit is `num_ctx` 2048 (`model_service.py:373`) | — | `retrieval/context_manager.py` |
| 8.7 | Shared prompt assembly | CONFLICTS (C7) + PARTIAL | `backend/model_service.py:152-218` | There's a single Alpaca-style template. Document text goes **inside `### Instruction:`** (`:206-218`) with no "untrusted evidence" boundary. Prompts are inline strings, not versioned YAML. Earlier assistant turns come from the client and are trusted (`backend/main.py:74-78`) | — | `orchestration/prompts.py` with per-model prompt profiles (C7) |
| 8.8a | Tool contract + registry | MISSING | — | Workers are called directly (`agent_orchestrator.py:217-263`) | §11.6 | `tools/registry.py` (PLAN §7.6) |
| 8.8b | Sandboxed Python execution | MISSING | — | Docker is available on the dev machine | §11.7, §11.19 | Phase 0.5 |
| 8.8c | Deterministic tools | EXISTS (needs fixing) | `backend/agent_orchestrator.py:31-143` (`AvionicsMathEngine`) | This is correctly deterministic (principle 3), but **it makes numbers up**: with no inputs it assumes 2800 kg of fuel and 58 kg/min burn (`:92-98`). The altitude regex reads "5 minutes" as 5 m (`:73`). Both reproduced this session | §11.5 | QW5: refuse when an input is missing; register it as `tools/aero_calc.py` |
| 8.8d | Document writers (docx/xlsx/pptx/chart) | PARTIAL | reportlab PDF builders `backend/ingestion_adapter.py:331-459` (ingestion only) | No artifact writers, versioning or provenance. reportlab isn't in `requirements.txt` | — | Phase 1.9 |
| 8.8e | Exclude dev-only `web_fetch` from production | MISSING (no tools at all) | — | — | — | With the registry |
| 8.9 | Multimodal Understanding Agent | PARTIAL | `backend/visual_rag_service.py:82-198`; "visual" worker in `agent_orchestrator.py:217-227` | It does page rendering, diagram heuristics (images or more than 10 vector drawings, `:128-130`), schematic keyword flags (`:134-151`) and OCR. **No vision-language model is ever called** (see 8.2c). The status messages it sends claim it "Extracted layout coordinates" (`agent_orchestrator.py:280`), which isn't true | §11.4 | Phase 1.6; mark unavailable steps as `pending_capabilities` |
| 8.10a | Critic: deterministic layer | MISSING in practice | "Safety validator" `backend/agent_orchestrator.py:406-427` | The validator does nothing: its "thought" is a fixed string claiming "Verified grounding against source material" (`:414`) | §11.5, §11.6 | Phase 1.10 (also `bench/FIX_PROPOSALS.md:53-101`) |
| 8.10b | Critic: model-based pass | MISSING | `VERIFICATION_MODEL` is configured (`backend/config.py:30`) but never called | — | — | Phase 1.10, using a different model family from the producer |
| 8.10c | Evaluation scorecard | PARTIAL / misleading | `backend/evaluation_service.py:18-97`; `frontend/src/components/EvaluationScorecard.jsx:17-18` | Faithfulness is floored at 78 (`:50`), so an empty answer still scores **78.6%** confidence and a nonsense answer scores 78% faithfulness (checked this session). Non-emergency queries always get `VERIFIED_SAFE` (`:70`). The UI fills in 85/95 when a value is missing | §11.5 | QW4: label it "heuristic", remove the floors, never show it as verification |
| 8.11 | Correlation Agent | MISSING | — | — | §11.9 | Phase 3.4–3.5 |
| 8.12a | Session memory (multi-turn) | PARTIAL | The client sends the full history (`frontend/src/hooks/useChat.js:73-79`); the server keeps the last 6 turns (`backend/config.py:83`, `backend/model_service.py:162`) | No server-side memory, and earlier turns can be tampered with by the client | — | Phase 1.11 |
| 8.12b | Workspace / long-term memory, `MemoryEntry` | MISSING | — | — | — | Phase 3.6 |
| 8.12c | Continuation proposals | MISSING | — | — | — | Phase 3.7 |
| 8.13a | Authentication (IdP abstraction) | MISSING | No auth on any route in `backend/main.py` | Open question §12.1 | §11.15 | Phase 3.10 (blocked); mock IdP behind a dev flag at Phase 1 |
| 8.13b | Authorization / RBAC / workspace authZ | MISSING | `/api/documents/list` returns every document to every caller (`backend/main.py:122-124`) | — | §11.3 | Phase 1 (mock) / 3.10 |
| 8.13c | Gateway, rate limiter, CORS | MISSING / unsafe | `backend/main.py:59-65`: `allow_origins=["*"]` together with `allow_credentials=True` | — | — | `security/gateway.py`, `security/rate_limiter.py` |
| 8.13d | Prompt-injection guard | MISSING | See 8.7 | — | — | Phase 1.4, 4.1b |
| 8.13e | Egress guard | PARTIAL | Ollama is local-first (`backend/config.py:18-20`). Outbound paths: LangSmith (`backend/langsmith_service.py:89-98`), HF Hub (`backend/model_service.py:118-144`, `download_model.py`), ColQwen2 download (`colpali_retrieval_service.py:124-129`), Google Fonts (`frontend/index.html:7-8`), Web Speech (`VoiceController.jsx:20-31`), Markdown images loading any URL (`frontend/src/components/MessageBubble.jsx:117-176`), and the `*:cloud` models in the local Ollama (`ollama list`). `bench/b10_sovereignty.py:176` hard-codes `air_gapped: True` | §11.20 | Phase 2.5; QW9; reject `:cloud` tags when the registry loads |
| 8.13f | XSS / output escaping | EXISTS (mostly) | `react-markdown` without `rehype-raw` (`frontend/src/components/MessageBubble.jsx:278-283`); no `dangerouslySetInnerHTML` anywhere in `frontend/src` | The gaps are outside images and unchecked `image_url` values (`frontend/src/components/VisualDiagramCard.jsx:52`, `:141`) | §11.17 | Allowlist `img`/`a`; add a CSP header |
| 8.13g | Spoofable SSE control frames | PARTIAL | Control frames like `[AGENT_STATUS:…]`, `[DONE]` and `[ERROR:…]` travel in the same `data:` channel as tokens (`backend/agent_orchestrator.py:185…441`; `backend/main.py:339-346`; parsed at `frontend/src/hooks/useChat.js:106-257`) | Model output or document text can forge a control frame. The JSON is built with f-strings (`agent_orchestrator.py:185`, `:328`, `:417`) | — | Move to typed SSE `event:` frames (Phase 1, compatibility mode during the transition) |
| 8.14a | Audit events (`AuditEvent`) | MISSING | — | — | — | `observability/audit.py` (Phase 0.4) |
| 8.14b | Tracing / observability | CONFLICTS (C5) + PARTIAL | `backend/langsmith_service.py:65-102` (local JSON trace + cloud upload); `backend/data_repository/traces/` (28 traces committed to git) | Traces contain the raw query and the full answer (`:71-75`), which PLAN §7.8 forbids. `/api/prompts/inspect` serves them to anyone, with no auth (`backend/main.py:298-304`) | — | ADR-0006 |
| 8.14c | Model / agent versioning | MISSING | `backend/models/export_metadata.json` exists, but nothing hashes the weights | — | — | ADR-0005 `version: sha256` |
| 8.15a | API: health | EXISTS | `backend/main.py:83-94` (`/api/health`) | It doesn't report `env`, `zero_egress` or capabilities | — | Extend it (add `hardware_tier`, ADR-0007) |
| 8.15b | API: tasks / stream / cancel / approve / feedback | PARTIAL | `POST /api/chat/stream` (`backend/main.py:309-356`) | Synchronous SSE only. There's no `task_id`, cancel, approve or feedback route | §11.11 | Add `/api/tasks…` and keep `/api/chat/stream` (§7) |
| 8.15c | API: ingest / jobs | PARTIAL | `/api/documents/upload` (`:135-152`), `/api/documents/session-upload` (`:155-227`), `/api/pdf/upload/{id}` (`:288-293`) | Three overlapping upload routes, all synchronous, with no job id | — | Put a job layer behind them |
| 8.15d | API: artifacts, memory, audit, ui/* | MISSING | Page image and thumbnail routes exist (`:230-261`) | — | — | Phase 1–3 |
| 8.15e | Every route goes through the gateway | MISSING | — | — | §11.15 | With 8.13 |
| 8.16a | Frontend: streaming chat + citations | PARTIAL | `frontend/src/hooks/useChat.js:69-298`; `frontend/src/components/MessageBubble.jsx` | It streams. Citations are a single "last page wins" number (`useChat.js:218-233`), not taken from evidence refs. Known bugs: sending does nothing until a document is selected (`useChat.js:28`), and the stream can get stuck in "streaming" (`:296-298`) | — | QW10; inline citations from `evidence_refs` |
| 8.16b | Agent activity view | EXISTS | `frontend/src/components/AgentActivityHUD.jsx` | It shows the plan, not what actually ran (see 8.1c) | — | Feed it real node events |
| 8.16c | Artifact panel, task history, approvals, feedback | MISSING | `PdfViewer.jsx` is the only side panel | — | — | Phase 1+ |
| 8.16d | Upload with ingestion progress | PARTIAL | `frontend/src/components/UniversalDocumentManager.jsx:52-72` | Only a spinner. Category, name and description options are never shown (`:21-23`). The "RAG INDEXED" badge is always shown (`:234-236`) | — | With 8.3h |
| 8.17a | Relational store | MISSING | `backend/data_repository/document_registry.json` (`universal_ingestion_service.py:31`, `:45-50`) | A JSON file rewritten on every change, not safe under concurrent writes | — | SQLite at MVP (ADR) |
| 8.17b | Object store | EXISTS | `backend/pdfs/`, `backend/data_repository/{uploads,page_images,adapter_scratch}` (`backend/config.py:75-80`) | No per-workspace layout. The data is committed to git (128 files) | — | Keep the local filesystem at MVP; untrack the data (QW8) |
| 8.18 | Disaster recovery / snapshots | MISSING | Planned in `MIGRATION.md:108` | — | §11.18 | Phase 4+ |
| 8.19a | Local inference | EXISTS | Ollama by default (`backend/config.py:18-20`); llama.cpp/GGUF (`model_service.py:88-107`); transformers (`:109-147`) | Already local-first, as the plan wants. No weight hashes. `ollama:latest`/models aren't pinned. HF fallback downloads with `trust_remote_code=True` (`:118-144`) | §11.20 | Keep it; add hashes (ADR-0005) |
| 8.19b | Hardware awareness / VRAM sizing | MISSING | Planned in `MIGRATION.md:66-72`; benchmark data in `bench/results/b1_per_model_AS_IS.json` | The dev machine has no GPU (an Iris Xe integrated GPU, 31 GiB RAM, checked this session) and nothing adjusts for that | — | QW11 / ADR-0007 device-aware tiers |

### 1b. Data contracts (PLAN §7) and profiles (§5.3)

| Contract | Status | Where | Difference | Pitfall | Action |
|---|---|---|---|---|---|
| §7.1 `config/models.yaml` | MISSING (PARTIAL equivalent) | `backend/config.py:25-32`, `backend/.env` | Env-var role map; no capabilities/version/vram | §11.20 | Phase 0.4 + ADR-0005 extension + ADR-0007 tiers |
| §7.2 `ModelRouter` | PARTIAL | `backend/model_service.py:256-265` | See 8.2a | §11.5 | Phase 0.4 |
| §7.3 `WorkbenchState` | MISSING | — | — | §11.1–2 | Phase 0.4 |
| §7.4 `AgentMessage` | MISSING | ad-hoc SSE JSON payloads (`agent_orchestrator.py:194-202`, `:276-283`) | No evidence_refs/confidence | — | Phase 0.4 |
| §7.5 `EvidenceUnit`/`Document` | MISSING (CONFLICTS C3) | closest: `index_meta.json` page dicts (`visual_rag_service.py:153-166`) and adapter "package" dicts (`ingestion_adapter.py:41-55`) | No workspace, provenance, location beyond page, blocks | §11.4, §11.14 | Phase 0.4 |
| §7.6 `ToolSpec`/registry | MISSING | — | — | §11.6 | Phase 0.4 |
| §7.7 Identity/permissions | MISSING | — | — | §11.15 | Phase 1 (mock) / 3.10 |
| §7.8 `AuditEvent` | MISSING | traces are not audit events (`langsmith_service.py:66-78`) | Raw text in traces | — | Phase 0.4 |
| §7.9 `SubTask`/`TaskPlan`/`EvaluationReport` | PARTIAL | template dicts (`orchestrator_planner.py:18-134`); eval dict (`evaluation_service.py:86-97`) | No status/result per subtask; eval has no `verdict`/`claim_checks` | §11.5 | Phase 0.4 / 1.10 |
| §7.10 Correlation / entity | MISSING | — | — | §11.9–10 | Phase 3 |
| §7.11 `MemoryEntry` | MISSING | — | — | — | Phase 3.6 |
| §7.12 `ContextBudget` | MISSING | char caps | — | — | Phase 1 |
| §7.13 Connector interface | MISSING | — | — | §11.12 | Phase 3.9 |
| §7.14 `BackgroundJob` | MISSING | — | — | §11.11 | Phase 1 |
| §5.3 Dual-profile (`hf` dev ⇄ `local` prod) | CONFLICTS (C1) | `conversation.md:49`, `backend/config.py:18` | Project is local-only by user directive | — | ADR-0001, awaiting decision |
| — Product scope / identity | CONFLICTS (C2) | `README.md:3`, `backend/pdf_service.py:19-32`, `backend/model_service.py:159`, `frontend/src/components/ChatPanel.jsx:92-97` | Aviation/defence-specific vs PLAN §1 general enterprise | — | ADR-0001 note, awaiting decision |
| — Python environment / lockfile | CONFLICTS (C8) | `backend/requirements.txt:8-28` (`>=` pins); `backend/venv` lacks qdrant_client/colpali_engine/reportlab/pytest | PLAN §13 "pin exact versions" | §11.20 | ADR (with 0.3), awaiting decision |

**Row counts.** These are the Status column of §1a and §1b, counted by script: 89 rows. A row with two statuses (for example "CONFLICTS + PARTIAL") counts under both.

| Status | Rows |
|---|---|
| EXISTS | 6 |
| PARTIAL | 32 |
| MISSING | 48 |
| CONFLICTS | 8 |

C6 (orchestrator substrate) appears in §2, on top of the 8.1 PARTIAL rows.

---

## 2. CONFLICTS — awaiting user decision

Each item below quotes both sides, recommends, and points to a draft ADR (status **Proposed**). **None is resolved. All are awaiting user decision** (PLAN §3.2, §12.14).

### C1 — Local-only vs dual-profile (hosted dev + local prod)
- **Project:** "*MAKE SURE THE ENTIRE SYSTEM SHOULD BE LOCALLY HOSTED, WITH NO ONLINE CONNECTION!*" (`conversation.md:49`); "*no external identity provider, given air-gap requirement*" (`MIGRATION.md:192`).
- **Plan:** "`WORKBENCH_ENV=hf` (or `dev`): hosted endpoints for fast iteration… `WORKBENCH_ENV=local` … required baseline" (PLAN §5.3); M2 "against hosted models" (PLAN §9 milestones).
- **Recommendation:** local-only. Keep the `hf` block schema-valid but **empty** (or absent), so the plan's invariant "every `hf` capability present in `local`" trivially holds, and run M2/M3 on local models (with `cpu_lite`/`gpu_*` tiers, ADR-0007). This also answers half of §12.2.
- **ADR:** `doc/07-decisions/adr/0001-canonical-source-of-truth.md`.

### C2 — Aviation/defence identity vs general enterprise platform
- **Project:** "*AeroMind 2.0 is a production-grade, local-first defense intelligence platform designed for military aviation…*" (`README.md:3`). The MiG-21 is hard-coded in `backend/pdf_service.py:19-32` and `backend/universal_ingestion_service.py:52-72`. Prompts branch on fighter names in `backend/model_service.py:159` and `backend/agent_orchestrator.py:407`. The UI suggests aviation questions in `frontend/src/components/ChatPanel.jsx:92-97`.
- **Plan:** "*An internal AI platform … gives employees a ChatGPT/Claude-grade experience*" across refineries, PSUs, defence, government, finance and healthcare (PLAN §1, §1.1).
- **Project's own direction:** "*clean, trustworthy tool — not an intimidating 'tactical system'*" (`FRONTEND.md:4`), and a move "*to a general-purpose, locally-hosted, multi-document … platform*" (`MIGRATION.md:3`).
- **Recommendation:** generalize the core. Move the aviation content (the aircraft registry, fighter prompt branch, math engine, MiG-21 suggestions) into an **"Aviation MRO" starter kit** (`kits/aviation/`) rather than deleting it. Keep the product name unless the user says otherwise.
- **ADR:** recorded as a scope note in `0001-canonical-source-of-truth.md`.

### C3 — Normalize-everything-to-PDF vs structure-preserving `EvidenceUnit`
- **Project:** "*Normalizes arbitrary file types (DOCX, XLSX, CSV, Images, ZIP) into standardized PDF/image structures for ColPali Visual RAG*" (`backend/ingestion_adapter.py:6-8`).
- **Plan:** "*Every extractor … emits this. It preserves structure (tables stay tables, timestamps stay timestamps)*" (PLAN §7.5).
- **Recommendation:** **both paths.** The native extractors produce `EvidenceUnit`s, and those are what search and citations use. The PDF rendering stays as the **viewer** path, so page-image citations and the PDF viewer keep working. Record `media_ref` and `location.page_number` on each unit so it links back to the rendered page.
- **ADR:** `doc/07-decisions/adr/0004-vector-layer-qdrant-hybrid.md` (ingestion section).

### C4 — ColPali page multi-vectors vs chunk text embeddings (bge-m3)
- **Project:** "*ColPali late-interaction multi-vector scoring via Qdrant index*" (`backend/visual_rag_service.py:10`). Collection config: `MultiVectorConfig(MAX_SIM)` (`backend/colpali_retrieval_service.py:97-104`).
- **Plan:** "*COSINE distance, real embedding model via router `embedding` capability*", with a payload keyed by `unit_id` (PLAN §8.4).
- **In practice:** ColPali is never loaded, so today's vectors are random (8.4b).
- **Recommendation:** **hybrid.** Make the primary vector space chunk-level text embeddings (`embedding` tag). Keep ColPali as an optional second named vector, turned on only for hardware tiers that can run it (`gpu_high`, `apple_full`; ADR-0007). Fusion and reranking come in Phase 3.12.
- **Lock-in warning:** the embedding model must be the same on every hardware tier. Changing it later means re-ingesting everything (§12.7).
- **ADR:** `doc/07-decisions/adr/0004-vector-layer-qdrant-hybrid.md`.

### C5 — LangSmith cloud tracing vs zero egress
- **Project:** "*Full LangSmith Cloud integration (`LANGCHAIN_TRACING_V2=true`)*" (`README.md:27`); upload at `backend/langsmith_service.py:89-98`; `LANGSMITH_TRACING: bool = True` (`backend/config.py:35`).
- **Plan:** "*No data leaves company infrastructure in production — provable*" (PLAN §1.4); "*OpenTelemetry to a local-only collector*" (PLAN §8.14).
- **Project's own plan:** "*Replace/supplement LangSmith with a fully local observability stack*" (`MIGRATION.md:142`).
- **Recommendation:** keep the local JSON traces, converted into `AuditEvent` JSONL with no raw text. Remove the cloud client from the `local` profile build (the "exclude, don't disable" rule, PLAN §2), and add a local OTel collector at Phase 4.4.
- **ADR:** `doc/07-decisions/adr/0006-observability-local-first.md`.

### C6 — Hand-rolled asyncio orchestrator vs LangGraph `StateGraph`
- **Project:** "*Dynamic DAG Execution Engine*" is one async generator (`backend/agent_orchestrator.py:150-163`). It isn't a framework.
- **Plan:** "*Main Agent / Orchestration (LangGraph `StateGraph`, per ADR-0003)*" with a checkpointer and `interrupt` (PLAN §8.1).
- **Recommendation:** adopt LangGraph (already importable in the system Python; pin it per PLAN §13) and **wrap** the existing workers as graph nodes: the visual, math and logistics closures at `agent_orchestrator.py:217-263`. During the transition, keep `/api/chat/stream` emitting the current SSE frames so the frontend keeps working.
- **ADR:** `doc/07-decisions/adr/0003-orchestration-substrate-langgraph.md`.

### C7 — Alpaca prompt template vs shared delimited-evidence assembly
- **Project:** "*Prompt format: Alpaca — matches 100k training dataset exactly*" (`backend/model_service.py:14`). The fine-tuned Mistral-7B in `backend/models/` (`backend/models/config.json`) was trained on it.
- **Plan:** "*One shared `assemble_prompt(...)` used by all agents. Evidence is always placed in a clearly delimited, labelled section … `<untrusted_document_evidence>`*" (PLAN §8.7).
- **Recommendation:** one `assemble_prompt` with **per-model prompt profiles** in `config/prompts/`. The `alpaca` profile goes to the fine-tuned Mistral entry, and `chatml`/native chat to the Ollama models. Every profile must still put evidence inside delimited, labelled "untrusted" sections. That keeps the plan's security rule and the model's training format.
- **ADR:** `doc/07-decisions/adr/0005-model-registry-schema-extension.md` (`prompt_profile` field).

### C8 — Python environment and dependency pinning
- **Project:**
  - `backend/requirements.txt:8-28` mostly uses `>=`.
  - `backend/venv` (Python 3.13.12) is missing `qdrant_client`, `colpali_engine`, `reportlab`, `rapidocr_onnxruntime` and `pytest`.
  - The app only runs on the user-level system Python, which has fastapi 0.141.1 against the pinned 0.115.0 (checked this session).
- **Plan:** "*Pin exact versions in the target*" (PLAN §13); "*requirements had only lower bounds (non-reproducible)*" (§11.20).
- **Recommendation:** one project venv, created from a lockfile generated from the versions that are known to work. The tool is the user's choice (`pip-tools` vs `uv`); a new tool needs an ADR.
- **Decision still needed:** which environment is canonical.
- **ADR:** drafted with Phase 0.3.

---

## 3. Integration seams

| Seam | Where | How |
|---|---|---|
| **Model router** | `backend/model_service.py:235-442` | `router/router.py` resolves capability → registry entry. `ModelService` is **wrapped, not rewritten**: its `_run_ollama_async` / `_run_gguf` / `_run_transformers` closures become `router/providers/{ollama,gguf,transformers}.py` called through one `ModelRouter.stream(capability, messages, evidence)`. `ModelService.stream_response(capability=…)` keeps its signature and delegates to the router, so existing callers (`agent_orchestrator.py:243-247`, `:395-401`; `main.py:335-339`) don't change in Phase 0. |
| **Orchestration graph** | `backend/main.py:309-356` (`/api/chat/stream`) | The compiled LangGraph is mounted behind the same route. An adapter (`api/sse_compat.py`) translates node events into the current `[AGENT_STATUS:…]`, `[DAG_PLAN:…]`, `[VISUAL_REF:…]`, `[EVAL_REPORT:…]` and `[PAGE_REF:…]` frames that `frontend/src/hooks/useChat.js:106-257` parses. New typed `event:` frames run alongside, behind a header or flag, until the frontend switches over. The old `MultiAgentOrchestrator` stays as the legacy path behind `ENABLE_MULTI_AGENT`-style config until the graph reaches parity. |
| **Tool registry** | new `backend/tools/registry.py` | Existing deterministic functions are registered as tools: `AvionicsMathEngine.calculate` (`agent_orchestrator.py:37`), RapidOCR (`visual_rag_service.py:115-123`), page render (`:44-80`), and the table search (`universal_ingestion_service.py:193`). Agents get them only through `get_tools_for()`. |
| **API routes** | `backend/main.py` (single `FastAPI` app, `:52-57`) | New routes go on `APIRouter`s under the **existing `/api` prefix**: `/api/tasks`, `/api/tasks/{id}/stream`, `/cancel`, `/approve`, `/feedback`, `/api/jobs/{id}`, `/api/artifacts/{id}`, `/api/memory`, `/api/audit`, `/api/ui/*`. They're added with `app.include_router(...)`. Existing routes stay as they are. |
| **Workspace identity** | **nowhere today** | `security/gateway.py` is a FastAPI dependency applied to every router. A mock IdP (dev flag only) produces a `UserContext`, and `workspace_id` comes from the request and is authorized there. Existing routes fall back to a single `default` workspace. That fallback is explicit, audited, and absent from the production build (§11.3). `session_id` (`main.py:158-168`) maps to `conversation_id`, not to a workspace. |
| **Config location** | repo root `config/` | `backend/config.py` is imported as `from config import settings` by every module (e.g. `main.py:22`). A `backend/config/` *package* would shadow that module and break the imports, so YAML lives in **`<repo>/config/`** (`models.yaml`, `agents.yaml`, `thresholds.yaml`, `hardware_profiles.yaml`, `prompts/`). The path is resolved from `settings.BASE_DIR/..`, and `config.py` stays the env/settings loader. |
| **Hardware tier** | `backend/main.py:38-49` (lifespan) | `router/hardware_probe.py` runs before `model_svc.load_model()`, selects the tier (ADR-0007), and passes it to `ModelRouter(environment, hardware_tier)`. |
| **Stores** | `colpali_retrieval_service.get_qdrant_client` (`:52-79`) | One shared client, injected everywhere, so there are never two stores (§11.13). The silent `:memory:` fallback becomes a loud failure. |

---

## 4. Proposed target layout (mapped onto the repo; nothing deleted)

```
<repo>/
├── config/                         NEW (repo root; avoids backend/config.py collision)
│   ├── models.yaml                 ← seeded from backend/config.py:25-32 + backend/.env
│   ├── hardware_profiles.yaml      ← ADR-0007
│   ├── agents.yaml  thresholds.yaml  connectors.yaml
│   └── prompts/{main,critic,retrieval,…}.yaml   ← prompt text moved out of model_service.py:182-204 (profiles per C7)
├── kits/aviation/                  NEW ← AIRCRAFT_REGISTRY (pdf_service.py:19-32), fighter prompts,
│                                       math engine fixtures, ChatPanel suggestions (C2)
├── backend/
│   ├── main.py                     KEPT; gains include_router(...) + gateway dependency
│   ├── config.py                   KEPT (env settings only)
│   ├── model_service.py            KEPT as facade → delegates to router/
│   ├── agent_orchestrator.py       KEPT as legacy path; workers re-used by agents/
│   ├── orchestrator_planner.py     KEPT; templates re-used by agents/planner.py
│   ├── visual_rag_service.py       KEPT; page render/OCR wrapped by tools/ + ingestion/
│   ├── colpali_retrieval_service.py KEPT; becomes optional vector space in knowledge/
│   ├── universal_ingestion_service.py / ingestion_adapter.py  KEPT as viewer/PDF path (C3)
│   ├── pdf_service.py              KEPT (aircraft listing via kit)
│   ├── evaluation_service.py       KEPT, relabelled heuristic metrics (feeds eval/, not Critic)
│   ├── langsmith_service.py        KEPT for dev only; local trace path feeds observability/ (C5)
│   ├── agents/      main_agent.py planner.py execution_agent.py coding_agent.py retrieval_agent.py
│   │                data_analysis_agent.py multimodal_agent.py critic_agent.py
│   │                correlation_agent.py memory_agent.py optimization_agent.py
│   ├── router/      router.py health.py model_onboarding.py hardware_probe.py providers/{ollama,gguf,transformers,vllm}.py
│   ├── orchestration/ state.py graph.py task_graph.py persistence.py prompts.py
│   ├── ingestion/   evidence_unit.py detectors.py scanner.py chunker.py pipeline.py queue.py
│   │                extractors/{pdf_text,pdf_scanned,image,csv_xlsx,docx_pptx,audio,text,unsupported}.py
│   ├── knowledge/   vector_store.py embeddings.py graph_store.py entity_resolution.py correlation.py
│   ├── retrieval/   context_manager.py reranker.py hybrid.py
│   ├── memory/      store.py scoping.py
│   ├── tools/       registry.py sandbox_exec.py kb_search.py aero_calc.py ocr_extract.py doc_writers/
│   ├── connectors/  base.py
│   ├── security/    auth.py permissions.py gateway.py injection_guard.py rate_limiter.py egress_guard.py upload_guard.py
│   ├── observability/ audit.py exporter.py tracing.py
│   ├── api/         tasks.py jobs.py artifacts.py audit.py ui.py sse_compat.py schemas.py
│   └── tests/       unit/ integration/ adversarial/ fixtures/   (existing backend/test_*.py stay where they are, collected too)
├── eval/            harness.py metrics.py fixtures/ ground_truth.json   ← absorbs bench/ + bench/gold.jsonl once verified
├── bench/           KEPT (b4 repointed at the real classifier)
├── deploy/          Dockerfile docker-compose.yml zero_egress.env   NEW
├── frontend/src/    KEPT; adds ui/ (primitives), i18n/, features/{tasks,artifacts,approvals,admin}/
└── doc/            adr/ conventions.md safety-rules.md adaptation-map.md PROJECT-ANALYSIS.md IMPROVEMENT-PROPOSAL.md
```

---

## 5. Required changes, in dependency order

1. Governance files plus this map, with ADRs 0001–0007 marked Proposed (Phase −1, §4.1.7).
2. **User decisions on C1–C8 and the §12 items** that block Phase 0 (0.1, 0.2).
3. QW7 / 0.3: one canonical environment with a lockfile, pytest configuration and pytest-asyncio, so the baseline can be re-run reliably.
4. QW8: stop tracking `node_modules`, `dist`, `__pycache__`, `.env`, `data_repository/` and the personal PDFs, without rewriting history, and only after the user decides.
5. QW1: make model resolution fail closed (`model_service.py:385-390`), so missing models show up as errors.
6. QW2: remove the double generation and honour `N_CTX` and `OLLAMA_HOST` (`model_service.py:79`, `:373`, `:380-396`).
7. QW3: upload allowlist, size limits and archive limits (`universal_ingestion_service.py:99-105`, `main.py:172`, `ingestion_adapter.py:253-264`).
8. QW4: label the evaluator and validator honestly (`evaluation_service.py:50`, `:70`; `agent_orchestrator.py:406-427`; `EvaluationScorecard.jsx:17-18`).
9. QW5: the math engine refuses when an input is missing (`agent_orchestrator.py:73`, `:92-98`).
10. QW9: LangSmith off in the local profile; self-host fonts; allowlist Markdown images.
11. QW10: frontend bugs (sending with no document selected, voice restart, stuck stream).
12. 0.4: contracts §7.1–7.6 and §7.8 (registry, router, state, AgentMessage, EvidenceUnit, ToolSpec, AuditEvent), with `ModelService` wrapped as the provider.
13. QW11 / 0.4b: hardware probe plus tier selection, feeding the router and `agents.yaml`.
14. QW6 (requires ADR-0004 / §12.7): real text embeddings through the router's `embedding` tag; ColPali opt-in.
15. 0.5: minimal LangGraph graph (classify → coding | draft → critic) plus a Docker sandbox, using the existing `/api/chat/stream` through `sse_compat`.
16. 0.6: fixture corpus v0 with ground truth; mark `bench/gold.jsonl` entries `verified:true` only once a human has checked them.
17. 0.7: reclassify the risks in `doc/01-status/PROJECT_STATE.md`.
18. 1.1–1.5: Qdrant schema review, EvidenceUnit extractors (PDF text, scanned PDF/image using RapidOCR, CSV/XLSX), the full ingestion pipeline, and a workspace-filtered `search_knowledge_base`.
19. 1.6–1.9: Multimodal agent (vision model actually called), Retrieval agent, Data Analysis agent (wrapping the table search and math tools), Execution agent with versioned writers.
20. 1.10–1.12: DAG dispatcher, Critic gate, synthesis, session memory, audit trail. Then the frontend moves to typed SSE events, inline citations and the activity timeline.
21. 2.1–2.6: tier-by-tier local parity, tool-calling parity, latency (B1 rerun), the no-egress test including rejection of `:cloud` tags, and failover.
22. 3.1–3.12: graph store, entity-resolution spike (equipment IDs), correlation with a negative control, memory, continuation, ASR, first connector, RBAC (blocked on §12.1), reranker plus hybrid retrieval.
23. 4.1–4.6: adversarial suite, fault injection, load testing on real hardware, OpenTelemetry, security review.
24. 5.1–5.6: scale-out, the Optimization Agent, pilot, model-refresh process.

---

## 6. Must be preserved

| Asset | Path | Why |
|---|---|---|
| SSE streaming UX and the frame protocol (during the transition) | `backend/main.py:309-356`; `frontend/src/hooks/useChat.js:69-298` | It's working now and the user sees it |
| Agent activity HUD | `frontend/src/components/AgentActivityHUD.jsx` | Already matches PLAN §8.16's "agent activity view" |
| PDF viewer synced to the cited page | `frontend/src/components/PdfViewer.jsx:41-50`; `/api/pdf/{id}` (`backend/main.py:266-285`) | Visual citation is a strong feature |
| Page-image render cache and thumbnails | `backend/visual_rag_service.py:32-80`, `:285-300`; `main.py:230-261` | Basis for page-level `media_ref` evidence |
| RapidOCR scan fallback | `backend/visual_rag_service.py:113-125` | Real OCR that already works |
| Format converters (LibreOffice, reportlab) | `backend/ingestion_adapter.py:316-459` | The viewer path under C3 |
| Deterministic aero math (once fixed) | `backend/agent_orchestrator.py:31-143` | Principle 3; becomes a kit tool |
| Ollama-first local inference, GGUF and transformers backends | `backend/model_service.py:61-147` | Already aligned with zero egress |
| Fine-tuned Mistral-7B weights | `backend/models/` (gitignored) | Becomes a registry entry with the `alpaca` prompt profile (C7) |
| Dynamic DAG plan display | `orchestrator_planner.py:18-134`, `[DAG_PLAN]` event | The UI already understands plans |
| Benchmarks and gold questions | `bench/*.py`, `bench/gold.jsonl`, `bench/results/` | B1 latency data feeds `latency_profile`. B4 and B10 need fixing, not deleting |
| Project design docs | `README.md`, `MIGRATION.md`, `FRONTEND.md`, `conversation.md`, `bench/FIX_PROPOSALS.md` | Rationale only, ranked as historical design docs (PLAN §3.1.3). Never overwritten without approval |
| Existing tests | `backend/test_*.py` | Part of the baseline (8 pass). Keep them and make them hermetic |

---

## 7. Where the plan should bend to the project

1. **The `/api` route prefix.** Plan routes become `/api/tasks…` and so on, and existing routes stay. PLAN §8.15 paths change by prefix only.
2. **No hosted dev profile if C1 is local-only.** The `hf` block stays empty, development runs on local tiers, and M2 "against hosted models" becomes "against `cpu_lite` local models".
3. **Ollama first.** The plan's default local backend already matches. vLLM comes in only at `gpu_multi` (ADR-0007).
4. **Embedded Qdrant at MVP.** `QdrantClient(path=…)` (`colpali_retrieval_service.py:74`) is acceptable instead of a Qdrant server until there are several workers. Pin the client version and fail loudly instead of falling back to `:memory:`.
5. **Page images as a first-class evidence location.** `PageSectionLocation.page_number` plus `media_ref=/api/documents/{doc}/page/{n}/image` (`colpali_retrieval_service.py:236`). Citations can point at a rendered page, not only at text.
6. **Hardware tiers on top of environments.** PLAN §5.3 has two profiles. AeroMind needs environment × hardware tier: `cpu_lite` on the i7 dev machine, `gpu_*` on NVIDIA/AMD, `apple_full` on Mac (ADR-0007, user request). Code parity still holds, because the tier only selects configuration.
7. **The fine-tuned Mistral as a registry entry.** `provider: transformers|gguf`, `prompt_profile: alpaca`, with capabilities set by eval results. It isn't discarded.
8. **Aviation as a starter kit.** Aviation becomes the first vertical kit and the first set of eval fixtures (PLAN §1.5's non-goals aren't affected).
9. **Python 3.13 and FastAPI already match** PLAN §13. No framework changes.
10. **A deterministic math tool.** It's a domain tool with no equivalent in PLAN §6, and it fits principle 3.

---

## 8. Open questions (PLAN §12): what AeroMind's context already answers

| # | Question | Answered by AeroMind? | Evidence | Still needed from user |
|---|---|---|---|---|
| 1 | Identity provider | **Partially** | "*offline user provisioning (no external identity provider, given air-gap requirement)*" (`MIGRATION.md:192`); "*local RBAC (viewer / analyst / admin)*" (`MIGRATION.md:127`) | Which local IdP: Keycloak, a local user DB, or LDAP? |
| 2 | Air-gap vs isolated network | **Partially** | "*NO ONLINE CONNECTION*" (`conversation.md:49`); "air-gap requirement" (`MIGRATION.md:192`). But the dev machine has internet, Google Fonts and `:cloud` Ollama models | Is it a true air-gap in production, or an isolated network? Is internet allowed in development? |
| 3 | HTML/intranet ingestion | **No** | No HTML extractor; `.html` isn't in the upload list | Yes or no |
| 4 | Approval authority | **No** | No approvals exist | Who approves, and at what risk level |
| 5 | Voice output | **Partially** | TTS button exists (`MessageBubble.jsx:214`); "*voice output with procedural narration*" (`conversation.md:31`), via the browser, which may send text to the cloud | Keep it, local-only, or drop it? |
| 6 | Production hardware | **Partially** | Dev machine: i7-1185G7, Iris Xe integrated GPU, 31 GiB RAM, no CUDA (checked). "*Target hardware floor (minimum VRAM)*" is itself an open question (`MIGRATION.md:190`) | Is the 24 GB GPU real? Which Macs? |
| 7 | Embedding model | **No** | ColQwen2 is configured (`config.py:47`) but never loads; `nomic-embed-text` is installed in Ollama | Choose one (bge-m3 recommended). Changing it later means full re-ingestion |
| 8 | Classification levels | **No** | — | List of levels and how clearances map to them |
| 9 | Max latency | **Partially** | Target was "*sub-10 second responses on local CPU*" (`conversation.md:96`); B1 measured 29 s median for qwen2.5:3b (`bench/results/b1_per_model_AS_IS.json`) | Acceptable p95 for each task type |
| 10 | First connector | **No** | — | Stakeholder's choice |
| 11 | Offline transfer procedure | **Partially** | `models.lock` planned (`MIGRATION.md:107`); signed manifests (`MIGRATION.md:128`) | The actual procedure and media |
| 12 | Video / VLM quantization loss | **No** | No video support. VLM quality never measured (no VLM ever runs, 8.2c) | Accept or reject after the Phase 2 eval |
| 13 | Retention periods | **No** | Traces and uploads are kept forever and committed to git (`backend/data_repository/`) | Retention for scratch, memory, audit and uploads |
| 14 | Project-specific conflicts | **This document** | C1–C8 above | Decisions on C1–C8 |
