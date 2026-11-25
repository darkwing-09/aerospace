# Conventions — AeroMind 2.0

This adapts PROJECT-IMPLEMENTATION-PLAN.md §3.6 to this repository. If this file and an Accepted ADR disagree, the ADR wins.

## Language and runtime
- **Python 3.13.** The existing code targets cpython-313, and the plan's reference stack uses 3.13 too.
- **One interpreter for everything.** Until C8 is decided, system `python3` is the only one that can import the app; `backend/venv` is incomplete. Once QW7 lands, the lockfile defines the environment.
- **Frontend:** React 18, Vite 5, Tailwind 3, plain JS/JSX. Moving to TypeScript would need an ADR.

## Backend import style (today) and how new code fits
- **Today:** a flat module layout under `backend/`, imported by bare name from `backend/` as the working directory: `from config import settings`, `from model_service import ModelService`. Module-level singletons hold state (`model_svc`, `visual_rag_service`, `universal_ingestion`, …).
- **Keep it.** Don't rename or move existing modules, because that would break imports, the tests and the bench scripts.
- **New packages** live under `backend/` and are imported the same way, e.g. `from router.router import router`. Each package gets an `__init__.py`.
- **Name clash:** never create a `backend/config/` package, because it would shadow `backend/config.py`. YAML config goes in the repo-root `config/` directory instead. Load it through `Path(settings.BASE_DIR).parent / "config"`, and allow an `AEROMIND_CONFIG_DIR` override.
- **Store instances:** new code receives them through FastAPI dependencies, or by explicit constructor arguments (dependency injection). The API and the pipeline must share the same instances (§11.13). Don't add new module-level singletons for stores.

## Target layout (mapped from plan §8.0)
```
config/                      models.yaml agents.yaml hardware_profiles.yaml thresholds.yaml
                             connectors.yaml prompts/<agent>.yaml
backend/
  main.py                    existing API (kept); new routers mounted via app.include_router
  config.py model_service.py agent_orchestrator.py orchestrator_planner.py
  visual_rag_service.py colpali_retrieval_service.py universal_ingestion_service.py
  ingestion_adapter.py pdf_service.py evaluation_service.py langsmith_service.py   (existing, wrapped)
  agents/                    main_agent.py planner.py execution_agent.py coding_agent.py retrieval_agent.py
                             data_analysis_agent.py multimodal_agent.py critic_agent.py correlation_agent.py
                             memory_agent.py optimization_agent.py
  router/                    router.py health.py hardware_probe.py model_onboarding.py
  orchestration/             state.py graph.py task_graph.py persistence.py prompts.py
  ingestion/                 evidence_unit.py detectors.py chunker.py pipeline.py queue.py scanner.py
                             extractors/{pdf_text,pdf_scanned,image,csv_xlsx,docx_pptx,audio,text,unsupported}.py
  knowledge/                 vector_store.py graph_store.py entity_resolution.py correlation.py embeddings.py
  retrieval/                 context_manager.py reranker.py hybrid.py
  memory/                    store.py scoping.py
  tools/                     registry.py sandbox_exec.py kb_search.py aero_math.py doc_writers/{docx,xlsx,pptx,chart}.py
  connectors/                base.py <one file per connector>.py
  security/                  auth.py permissions.py gateway.py injection_guard.py rate_limiter.py egress_guard.py paths.py
  observability/             audit.py exporter.py tracing.py
  api/                       tasks.py jobs.py artifacts.py audit.py ui.py streaming.py schemas.py
  tests/                     unit/ integration/ adversarial/ fixtures/ conftest.py
eval/                        harness.py metrics.py fixtures/ results/
kits/<vertical>/             prompts/ templates/ fixtures/ eval/      (aviation_mro first)
deploy/                      Dockerfile docker-compose.yml zero_egress.env models.lock.json
doc/                        adr/ conventions.md safety-rules.md adaptation-map.md ...
```
The existing `backend/test_*.py` files stay where they are. Don't move them without approval. New tests go in `backend/tests/`.

## Code rules (from plan §3.6)
- **One responsibility per file.** Each agent gets its own file in `agents/`, and each tool its own file in `tools/`.
- **Agent contract.** Every agent declares:
  - `name`
  - its responsibility, in the module docstring
  - its allowed tools (taken from the registry only)
  - a **capability tag, never a model name**
  - typed input and output (`TypedDict` for state that crosses graph nodes; Pydantic or dataclasses for records)
  - explicit `retry_budget` and `max_steps`, read from `config/agents.yaml`
- **Changeable values belong in `config/*.yaml`:** model choices, per-tier agent enablement, thresholds, prompts (with a `version`), and retry budgets.
- **No environment or tier branches** (`if env ==` / `if tier ==`) in agent code. Profiles and tiers only select config (§5.3, ADR-0007).
- **Use type hints throughout.** Comments explain **why**, not what.
- **Extractors never raise.** They return `Document(status=FAILED, errors=[...])`.
- **Compare enums to enums,** never to string literals (§11.14).
- **Don't build premature abstractions,** except the interfaces the plan requires: identity provider, connectors and model providers.

## Prompts
- Every prompt is assembled through `orchestration/prompts.py::assemble_prompt(instructions, user_request, evidence, history, profile)`.
- Evidence always goes inside `<untrusted_document_evidence source='…'>…</untrusted_document_evidence>`.
- `profile` selects the model's prompt format: `chatml` by default. `alpaca` exists only for the fine-tuned Mistral-7B (C7); it puts evidence in a delimited block, never inside `### Instruction:`.

## Tests
- **Layout:**
  - `backend/tests/unit/`: pure logic, with real fixture files for every extractor.
  - `backend/tests/integration/`: tests that run through the compiled graph or the API (`TestClient`).
  - `backend/tests/adversarial/`: the cases from plan §10.2.
  - `backend/tests/fixtures/`: synthetic or sanitised data only, with a `manifest.json` of sha256 values.
- **Markers** (declared in `backend/pytest.ini`): `needs_ollama`, `needs_docker`, `needs_gpu`, `needs_network`, `slow`. Use markers to *select* which tests run; never add a skip to hide a failure.
- **Isolation:** `tests/conftest.py` redirects every data path (`DATA_DIR`, `UPLOADS_DIR`, `PAGE_IMAGES_DIR`, `TRACES_DIR`, `QDRANT_PATH`) to `tmp_path`. A test run must leave `git status` clean.
- **Command:** `cd backend && python3 -B -m pytest -p no:cacheprovider <path> -q`
- **Coverage rule:** every agent has at least one integration test that runs through the actual graph, and there is one wiring test that spies to check every subsystem is invoked (§11.6).

## API and SSE
- **Keep the existing routes.** The `/api/*` routes and their response shapes stay. New plan routes go under `/api/tasks`, `/api/jobs`, `/api/artifacts`, `/api/audit`, `/api/memory` and `/api/ui/*`.
- **SSE control data moves to typed events:** `event: <type>\ndata: <json>\n\n`. Event types are `agent_activity`, `plan`, `evidence`, `token`, `evaluation`, `approval_required`, `error` and `done`. Each `token` frame carries JSON `{"t": "..."}`, so no model or document text can impersonate a control event.
- **Migration:** the legacy in-band `[TAG:json]` frames stay available behind `?protocol=legacy` until the frontend has migrated (one release).
- **Identity** comes from the validated bearer token only, never from a trusted header.

## Frontend
- **Structure:**
  - Components in `src/components/`.
  - Shared primitives in `src/ui/` (Button, Dialog, Card, Badge, Toast, Skeleton).
  - Hooks in `src/hooks/`.
  - API calls go through one client module, `src/api/client.js`, with the base URL from `import.meta.env.VITE_API_BASE` (default `/api`).
- **Styling:**
  - Colors come from CSS-variable tokens defined in `src/index.css` and mapped in `tailwind.config.js`. Don't hard-code hex values in components.
  - Light and dark themes both work through tokens.
  - Contrast must pass WCAG AA.
  - Respect `prefers-reduced-motion`.
- **Dialogs and live content:** use `role="dialog"`, a focus trap and Esc to close. Streamed text sits in an `aria-live="polite"` region.
- **No external network loads:** fonts are self-hosted, and markdown `img`/`a` go through an allowlist. Never use `dangerouslySetInnerHTML` with model or document content.
- **Strings:** all user-facing text goes through the i18n layer (i18next, ADR), starting with English. Use logical CSS properties so right-to-left layouts work.

## Git
- Keep changes small, and describe each one in one sentence (§3.2).
- Never commit `.env`, model weights, `node_modules`, `dist`, or anything under `backend/data_repository/` (after QW8).
- Commit messages end with the attribution line given in the session's system reminder.
