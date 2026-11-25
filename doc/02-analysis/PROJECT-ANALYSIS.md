# AeroMind 2.0 — Project Analysis (Stage 1 / Plan Phase −1)

> **Correction (2026-11-04):** the per-role models in `backend/.env` (`ORCHESTRATOR_MODEL`, `VISION_MODEL`, …) were **never applied**. Nothing calls `load_dotenv`, and they aren't pydantic fields, so every role actually ran on `qwen2.5:3b`. Statements below that "four of six configured models silently fall back" describe the fallback *code path* (`model_service.py:385-390`, removed by QW1), not what ran. See `doc/01-status/PROJECT_STATE.md` → Session 2026-11-04.


**Date:** 2026-11-03 · **Scope:** the whole repository at commit `79e8006` ("Add benchmark results"). Everything except vendored `frontend/node_modules`, `backend/venv` and model weights was read.
**Audience:** engineers (and coding agents) taking over the project before it is adapted to `PROJECT-IMPLEMENTATION-PLAN.md`.
**Citation format:** `path:line` relative to the repository root. Each claim marked *(verified this session)* was executed or reproduced during this analysis. All other claims come from reading the source.

---

## 0. Executive summary

AeroMind 2.0 is a single-user, single-document, local-first RAG chat app. It pairs a **FastAPI** backend with a **React/Vite** frontend and targets one domain: a MiG-21bis flight manual.

It presents itself as a "multi-agent SLM" system with "ColPali visual RAG", a "safety/SOP validator" and an "evaluation scorecard". Several of those parts don't do what they claim:

| Part | What it actually does |
|---|---|
| Planner | A keyword heuristic |
| Plan graph (DAG) | Emitted to the UI, never executed |
| Safety/SOP validator | A hard-coded status message |
| Evaluation scores | Have a floor of 78% |
| Visual retrieval | Uses pseudo-random vectors seeded by Python's salted `hash()`, so results change between restarts *(verified this session)* |
| Model routing | Silently falls back to `qwen2.5:3b` because four of the six configured agent models aren't installed |

There is no authentication, no workspace isolation, no audit log, a path-traversal file write, and a cloud tracing integration (LangSmith) that conflicts with the project's own "no online connection" requirement.

What is worth keeping:
- The streaming chat UX, the agent-activity HUD and the PDF viewer that jumps to the cited page.
- The page-render cache and the RapidOCR fallback.
- An Ollama-first local inference path.
- A deterministic math engine, once its invented defaults are removed.
- A benchmark folder with honest self-criticism (`bench/FIX_PROPOSALS.md`).

---

## 1. Purpose, users and workflows

### 1.1 What the docs say
- **Positioning:** "a production-grade, local-first defense intelligence platform designed for military aviation, flight systems diagnostics, and technical manual operations" (`README.md:1-3`).
- **Claimed agents:**
  - Mission Commander / Supervisor SLM
  - ColPali Visual Schematic Agent
  - Avionics Math Engine, "with zero hallucination"
  - Tabular & Logistics Agent
  - Flight Safety & SOP Validator
  - Command Synthesis SLM

  Source: `README.md:9-15`.
- **Claimed features:**
  - Multi-format ingestion: PDF, DOCX, CSV/XLSX, JSON, images (`README.md:17-22`)
  - Voice in and out (`README.md:23-25`)
  - LangSmith Cloud tracing and real-time evaluation scorecards (`README.md:26-29`)
  - A "jargon-free live HUD" (`README.md:30`)
- **Users:** pilots, technicians and flight engineers asking about procedures, Mach/fuel calculations and schematics, with answers linked to manual pages (`conversation.md`, `FRONTEND.md`).
- **Direction of travel:**
  - `MIGRATION.md` is a phased plan from the "MiG-21-bootstrapped prototype" to a general local multi-document platform. Phase 1 is marked done; phases 2–8 cover citations with `doc_id`, VRAM budgeting, a reranker/BM25, offline `models.lock`, role-based access, audit, local observability and LoRA. All are unchecked.
  - `FRONTEND.md` is a plan to remove military jargon and emoji, add design tokens and a light mode. It hasn't been implemented (see §7).

### 1.2 Workflows actually supported by the code
1. **Pick a manual and chat.**
   - The frontend selects a document (`frontend/src/hooks/useAircraft.js`) and POSTs to `/api/chat/stream` (`frontend/src/hooks/useChat.js:69`).
   - The backend plans with keywords, runs up to three "workers", streams a synthesis and emits a scorecard (`backend/agent_orchestrator.py:150-456`).
2. **Upload a document** through the document manager (`/api/documents/upload`, `backend/main.py:135-152`) or a session upload (`/api/documents/session-upload`, `backend/main.py:155-227`; the current frontend doesn't call it, see §3.6).
3. **View a PDF page** that the answer refers to (`[PAGE_REF:n]` → `frontend/src/components/PdfViewer.jsx:41-50`).
4. **Inspect traces** in the Prompt Inspector modal (`/api/prompts/inspect`, `backend/main.py:298-304`).
5. **Voice:** browser Web Speech API for input and output (`frontend/src/components/VoiceController.jsx:20-31`).

### 1.3 Contradictions between the docs and the code

| Doc claim | Reality | Evidence |
|---|---|---|
| "Supervisor SLM … dynamic task decomposition" (`README.md:10`) | A regex keyword template, returned "instantly" | `backend/orchestrator_planner.py:229-230` |
| Plan DAG executed "parallel & sequential" (`README.md:9`) | The DAG is sent to the UI. Execution is three fixed booleans run with `asyncio.gather` | `backend/agent_orchestrator.py:206-270` |
| "Safety & SOP Validator" (`README.md:14`) | No check. It emits a hard-coded "thought" | `backend/agent_orchestrator.py:406-427` |
| Math "with zero hallucination" (`README.md:12`) | Uses hard-coded defaults (2800 kg fuel, 58 / 280 kg/min) when the user gives no numbers | `backend/agent_orchestrator.py:92-98` |
| "ColPali" visual retrieval (`README.md:16`) | ColQwen2 never loads by default; vectors are pseudo-random | `backend/colpali_retrieval_service.py:118-119,136-176` |
| "Entire system locally hosted, with no online connection" (`conversation.md:48-50`) and "All SLMs run entirely locally" (`conversation.md:185`) | LangSmith cloud upload, Google Fonts, Web Speech API (cloud speech in Chrome/Edge), HF Hub downloads | `backend/langsmith_service.py:89-98`, `frontend/index.html:7-8`, `frontend/src/components/VoiceController.jsx:20-31`, `download_model.py` |
| `MAX_NEW_TOKENS = 500` (`conversation.md:96`) | 300 in code; 1200 in `.env.example` | `backend/config.py:60` |
| Models "below 7B" (`conversation.md:48-50`) | `.env` asks for 7B models that aren't installed | `backend/.env` (`ORCHESTRATOR_MODEL=qwen2.5:7b-instruct`, `MATH_MODEL=qwen2.5-math:7b`, `REASONING_MODEL=deepseek-r1-distill-qwen:7b`) |

---

## 2. Tech stack, versions and environment

### 2.1 Backend
- **Language:** Python 3.13.12. The venv was created from `/usr/bin/python3.13` (`backend/venv/pyvenv.cfg`), and the committed `__pycache__` files are `cpython-313`.
- **Framework:** FastAPI + Uvicorn. The single app is `backend/main.py:52-57`; settings use `pydantic-settings` (`backend/config.py:4,7-91`).
- **Imports:** flat; modules import each other by bare name (`from config import settings`, `backend/main.py:22-30`). This means the working directory must be `backend/`.
- **Dependencies** (`backend/requirements.txt`):
  - Exact pins only for fastapi 0.115.0, uvicorn 0.30.6, python-multipart 0.0.9, pydantic-settings 2.4.0, python-dotenv 1.0.1 and httpx 0.27.2 (`backend/requirements.txt:2-5,31-32`).
  - Everything else is `>=`: torch, transformers, colpali-engine, qdrant-client, langsmith, pandas, PyMuPDF and others (`backend/requirements.txt:8-28`). Builds are not reproducible (plan pitfall §11.20).
  - `reportlab` is imported (`backend/ingestion_adapter.py:334,394,440`) but not listed.
  - `rapidocr_onnxruntime` is imported (`backend/visual_rag_service.py:116`) but not listed.
  - `pytest` is not listed.
- **Two Python environments, and only one can run the app** *(verified this session)*:

| Package | `backend/venv/bin/python` | system `python3` |
|---|---|---|
| fastapi | 0.115.0 | 0.141.1 |
| pydantic_settings | 2.4.0 | 2.5.2 |
| qdrant_client | **MISSING** | ok |
| fitz (PyMuPDF) | ok | 1.28.2 |
| pandas | 3.0.5 | 3.0.5 |
| reportlab | **MISSING** | 5.0.1 |
| langsmith | 0.11.2 | 0.10.18 |
| torch | 2.11.0+cu130 | 2.13.0+cu130 |
| transformers | 5.7.0 | 5.16.1 |
| colpali_engine | **MISSING** | ok |
| rapidocr_onnxruntime | **MISSING** | ok |
| pytest | **MISSING** | 9.0.2 |
| langgraph / langchain_core | **MISSING** | ok / 1.5.4 |
| ruff | MISSING | MISSING |

  The venv follows `setup.sh` (`setup.sh:9-11`) but can't import `colpali_retrieval_service`'s Qdrant dependency. The working runtime is the user-level system Python (`~/.local/lib/python3.13/site-packages`).

- **Stores:**
  - Embedded Qdrant on disk at `backend/data_repository/qdrant_db` (`backend/config.py:57`; client creation at `backend/colpali_retrieval_service.py:59-77`).
  - A JSON document registry (`backend/universal_ingestion_service.py:31`).
  - The local filesystem for uploads, page images and traces (`backend/config.py:74-80`).
  - No relational DB, no queue, no auth provider.

### 2.2 Frontend
- **Dependencies** (`frontend/package.json:11-26`): React 18.3.1, react-markdown ^10.1.0 + remark-gfm, react-pdf ^9.1.0 with **pdfjs-dist pinned to 4.8.69**, and lucide-react. Dev: Vite ^5.4.2, Tailwind ^3.4.10, PostCSS, autoprefixer.
- **Scripts:** only `dev`, `build` and `preview` (`frontend/package.json:6-10`). There is no lint, test or typecheck, no ESLint/Prettier/TS/Vitest config, and the code is plain JSX.
- **Dev proxy:** `/api` goes to the hard-coded `http://127.0.0.1:8000` (`frontend/vite.config.js:7-10`).

### 2.3 Models and inference
- **Ollama** is the default backend (`backend/config.py:18-20`). Installed models *(verified with `ollama list` this session)*:

| Model | Size | Used by config? |
|---|---|---|
| qwen3:4b-instruct-2507-q4_K_M | 2.5 GB | no |
| qwen3:4b | 2.5 GB | no |
| qwen3-vl:2b | 1.9 GB | no |
| qwen2.5:3b | 1.9 GB | **yes** (`OLLAMA_MODEL`, `SYNTHESIS_MODEL`; every fallback lands here) |
| qwen2.5-coder:1.5b | 986 MB | no |
| gemma4:e4b | 9.6 GB | `VISION_MODEL` (but never called for generation, see §4.4) |
| nomic-embed-text | 274 MB | no (no text embeddings exist in the code) |
| glm-5.1:cloud, glm-5:cloud, kimi-k2.5:cloud | — | no, but **these are remote models served through the same local daemon**: an egress path that any request naming them would open |

- **Configured but not installed:** `qwen2.5:7b-instruct` (orchestrator), `qwen2.5-math:7b` (math), `deepseek-r1-distill-qwen:7b` (reasoning), `qwen2.5:3b-instruct` (verification). These are set in `backend/.env`; defaults are at `backend/config.py:25-32`.
- **Fine-tuned local model** in `backend/models/`: a `MistralForCausalLM`, about 7.25B parameters in fp16 across three safetensors shards (14 GB on disk). Weights aren't tracked (`.gitignore:1,3`).
  - It is only used when `USE_OLLAMA=false` and `USE_LLAMA_CPP=false` (`backend/model_service.py:65-70,109-147`).
  - Its provenance is inconsistent: `backend/models/export_metadata.json` says the base is `unsloth/mistral-7b-v0.3-bnb-4bit`, while `backend/models/README.md` says `Mistral-7B-v0.1`.
  - The HF repo ID differs between `backend/models/README.md` and `backend/config.py:9` / `download_model.py`.

### 2.4 Hardware of the development machine *(verified this session)*
- CPU: Intel Core i7-1185G7, 8 threads.
- GPU: **Intel Iris Xe (TigerLake-LP GT2) only. No NVIDIA device, no `/dev/nvidia*`, no `nvidia-smi`, so no CUDA.**
- RAM: 31 GiB (about 7.8 GiB available at the time of the check) plus 24 GiB swap.
- Disk: 155 GB free.
- Docker and Ollama are installed (other unrelated containers are running).

All inference here is CPU-only. Benchmark B1 measured about 9.1 tok/s for qwen2.5:3b and about 5.1 tok/s for gemma4:e4b (`bench/results/b1_per_model_AS_IS.json`).

### 2.5 Build, deploy and CI
- There is no Dockerfile, docker-compose file, CI workflow, Makefile, `pyproject.toml`, `pytest.ini` or `conftest.py` anywhere in the repo.
- The only setup is `setup.sh`. It creates a venv, runs `pip install`, runs `cp .env.example .env` (which overwrites an existing `.env`), and runs `npm install` (`setup.sh:9-18`).
- The README quick start is at `README.md:37-57`.

---

## 3. Architecture

### 3.1 Backend module map

| Module | Responsibility | Key lines |
|---|---|---|
| `backend/main.py` | FastAPI app, CORS, all routes, SSE wrapper, lifespan | `:38-49`, `:52-65`, `:83-356` |
| `backend/config.py` | `Settings` (env + `.env`), role→model map, paths; creates directories at import time | `:7-91`, `:25-32`, `:94-102` |
| `backend/model_service.py` | Model backends (Ollama / llama.cpp / transformers), Alpaca prompt builder, token streaming | `:47-147`, `:152-218`, `:235-442` |
| `backend/agent_orchestrator.py` | `AvionicsMathEngine` (regex math), `MultiAgentOrchestrator.execute_query_stream` (the whole "multi-agent" pipeline) | `:31-143`, `:146-456` |
| `backend/orchestrator_planner.py` | Four hard-coded DAG templates and a regex classifier | `:18-134`, `:137-212`, `:215-230` |
| `backend/visual_rag_service.py` | PDF page render cache (PyMuPDF), per-page layout heuristics, RapidOCR fallback, keyword fallback ranking | `:44-80`, `:82-198`, `:200-283` |
| `backend/colpali_retrieval_service.py` | Qdrant client, per-document multi-vector collection, ColQwen2 (opt-in) or fallback vectors, MaxSim search | `:52-79`, `:81-109`, `:111-176`, `:178-345` |
| `backend/universal_ingestion_service.py` | JSON registry, upload save, per-format metadata parsing, "multi-dataset" search | `:36-81`, `:83-191`, `:193-253` |
| `backend/ingestion_adapter.py` | Session upload normalisation: DOCX/XLSX/CSV/TXT/image/ZIP → PDF (reportlab/LibreOffice) → visual index | `:35-76`, `:78-312`, `:316-459` |
| `backend/pdf_service.py` | Hard-coded `AIRCRAFT_REGISTRY` (MiG-21bis), PDF path lookup, single-stream context builder | `:19-32`, `:64-78`, `:101-121` |
| `backend/evaluation_service.py` | Heuristic "faithfulness / citation / safety" scorecard | `:20-97` |
| `backend/langsmith_service.py` | Local JSON trace files plus LangSmith cloud `create_run` | `:20-24`, `:51-102`, `:104-114` |
| `backend/test_*.py` | Tests and scripts (see §6.1) | — |

**Singletons are created at import time:**
- `model_svc` (`backend/main.py:34`)
- `universal_ingestion` (`backend/universal_ingestion_service.py:256`), which reads and writes the registry in its constructor (`:33-34`)
- `visual_rag_service`, `colpali_retrieval_service`, `ingestion_adapter`, `pdf_svc`, `multi_agent_orchestrator`, `langsmith_service`, `evaluation_service`

Importing any module touches the filesystem: `backend/config.py:94-102` creates directories.

### 3.2 Entry point and background work
- **Run command:** `cd backend && uvicorn main:app --reload --port 8000` (`README.md:49-51`).
- **Lifespan** (`backend/main.py:38-49`):
  1. If `mig21bis.pdf` exists, start `visual_rag_service.index_document` in a thread without awaiting it (`:42-46`).
  2. Start `model_svc.load_model()` without awaiting it (`:47`). For Ollama this is only an HTTP check against the hard-coded `http://127.0.0.1:11434/api/tags`; it ignores `OLLAMA_HOST` (`backend/model_service.py:79`).
- **Other background work:** `POST /api/model/load` dispatches `model_svc.load_model` with FastAPI `BackgroundTasks` (`backend/main.py:110-117`). There is no queue, no job table, and no cancellation.
- **Synchronous heavy work in request handlers:**
  - Session upload runs full conversion, OCR and indexing inline inside an `async` handler (`backend/main.py:178-212`), so the event loop is blocked.
  - `ingest_file` does the same for PDFs (`backend/universal_ingestion_service.py:123-139`).

### 3.3 API surface: every route in `backend/main.py`

| Method | Path | Handler (line) | Purpose | Auth / authz |
|---|---|---|---|---|
| GET | `/api/health` | `health` (`:83-94`) | Flags, model state, document count | none |
| GET | `/api/aircraft` | `list_aircraft` (`:97-99`) | Hard-coded aircraft registry | none |
| GET | `/api/model/status` | `model_status` (`:102-107`) | Model load status | none |
| POST | `/api/model/load` | `trigger_model_load` (`:110-117`) | Background model load | none |
| GET | `/api/documents/list` | `list_documents` (`:122-124`) | **All** documents, optional `category` filter | none |
| GET | `/api/documents/{doc_id}` | `get_document_meta` (`:127-132`) | Registry entry, including the server `file_path` | none |
| POST | `/api/documents/upload` | `upload_universal_file` (`:135-152`) | Multipart upload → `ingest_file` | none |
| POST | `/api/documents/session-upload` | `session_document_upload` (`:155-227`) | Upload → normalise → index | none |
| GET | `/api/documents/{doc_id}/page/{page_num}/image` | `get_page_image` (`:230-244`) | PNG page render (renders on demand) | none |
| GET | `/api/documents/{doc_id}/page/{page_num}/thumb` | `get_page_thumb` (`:247-261`) | JPEG thumbnail | none |
| GET | `/api/pdf/{aircraft_id}` | `serve_pdf` (`:266-285`) | Raw PDF, `Cache-Control: public` | none |
| POST | `/api/pdf/upload/{aircraft_id}` | `upload_pdf` (`:288-293`) | Upload a PDF under an id | none |
| GET | `/api/prompts/inspect` | `inspect_traces` (`:298-304`) | Last N traces, **all users' queries and responses** | none |
| POST | `/api/chat/stream` | `chat_stream` (`:309-356`) | SSE multi-agent chat | none |

**Cross-cutting:**
- CORS allows `*` origins **with** credentials, plus all methods and headers (`backend/main.py:59-65`).
- No identity is carried anywhere.
- `doc_id` values come from the client and are used to build filesystem paths. `get_document_cache_dir` creates `page_images/<doc_id>` for any id it's given (`backend/visual_rag_service.py:32-35`).

### 3.4 SSE protocol (in-band control frames)
The server writes `data: <payload>\n\n` frames (`backend/main.py:322-356`).

**Control frames** are encoded *inside the token stream* as `[TAG:json]` strings:

| Frame | Emitted at | Parsed at (frontend) |
|---|---|---|
| `[AGENT_STATUS:{agent,title,action,stage,node_id,model}]` | `backend/agent_orchestrator.py:185,214,328,417` | `frontend/src/hooks/useChat.js:152` |
| `[DAG_PLAN:{intent,rationale,nodes[]}]` | `backend/agent_orchestrator.py:192` | `frontend/src/hooks/useChat.js:124` |
| `[AGENT_THOUGHT:{step,agent,title,thought,task,status}]` | `backend/agent_orchestrator.py:202,284,306,324,338,427` | `frontend/src/hooks/useChat.js:133` |
| `[VISUAL_REF:{page,is_schematic,is_diagram,headings,image_url,thumbnail_b64}]` | `backend/agent_orchestrator.py:295` | `frontend/src/hooks/useChat.js:181` |
| `[AGENT_STEP:{agent,title,summary}]` | `backend/agent_orchestrator.py:313` | `frontend/src/hooks/useChat.js:161` |
| `[EVAL_REPORT:{…}]` | `backend/agent_orchestrator.py:440` | `frontend/src/hooks/useChat.js:200` |
| `[PAGE_REF:n]` | `backend/agent_orchestrator.py:441` | `frontend/src/hooks/useChat.js:218` |
| `[ERROR:msg]` | `backend/main.py:344` | `frontend/src/hooks/useChat.js:237` |
| `[DONE]` | `backend/main.py:346` | `frontend/src/hooks/useChat.js:106` |
| (anything else) = answer text, with `\n` escaped as `\\n` | `backend/agent_orchestrator.py:403-404`, `backend/main.py:338-339` | `frontend/src/hooks/useChat.js:257` |

**Problems:**
1. Model or document text that contains `[DONE]`, `[ERROR:…]` or `[PAGE_REF:…]` is interpreted as a control frame (spoofing).
2. A literal backslash-n in generated code is corrupted on the client.
3. Some JSON is built with f-strings around model names (`backend/agent_orchestrator.py:185,328,417`), which breaks if a name contains `"`.
4. Model failures arrive as answer text (`"[Generation error: …]"`, `backend/model_service.py:400,418,421,425`), not as error frames.

### 3.5 Data flow of one chat request (`POST /api/chat/stream`)
1. `ChatRequest{aircraft_id, session_id, doc_id, messages[]}` (`backend/main.py:74-78`). `target_id = doc_id or aircraft_id or "default"` (`:319`). The client sends the whole history, including prior *assistant* turns, which the server trusts.
2. `execute_query_stream` resolves the document path through the registry, then `pdfs/`, then `uploads/` candidates (`backend/agent_orchestrator.py:168-181`).
3. **Planning:** `orchestrator_planner.plan_workflow` → `_heuristic_dag_fallback` keyword regexes (`backend/orchestrator_planner.py:137-212,229-230`). The plan is sent to the UI (`backend/agent_orchestrator.py:192`).
4. **"Dispatch":** three booleans are derived from the plan's capabilities and node ids (`backend/agent_orchestrator.py:206-211`). `asyncio.gather` runs (`:266-270`):
   - visual retrieval (`:217-227`)
   - math: regex first, then LLM fallback (`:229-256`)
   - "logistics": `search_multi_dataset` (`:258-263`)
5. **Context assembly:**
   - Up to 3 pages, 3000 characters each. PyMuPDF is reopened per page if the snippet is shorter than 100 characters (`backend/agent_orchestrator.py:341-370`).
   - Plus the math summary and 2 × 400-character logistics snippets (`:372-379`).
   - Up to 2 base64 page images (`:384-391`).
6. **Synthesis:** `model_service.stream_response(..., capability="synthesis")` (`backend/agent_orchestrator.py:395-404`).
   - Builds the Alpaca prompt (`backend/model_service.py:267`) and resolves the model from `AGENT_MODEL_MAP` (`:257-265`).
   - Streams from Ollama after first making a full non-streamed call (§6.4).
7. **"Verification":** a status frame and a canned thought only (`backend/agent_orchestrator.py:406-427`).
8. **Scorecard:** `evaluation_service.evaluate_response` (`backend/agent_orchestrator.py:431-438`) → `[EVAL_REPORT]` and `[PAGE_REF]` (`:440-441`).
9. **Trace:** `langsmith_service.create_run_trace` writes `data_repository/traces/trace_<uuid>.json`, and uploads to the cloud if a key is set (`backend/agent_orchestrator.py:444-456`; `backend/langsmith_service.py:80-100`).

### 3.6 Frontend structure
- **Component tree:**
  - `main.jsx` → `App` (`frontend/src/App.jsx`)
  - `App` renders `TopBar` (with `AircraftSelector`), `ChatPanel` (with `AgentActivityHUD`, a `MessageBubble` list and `VoiceController`), `PdfViewer` (controlled through a ref), and the modals `UniversalDocumentManager` and `PromptInspectorModal`.
  - `MessageBubble` uses `VisualDiagramCard`, `EvaluationScorecard`, a TTS button and an `AgentThinkingAccordion` defined in the same file.
- **State:** local `useState` only, through the hooks `useAircraft` and `useChat`. There is no store or context.
- **Streaming:** `fetch` with a manual `ReadableStream` reader, split on `\n\n` (`frontend/src/hooks/useChat.js:69-103`). It doesn't use `EventSource`.
- **Every URL the frontend calls** (all relative, through the Vite proxy):

| Method | URL | Caller |
|---|---|---|
| GET | `/api/aircraft` | `frontend/src/hooks/useAircraft.js:18` |
| POST | `/api/chat/stream` | `frontend/src/hooks/useChat.js:69` |
| GET | `/api/model/status`, every 4 s, forever | `frontend/src/components/TopBar.jsx:27,36` |
| GET | `/api/pdf/${aircraftId}` | `frontend/src/components/PdfViewer.jsx` (react-pdf `file`) |
| GET | `/api/documents/list` | `frontend/src/components/UniversalDocumentManager.jsx:28` |
| POST | `/api/documents/upload` | `frontend/src/components/UniversalDocumentManager.jsx:59` |
| GET | `/api/prompts/inspect?limit=10` | `frontend/src/components/PromptInspectorModal.jsx:22` |
| GET | `image_url` from SSE payloads | `frontend/src/components/VisualDiagramCard.jsx` |
| GET (egress) | `https://fonts.googleapis.com/...` | `frontend/index.html:7-8` |

  `/api/documents/session-upload` and `/api/pdf/upload/{id}` have no frontend caller.

---

## 4. AI/LLM usage

### 4.1 Every place that calls a model provider directly
All of these are plan §2.1 router violations: no call goes through a capability-tag router.

| # | Call | Location | Network? |
|---|---|---|---|
| 1 | Ollama `GET /api/tags` health check (hard-coded host) | `backend/model_service.py:77-86` | localhost |
| 2 | Ollama `POST /api/generate`, **non-streamed** (wasted full generation) | `backend/model_service.py:380-384` | localhost |
| 3 | Ollama `POST /api/generate`, streamed | `backend/model_service.py:392-414` | localhost |
| 4 | llama-cpp-python `Llama(...)` GGUF | `backend/model_service.py:88-107,273-290` | local |
| 5 | transformers `AutoModelForCausalLM.from_pretrained(HF_MODEL_ID, trust_remote_code=True)` | `backend/model_service.py:109-147` | **HF Hub** if not cached; `trust_remote_code=True` runs repo code |
| 6 | ColQwen2 `from_pretrained(COLPALI_MODEL_NAME)`, gated by `ENABLE_COLPALI_DOWNLOAD` | `backend/colpali_retrieval_service.py:111-134` | **HF Hub** |
| 7 | `huggingface_hub.snapshot_download` | `download_model.py` | **HF Hub** |
| 8 | `test_model.py` loads `HF_MODEL_ID` with no cache dir | `backend/test_model.py:7-23` | **HF Hub** |
| 9 | LangSmith `Client(...).create_run(...)` with the query and the first 500 characters of the response | `backend/langsmith_service.py:34-46,89-100` | **cloud** (`api.smith.langchain.com`, `backend/config.py:39`) |
| 10 | RapidOCR (ONNX, local) | `backend/visual_rag_service.py:113-125` | local |

The agents that use #2/#3 are the orchestrator's math fallback (`backend/agent_orchestrator.py:243-248`) and synthesis (`:395-401`).

### 4.2 Model selection ("routing")
- **Role → model name map:** `AGENT_MODEL_MAP` (`backend/config.py:25-32`). The roles are orchestrator, math, vision_table, reasoning, verification and synthesis. Roles aren't capability tags, and there is no version, context, VRAM or rank.
- **Resolution:** `capability` → map entry → else `synthesis` → else `OLLAMA_MODEL` (`backend/model_service.py:257-265`).
- **Silent fallback:** if Ollama returns 404, the code silently retries with `OLLAMA_MODEL` (`backend/model_service.py:385-390`). Four of the six configured models aren't installed (§2.3), so in practice **every role runs on `qwen2.5:3b`** while the UI shows the configured names in `AGENT_STATUS` (`backend/agent_orchestrator.py:184-185`). This is plan pitfall §11.5. It is already documented as fix (a) in `bench/FIX_PROPOSALS.md`.
- **Vision support** is guessed from substrings of the model name (`backend/model_service.py:357`). Synthesis uses `qwen2.5:3b`, so the page images gathered at `backend/agent_orchestrator.py:384-391` are **dropped**. The configured `vision_table` model (gemma4:e4b) is only used as a label in the plan (`backend/orchestrator_planner.py:27`); no code path generates with it. **No VLM ever runs.**
- **Fixed generation options:**
  - `num_ctx: 2048` is hard-coded (`backend/model_service.py:373`), although `N_CTX=8192` (`backend/config.py:21`). Prompts with 3 × 3000-character pages plus history easily pass 2048 tokens and are silently truncated by Ollama.
  - `num_thread: 8` is hard-coded (`backend/model_service.py:372`).

### 4.3 Prompt construction
- **One template for every role:** Alpaca-style, `### System:` / `### Instruction:` / `### Response:` (`backend/model_service.py:152-218`). It matches the fine-tuned Mistral's training format (docstring `:14-24`) and is also sent to Qwen models, which expect ChatML.
- **No untrusted-evidence boundary.** Retrieved document text is placed inside `### Instruction:` as `DOCUMENT CONTEXT & EXTRACTED PAGES:` (`backend/model_service.py:206-216`). This violates plan §8.7.
- **Prior turns** are truncated by characters (assistant turns to 400 characters, `backend/model_service.py:173`).
- **The persona is chosen by substrings of the id** ("mig21", "f16", "fighter"…) (`backend/model_service.py:159,182-204`).
- **Fragile stop tokens:** `STOP_TOKENS` include `"###"` (`backend/config.py:63-71`), so any markdown heading `###` in an answer stops generation.

### 4.4 Retrieval ("ColPali visual RAG") *(verified this session)*
- **Indexing:** `visual_rag_service.index_document` parses every page with PyMuPDF. It collects text (≤4000 characters), blocks, images and drawings, plus a schematic keyword flag, and runs RapidOCR when the text is under 30 characters (`backend/visual_rag_service.py:100-167`). It then calls `colpali_retrieval_service.index_document_pages` (`:184-193`).
- **Embedding:**
  - ColQwen2 loads only if `ENABLE_COLPALI_DOWNLOAD=true` (`backend/colpali_retrieval_service.py:118-119`); the default is false.
  - Otherwise page vectors are `np.random.RandomState(hash(text[:100]+seed))`, 16×128 random normals plus word-hash bumps (`backend/colpali_retrieval_service.py:136-159`).
  - Query vectors are one-hot `hash(word) % 128` (`:161-176`).
  - Python's `str` hash is **salted per process** (PYTHONHASHSEED), so vectors stored in `qdrant_db` in one process don't match query vectors built in another.
- **Reproduction:** `search_visual_pages('mig21bis', 'engine fire emergency procedure', top_k=5)` run in three fresh processes against the same index returned
  - `[175, 181, 300, 257, 328]`
  - `[195, 240, 310, 70, 173]`
  - `[214, 215, 131, 20, 21]`

  with `model_loaded=False` every time. **Retrieval is effectively random across restarts.** This is plan pitfall §11.8 ("fake embeddings").
- **The keyword fallback never runs** when Qdrant works. `query_points` always returns `top_k` hits whatever their relevance, so the term-overlap fallback (`backend/visual_rag_service.py:237-283`) only runs if Qdrant errors.
- **Scores:** `score*100` is shown to the user; a missing score defaults to 85.0 (`backend/colpali_retrieval_service.py:331`). Test output showed scores of about 300 (multi-vector MaxSim sums), which aren't percentages.
- **Data model:**
  - Collection per document: `colpali_<doc_id>` (`backend/colpali_retrieval_service.py:87`).
  - Point id = page number (`:226`).
  - Payload has no workspace, classification or ACL fields (`:228-237`).
- **Tabular "retrieval":** `search_multi_dataset` keeps a CSV row only if **the whole query string** is a substring of one cell (`backend/universal_ingestion_service.py:232-237`). Natural-language questions never match, so the "Logistics agent" in practice returns either nothing or PDF page results.
- No reranker, no hybrid/BM25, no sufficiency check, no token budget.

### 4.5 "Agents"

| Claimed agent | Implementation | Verdict |
|---|---|---|
| Mission Commander / planner SLM | `_heuristic_dag_fallback` regex → one of 4 templates (`backend/orchestrator_planner.py:137-212`); the docstring says it uses the orchestrator model (`:224-228`) | Deterministic template; no model call |
| DAG dispatcher | Plan nodes collapse to 3 booleans (`backend/agent_orchestrator.py:209-211`); `depends_on` is ignored | Plan is not executed (pitfall §11.6) |
| Visual Schematic agent | Retrieval only (`backend/agent_orchestrator.py:217-227`); the "thought" text claims "Extracted layout coordinates" (`:280`) | No VLM; the claim is untrue |
| Avionics Math engine | Regex + formulas (`backend/agent_orchestrator.py:31-143`); LLM fallback (`:237-256`) | Useful but fabricates (see §6.3) |
| Logistics agent | `search_multi_dataset` (`backend/agent_orchestrator.py:258-263`) | Effectively dead (see §4.4) |
| Command Synthesis | `stream_response(capability="synthesis")` | Real, on qwen2.5:3b |
| Safety & SOP Validator | Status frame + canned thought: "Verified grounding against source material." (`backend/agent_orchestrator.py:406-427`) | **No check at all** |
| Evaluation scorecard | Keyword overlap scaled into [78, 99] (`backend/evaluation_service.py:48-50`) | Misleading (see §6.3) |

- **Tool calling:** none. There's no tool registry, no function-calling schema and no sandbox. Math is the only "tool", and it's called directly.
- **Memory:** none on the server. History is whatever the client resends, capped to `MAX_CONTEXT_TURNS=6` (`backend/config.py:83`; `backend/model_service.py:162`).

---

## 5. Data handling

### 5.1 Ingestion paths and formats
There are two ingestion paths that don't share code:

**A. `POST /api/documents/upload` → `universal_ingestion.ingest_file`** (`backend/universal_ingestion_service.py:83-191`):

| Format | What happens | Indexed for retrieval? |
|---|---|---|
| `.pdf` | Saved to `backend/pdfs/<client filename>`; visual index + Qdrant (`:99-100,123-142`) | yes (fake vectors) |
| `.csv/.tsv/.xlsx/.xls` | Saved to `uploads/`; row count, columns and 5-row preview in the registry (`:144-159`) | only through whole-query substring search |
| `.docx/.doc` | First 8 paragraphs kept as `text_sample` (`:161-170`) | **no** |
| `.json/.geojson` | Top-level type and keys only (`:172-182`) | **no** |
| images | `is_image=True`, nothing else (`:184-186`) | **no** |

**B. `POST /api/documents/session-upload` → `ingestion_adapter.normalize_to_pdf_or_image`** (`backend/ingestion_adapter.py:35-76`). Everything is turned into a PDF and then visually indexed:

| Format | Conversion | Data loss |
|---|---|---|
| PDF | as is (`:78-102`) | — |
| DOCX | LibreOffice `soffice --headless` (`:316-329`), else reportlab rebuild (`:331-390`) | reportlab path: formatting lost; `Paragraph(p.text)` isn't escaped, so reportlab markup in the text is interpreted (`:366`) |
| XLSX | reportlab table report (`:131-168`, `:392-436`) | **Only the first 10 rows of each sheet (`:145`), 8 columns (`:417`), 30 characters per cell (`:421`)** |
| CSV | same report (`:170-203`) | **Only the first 15 rows** (`:180`) |
| Images | PNG copy + thumbnail + single-page PDF wrapper (`:205-243`) | `extracted_text` is the placeholder `"Direct visual image schematic <name>"` (`:241`); OCR happens only later, through the <30-character rule in `index_document` |
| ZIP | `extractall`, then each child processed recursively (`:245-283`) | **No limit on size, entry count or nesting depth.** A zip inside a zip recurses without bound (`:261`). Classic `..` Zip Slip is stopped by `zipfile`'s own name sanitising |
| TXT/MD/LOG/JSON, or anything else | reportlab text PDF (`:285-312`, `:438-459`) | Structure lost (JSON flattened to lines) |

- Not supported: audio, video, PPTX, HTML.
- No malware or format scanning, no MIME sniffing (only the extension, `backend/ingestion_adapter.py:56`), no size limit (the whole file is read into memory, `backend/main.py:174`).
- No structure-preserving records: tables don't stay tables, and there's no EvidenceUnit, provenance or checksum.

### 5.2 Storage

| Data | Location | Notes |
|---|---|---|
| Registry | `backend/data_repository/document_registry.json` (`backend/universal_ingestion_service.py:31,45-50`) | Global, rewritten on every change, no locking. Entries are keyed by filename stem, so a second upload with the same stem overwrites (`:96,188`) |
| Original files | `backend/pdfs/`, `backend/data_repository/uploads/` (`backend/config.py:75,78`) | Filenames come from the client (see §6.5) |
| Page renders | `backend/data_repository/page_images/<doc_id>/` (`backend/visual_rag_service.py:32-42`) | `index_meta.json` cache never expires |
| Vectors | Embedded Qdrant `backend/data_repository/qdrant_db` | **If the on-disk lock is held, it silently falls back to `QdrantClient(":memory:")`** (`backend/colpali_retrieval_service.py:73-77`), so indexes disappear on restart and the database has split into two copies |
| Traces | `backend/data_repository/traces/trace_<uuid>.json` (`backend/langsmith_service.py:80-86`) | Full query + response + plan; unbounded growth |
| Session docs | `backend/main.py:186-200` writes directly into `universal_ingestion.documents` | Hard-coded `created_at: "2026-08-31"` (`:198`); `ingest_file` also hard-codes `"2026-08-30"` (`backend/universal_ingestion_service.py:119`) |

### 5.3 Multi-tenancy, permissions and audit
- **Workspaces:** none. `session_id` only prefixes `doc_id` (`backend/main.py:166-168`). `/api/documents/list` returns every document to every caller (`backend/main.py:122-124`), and any `doc_id` can be read, rendered or downloaded.
- **Permissions:** none. There is no user, role or classification concept anywhere.
- **Audit:** none. Trace files (`backend/langsmith_service.py`) are debugging records, not an append-only, attributable audit log. They have no user, no workspace and no failure category, they contain raw text, and anyone can read them through `/api/prompts/inspect`.

---

## 6. Quality

### 6.1 Baseline test run *(verified this session)*
There is no test configuration. The test files sit next to the code in `backend/`, and they **write into git-tracked `backend/data_repository/`**:
- `backend/test_ingestion_adapter.py:17,35,49` (adapter scratch)
- `backend/test_multiagent_system.py:103-118` (traces)
- Qdrant collections

To avoid changing the repo, the suite was run against an rsync copy of `backend/` in a scratch directory. The copy left out `venv/`, `models/` and `.env`, so there was no LangSmith key and no cloud upload. It used the system Python, because the venv lacks pytest, qdrant_client and colpali_engine.

```
cd <scratch>/backend
env -u LANGCHAIN_API_KEY -u LANGSMITH_API_KEY HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  python3 -B -m pytest -p no:cacheprovider -rA -q
```

**Result: 2 failed, 8 passed, 1 warning in 7.65 s** (pytest 9.0.2).

| Test | Result | Why |
|---|---|---|
| `test_ingestion_adapter.py::test_csv_ingestion` | PASSED | |
| `test_ingestion_adapter.py::test_image_ingestion` | PASSED | |
| `test_ingestion_adapter.py::test_zip_ingestion` | PASSED | |
| `test_multiagent_system.py::test_universal_ingestion` | PASSED | only asserts the registry isn't empty (`backend/test_multiagent_system.py:29`) |
| `test_multiagent_system.py::test_visual_rag` | PASSED | asserts `len(results) > 0`, which is always true with fake vectors (`:52`) |
| `test_multiagent_system.py::test_avionics_math` | PASSED | asserts `is not None` *after* the result has already been used (`:62-63`) |
| `test_multiagent_system.py::test_evaluation_service` | PASSED | asserts `>= 75`, below the hard floor of 78 |
| `test_multiagent_system.py::test_langsmith_service` | PASSED | writes a trace file |
| `test_model.py::test` | **FAILED** | `OSError: We couldn't connect to 'https://huggingface.co'`. It needs the Hub (`backend/test_model.py:9-15`); it has no assertions |
| `test_multimodal_pipeline.py::test_pipeline` | **FAILED** | `async def functions are not natively supported` (no pytest-asyncio). It also needs Ollama |

`backend/test_syllabus_query.py` has no `test_*` function, so it isn't collected; it's a manual script.

Most passing tests can't fail against the defects described in this document. In plan §11's words, they are "VERIFIED (mock/fallback)", not real verification.

**Frontend:** no tests, no linter, no type checking. `npm run build` was **not** re-run this session.

### 6.2 Lint and type errors
No linter is configured or installed (ruff and ESLint are missing). There are no type hints at module boundaries beyond the basics. The issues below were found by reading the code.

### 6.3 Reproduced defects *(verified this session)*

| # | Defect | Repro | Location |
|---|---|---|---|
| D1 | Retrieval differs on each restart | 3 processes, same query → 3 disjoint top-5 lists (§4.4) | `backend/colpali_retrieval_service.py:142,154,169` |
| D2 | Math engine invents numbers | `calculate("what is the fuel consumption of the engine")` → `• Endurance = 2800.0 kg / 58.0 kg/min = 48.3 minutes` | `backend/agent_orchestrator.py:91-106` |
| D3 | Wrong unit parsing | `calculate("mach 2 for 5 minutes")` → `TAS = Mach (2.0) × a(5.0m) = 2450.0 km/h` ("5 m…" read as an altitude) | `backend/agent_orchestrator.py:73` |
| D4 | Over-broad math trigger | `"time"`, `"speed"`, `"range"`, `"kg"` trigger the math path (`backend/agent_orchestrator.py:40-60`); the LLM fallback then "calculates" ordinary questions | `backend/agent_orchestrator.py:237-256` |
| D5 | Evaluator floor | empty response → `faithfulness 78, overall_confidence 78.6`; "The moon is made of cheese." → `faithfulness 78` | `backend/evaluation_service.py:50` |
| D6 | Safety rubber stamp | every non-emergency query → `safety_compliance: "VERIFIED_SAFE"`, score 98 | `backend/evaluation_service.py:69-71` |
| D7 | Verifier does nothing | always emits "Verified grounding against source material." | `backend/agent_orchestrator.py:410-427` |
| D8 | Silent model substitution | configured models aren't installed → 404 → `qwen2.5:3b` | `backend/model_service.py:385-390` |

### 6.4 Other bugs found by reading the code
- **Double generation.** For Ollama, `client.post(...)` with `"stream": True` reads the *entire* response, which is a full generation, only to check for 404. It then calls `client.stream(...)` and generates again (`backend/model_service.py:380-396`). Every LLM call costs about 2×. At about 9 tok/s on this CPU (B1), that adds roughly 30 s per answer.
- **`OLLAMA_HOST` ignored** in the health check (`backend/model_service.py:79`).
- **Unhandled load failure.** `load_model` re-raises inside a fire-and-forget task (`backend/model_service.py:55-58`; `backend/main.py:47`), so the exception is unhandled, and `is_loaded` stays false for good with no retry.
- **Wrong page used for citation scoring.** `primary_page` defaults to 1 and is fed to the evaluator's citation check (`backend/agent_orchestrator.py:272,436`).
- **Shared stop token cuts answers.** `STOP_TOKENS` includes `"###"` (`backend/config.py:68`), which ends any answer that uses a markdown H3.
- **Slow page fetch.** `get_page_image_base64` needs the PNG rendered; for pages that only have a thumbnail it returns `None`, so they're silently skipped (`backend/visual_rag_service.py:285-289`).
- **Collisions.** `doc_id` comes from the filename stem only (`backend/universal_ingestion_service.py:96`), so two files named `report.pdf` overwrite each other.
- **Wrong cache key.** `ingest_file` stores PDFs under `pdfs/<filename>`, but `index_document` caches by `doc_id` and returns the cached index if it exists (`backend/visual_rag_service.py:87-98`). Re-uploading a changed file with the same name keeps the stale index.
- **`setup.sh` overwrites `.env`** with `.env.example` (`setup.sh:12`).

### 6.5 Security smells

| Severity | Issue | Location |
|---|---|---|
| **High** | **Path traversal write.** The client-controlled `filename` is joined into the destination (`pdf_dir / filename`, `uploads_dir / filename`), so a multipart filename such as `../../main.py` overwrites server files | `backend/universal_ingestion_service.py:99-105` |
| **High** | Same issue in session upload: `f"{doc_id}_{file.filename}"`, where `file.filename` may contain `/..` components | `backend/main.py:167-176` |
| **High** | No authentication or authorisation on any route; CORS `*` with credentials | `backend/main.py:59-65` |
| High | Unbounded ZIP recursion and size (zip bomb, nested zips) | `backend/ingestion_adapter.py:253-264` |
| High | Prompt injection: document text in instruction position; client-supplied assistant history trusted | `backend/model_service.py:206-216`; `backend/main.py:320` |
| Medium | In-band SSE control frames can be spoofed by model or document text | §3.4 |
| Medium | `/api/prompts/inspect` exposes every trace (queries, responses) | `backend/main.py:298-304` |
| Medium | Cloud egress: LangSmith upload of query and response | `backend/langsmith_service.py:89-100` |
| Medium | `trust_remote_code=True` on model load | `backend/model_service.py:121,137` |
| Medium | `/api/documents/{doc_id}` returns the server's absolute `file_path` | `backend/main.py:127-132` |
| Medium | Frontend: markdown images `![](https://…)` from model output render as `<img>`, an exfiltration channel through injected documents; no `img`/`a` override | `frontend/src/components/MessageBubble.jsx` (markdown components, about `:117-176`) |
| Medium | Frontend egress: Google Fonts; Web Speech recognition (Chrome sends audio to Google); possibly network TTS voices | `frontend/index.html:7-8`; `frontend/src/components/VoiceController.jsx:20-31` |
| Low | `serve_pdf` sends `Cache-Control: public` for possibly sensitive documents | `backend/main.py:282-284` |
| Low | Ollama `:cloud` models are reachable through the local daemon; there's no allow-list of model names | §2.3 |
| Info | `backend/.env` is committed. Keys are currently empty, and the git history has none (checked every commit that touched it); `.gitignore` doesn't exclude it | `.gitignore` |
| Info | No unescaped HTML in the frontend: no `dangerouslySetInnerHTML`, and react-markdown runs without `rehype-raw` | frontend audit |

### 6.6 Performance hotspots
1. Double Ollama generation (§6.4): about 2× latency on every call.
2. `num_ctx: 2048` hard-coded (`backend/model_service.py:373`) causes silent truncation, which hurts quality rather than speed.
3. PyMuPDF reopened per retrieved page while building context (`backend/agent_orchestrator.py:347-352`). Indexing a 330-page manual runs synchronously and blocks the event loop when triggered from upload handlers (§3.2).
4. Base64 thumbnails sent inline in every `VISUAL_REF` SSE frame (`backend/agent_orchestrator.py:287-295`; `backend/colpali_retrieval_service.py:323-329`). Page images are re-encoded to JPEG per request (`backend/visual_rag_service.py:285-300`).
5. The frontend polls `/api/model/status` every 4 s forever (`frontend/src/components/TopBar.jsx:36`).
6. The registry JSON is rewritten in full on every change (`backend/universal_ingestion_service.py:45-50`).
7. CSV/XLSX files are re-read from disk with pandas on every "logistics" query (`backend/universal_ingestion_service.py:228-230`).

### 6.7 Dead code
- `UniversalIngestionService.ingest_file` imports `shutil`, which is never used (`backend/universal_ingestion_service.py:17`). There are several unused imports across modules (`re`, `uuid`, `asyncio` in places).
- `PDFService.text_cache` is never used (`backend/pdf_service.py:37`). `get_aircraft_info` is never called (`:80-83`).
- `IngestionAdapter.session_docs` is never used (`backend/ingestion_adapter.py:33`).
- The `ENABLE_MULTI_AGENT=false` single-stream path (`backend/main.py:329-339`) is untested.
- Frontend:
  - `StatusBadge.jsx` is never imported.
  - The "Compiling…" bubble can never render.
  - Unused CSS classes `.cursor-blink`, `.glow-orange`, `.glass-panel`, `.step-block`, `.step-number` (`frontend/src/index.css`).
  - Props `onSelectAircraft` and `onOpenInspector` are passed but never used (frontend audit).

### 6.8 Repo hygiene (`git ls-files`, 10,167 tracked files)

| Committed artifact | Count / detail |
|---|---|
| `frontend/node_modules/` | 9,959 files |
| `frontend/dist/` | 5 build outputs |
| `backend/__pycache__/` | 12 `.pyc` files (committed before the ignore rule) |
| `backend/.env` | 1 (keys empty) |
| `backend/data_repository/` | 128 files: 80 page images, 28 traces, 8 Qdrant files (including `.lock`), 8 test leftovers, the registry |
| Uploaded user PDFs | 3, which look personal (an internship assessment, a hackathon document, and a named person's question paper `…yash_flt_2026gs_qp…`) |
| `backend/pdfs/` | `mig21bis.pdf` and `DCS MiG-21bis Guide.pdf` are the **same blob** (about 69 MB, probably a third-party DCS game manual, so a licensing question), plus `DA_2026_Syllabus.pdf` |

The 5-line `.gitignore` covers only `backend/models/`, `backend/venv/`, `*.safetensors`, `__pycache__/` and `*.py[cod]`.

### 6.9 Benchmark validity (`bench/`)
- **B1** (`bench/b1_per_model.py`): its "p95" is the 4th of 5 samples, and "warm TTFT" is a single sample. The numbers are still useful as rough CPU baselines:

| Model | tok/s | cold load | Ollama RSS |
|---|---|---|---|
| qwen2.5:3b | 9.11 | 2.1 s | 2.2 GB |
| gemma4:e4b | 5.06 | 5.2 s | 10.3 GB |

- **B4** (`bench/b4_router_accuracy.py`) tests a regex *copy* of a router function that no longer exists in that form. Its 72% (36/50) doesn't measure `orchestrator_planner.py`, and its "100% injection" counts FACTUAL as correct.
- **B10** (`bench/b10_sovereignty.py`) hard-codes `air_gapped: True` while its own `ss` snapshot shows external :443 connections. The snapshot is system-wide, it doesn't run a query, its secret detector flags `MAX_NEW_TOKENS`, and it would write the first 4 characters of any real secret into its results JSON.
- **`bench/gold.jsonl`** is one JSON document, not JSONL. Its 50 items are all `verified: false` with `source_page: null`, and some expected answers are copied from the math engine's own constants (circular).
- **B2 and B5** have no results committed.

---

## 7. UI/UX

### 7.1 Look and feel
- Dark "tactical HUD" aesthetic: navy/orange, monospace everywhere, radar scanline animation.
- Fixed two-column layout: chat `w-[45%]` (`frontend/src/components/ChatPanel.jsx:100`) beside the PDF viewer.
- The copy is still military: "Defense Intelligence Platform", "Suggested Tactical Inquiries", "Mission Commander SLM", "OPERATIONAL CAUTION". This contradicts `FRONTEND.md`'s plain-language plan.

### 7.2 Design system
- **Tokens:** only in `frontend/tailwind.config.js`:
  - colours `navy` (800/700/600/500), `orange` (DEFAULT/light/dark), `slate.panel/border`, `success`, `danger`, `warning`
  - fonts `mono` and `sans`
- **Missing:** no CSS variables, no spacing, radius or type-scale tokens. **No light theme** (`color-scheme: dark` in `frontend/src/index.css`).
- **Classes used but undefined** (they silently do nothing):
  - `navy-900` / `navy-750`: 15 occurrences
  - `animate-in` / `fade-in` / `slide-in-from-*`: about 10 places; these need `tailwindcss-animate`, which isn't installed (`plugins: []`)
- **Raw hex backgrounds** bypass the tokens (for example `bg-[#0a0d12]`, `frontend/src/App.jsx:56`).
- **No shared primitives:** modal shells, close buttons and spinners are copy-pasted.

### 7.3 Contrast (computed WCAG ratios, from the frontend audit)

| Text on background | Ratio | AA (4.5:1) |
|---|---|---|
| gray-500 on navy-800 | 3.91 | fail |
| gray-500 on navy-600 | 3.15 | fail |
| gray-600 on navy-800 | 2.50 | fail |
| white on orange `#e8780a` (primary buttons) | 2.95 | fail |
| white on success `#3fb950` | 2.54 | fail |
| gray-400 on navy-800 | 7.45 | pass |
| orange on navy-800 | 6.42 | pass |

There are 46 uses of 9–10 px text.

### 7.4 Accessibility gaps
- The chat textarea has no label.
- The three modals have no `role="dialog"`, `aria-modal`, focus trap, Escape-to-close or focus return.
- The manual dropdown has no `aria-expanded`, listbox semantics or keyboard navigation.
- Document cards are clickable `<div>`s that can't be reached by keyboard.
- **No `aria-live` regions anywhere**, so streamed answers and agent status are never announced.
- Focus styles are removed (`outline-none`) and there's no `focus-visible`.
- The global arrow-key handler calls `preventDefault` on page scrolling outside inputs.
- Enter-to-send doesn't check `isComposing`, which breaks IME input.
- `select-none` on the whole app (`frontend/src/App.jsx:56`) stops users copying answers.
- No `prefers-reduced-motion` handling.
- Touch targets are under 44 px.

### 7.5 Responsiveness
- Only 5 responsive classes exist in the whole app.
- The 45/55 split never stacks, so the app is unusable on phones.
- Modals use fixed `h-[88vh]`, `w-[45%]` and `grid-cols-3`.
- The Settings/Inspector and Manuals buttons are hidden on small screens.

### 7.6 Internationalisation
None. All strings are hard-coded English, `lang="en"`, and speech recognition is fixed to `en-US` (`frontend/src/components/VoiceController.jsx:31`). There is no right-to-left support and no Indic fonts.

### 7.7 Empty, loading and error states
- **Present:** app boot spinner, chat welcome screen, PDF placeholder, loading and error panels, upload spinner, trace loading.
- **Missing:**
  - `/api/aircraft` failure (silent).
  - Empty manual list.
  - Document-manager list error and loading.
  - Inspector error (a failed fetch reads as "Select a trace…").
  - Model-status errors swallowed (the UI just shows "Offline").
  - No "select a manual first" hint.
  - No "speech not supported" hint.
- **Invented values shown as real:**
  - `EvaluationScorecard` defaults `faithfulness_score = 85` and citations to 95 (`frontend/src/components/EvaluationScorecard.jsx:17-18`).
  - An unconditional "RAG INDEXED" badge and a fallback of 330 pages in the document manager.
  - "Sources checked ✓" always shown.

### 7.8 Frontend bugs (from the frontend audit)
1. **Chat does nothing until a manual is selected.** `sendMessage` returns when `!aircraftId` (`frontend/src/hooks/useChat.js:28`), the initial selection is `null`, and the input is still cleared.
2. **The chat can get stuck streaming.** If the stream ends without `[DONE]`, `isStreaming` is never reset (`frontend/src/hooks/useChat.js` read loop). Aborted requests leave a stuck placeholder.
3. **Voice input restarts on every render.** The effect depends on `[onTranscript]` (`frontend/src/components/VoiceController.jsx:82`), and ChatPanel passes a new arrow function each render, so dictation dies after the first result.
4. **Inline code renders as `<pre>`.** react-markdown 10 no longer passes `inline`, which produces invalid DOM.
5. **Upload options are never shown.** The category, name and description state has no inputs, so every upload is sent as `AIRCRAFT_MANUAL`.
6. **Smaller issues:**
   - An `[ERROR:]` message is overwritten by later tokens.
   - SSE parsing ignores CRLF line endings and multi-line `data:` fields.
   - The lightbox breaks when only a thumbnail exists.
   - A stale closure in `fetchDocs`.
   - The page-highlight timer is never cleared.

---

## 8. Documentation inventory

| Doc | Nature | Status |
|---|---|---|
| `README.md` | Feature claims + quick start | Overstates the implementation (§1.3) |
| `MIGRATION.md` | Phased generalisation roadmap with open questions | Phase 1 marked done; 2–8 open. Useful rationale; overlaps strongly with the implementation plan |
| `FRONTEND.md` | UI copy and design-token plan | Not implemented |
| `conversation.md` | Log of user instructions and the assistant's build summaries | Records the "fully local, no online connection" requirement (`conversation.md:48-50`) and claims that don't hold (§1.3) |
| `bench/FIX_PROPOSALS.md` | Self-review proposing (a) fail-closed model resolution, (b) a real verifier call, (c) real ColPali embeddings | Accurate; none applied |
| `backend/models/README.md` | Model card | Inconsistent base model and repo id (§2.3) |
| ADRs, `CLAUDE.md`, `doc/01-status/PROJECT_STATE.md`, architecture docs | — | **None exist** |
| TODO / FIXME / XXX / HACK markers | — | **None** in the backend, frontend source or docs |

---

## 9. What could not be verified this session
- **GPU paths:** CUDA, ROCm and Apple Metal/MPS, including ColQwen2 on a GPU and transformers fp16. This machine has no discrete GPU.
- **Real ColQwen2 retrieval:** it needs `ENABLE_COLPALI_DOWNLOAD=true` and a network download of about 3 GB, which wasn't done to avoid egress.
- **`test_model.py`:** needs the HF Hub or a configured local path. **`test_multimodal_pipeline.py`:** needs pytest-asyncio or a manual run with Ollama models loaded. Neither was run successfully.
- **End-to-end `/api/chat/stream`** against a running server. The pipeline was analysed from the code and from component-level repros, not run as a server.
- **The frontend** wasn't built or run (`npm run build` / `vite`). The UI analysis comes from reading the code.
- **The llama.cpp/GGUF path:** `llama_cpp` isn't installed in either environment, so it wasn't exercised.
- **LibreOffice DOCX conversion:** `soffice` isn't installed here, so only the reportlab fallback path would run.
- **Path traversal** was confirmed by reading the code. No exploit was executed against a live server.
- **Licensing** of the MiG-21 / DCS manual and the provenance of the fine-tuned model.

---

## 10. Top 10 findings (ranked)

1. **Retrieval is effectively random.** ColQwen2 never loads, and the fallback vectors are seeded by Python's per-process salted `hash()`. The same query gave three different top-5 page sets in three processes (`backend/colpali_retrieval_service.py:118,142,154`).
2. **The "multi-agent" pipeline is mostly cosmetic.** The planner is a keyword template (`backend/orchestrator_planner.py:229`), the DAG is never executed (`backend/agent_orchestrator.py:209-211`), and the Safety/SOP validator is a canned string (`:406-427`).
3. **The evaluation scorecard can't report failure.** Its faithfulness floor is 78% (an empty answer scores 78.6% confidence), it gives a blanket "VERIFIED_SAFE", and the UI adds defaults of 85/95 (`backend/evaluation_service.py:50,70`; `frontend/src/components/EvaluationScorecard.jsx:17-18`).
4. **Model configuration silently ignored, plus a silent-substitution code path.** The per-role `.env` models were never applied (every role ran on `qwen2.5:3b`). Separately, a 404 fallback would have swapped any missing model for `qwen2.5:3b`; QW1 removed it. No VLM ever runs, because images are dropped for the text-only model (`backend/model_service.py:357,385-390`).
5. **Path-traversal file write** through the upload filename, on a server with no authentication and `CORS *` with credentials (`backend/universal_ingestion_service.py:99-105`; `backend/main.py:59-65,172`).
6. **The math engine invents numbers** from hard-coded defaults (2800 kg, 58 kg/min) and misparses units ("5 minutes" read as 5 m) (`backend/agent_orchestrator.py:73,92-98`).
7. **Egress contradicts the stated "no online connection" requirement.** LangSmith cloud uploads, Google Fonts, the Web Speech API, HF Hub downloads, and reachable Ollama `:cloud` models (`backend/langsmith_service.py:89-100`; `frontend/index.html:7-8`; `frontend/src/components/VoiceController.jsx:20-31`).
8. **Ingestion loses data and structure.** CSV keeps 15 rows, XLSX 10 rows × 8 columns × 30 characters; DOCX/JSON/images aren't indexed through the main upload path; the table search is effectively dead. There's no workspace isolation, no permissions and no audit log (`backend/ingestion_adapter.py:145,180,417-421`; `backend/universal_ingestion_service.py:232-237`).
9. **Every Ollama call generates twice** (a non-streamed then a streamed request), and `num_ctx` is hard-coded to 2048, so prompts are truncated silently (`backend/model_service.py:373,380-396`).
10. **The baseline tests can't catch these defects.** The result is 8 passed / 2 failed, and the assertions are tautological (`backend/test_multiagent_system.py:52,62,98`). The tests write into tracked data, the venv can't run the app, and the repo commits about 10k `node_modules` files, `.env`, data and personal-looking PDFs.
