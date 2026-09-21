# AeroMind Platform — Migration & Evolution Roadmap

This document tracks the migration path from the current **MiG-21-bootstrapped prototype** to a **general-purpose, locally-hosted, multi-document tactical RAG platform**. It is organized into phases so work can be picked up incrementally without breaking the existing pipeline.

Each phase lists: **Goal**, **Changes Required**, **Files Touched**, and **Acceptance Criteria**.

---

## Phase 0 — Baseline (Current State)

- Single-aircraft (MiG-21) hardcoded default in frontend.
- Documents ingested only via `/api/documents/upload` (admin-style flow).
- Fixed `AGENT_MODEL_MAP` with no VRAM awareness.
- LangSmith-based tracing (cloud dependency).
- No document versioning, no offline degradation path, no RBAC.

This is the starting point for every phase below.

---

## Phase 1 — Generalize Document Input (Break the MiG-21 Default)

**Goal:** Remove hardcoded aircraft assumption; support arbitrary file types dropped directly into chat.

### Changes
- [x] Add file attachment icon to chat input component (frontend) — accepts PDF, DOCX, XLSX, CSV, PNG/JPG, ZIP.
- [x] Build **ingestion adapter layer** (`ingestion_adapter.py`) that normalizes all formats to PDF/image before hitting `visual_rag_service.py`:
  - DOCX/XLSX → PDF via headless LibreOffice or native Python fallback
  - Images → passed directly to ColPali embedding (skip rasterization)
  - CSV → parsed into structured table, embedded separately
  - ZIP → unpacked, each file routed recursively through the adapter
- [x] Introduce **session-scoped documents**: uploads from chat get an ephemeral `doc_id` tied to `conversation_id`, stored in a separate Qdrant collection (or payload-filtered) from the permanent manual library.
- [x] Change frontend default state: empty chat opens on a neutral prompt ("Upload a manual or select a registered aircraft") instead of pre-loading MiG-21.
- [x] Update `orchestrator_planner.py` intent classification to handle multi-document context (queries referencing "this file" vs. a named registered aircraft).

### Files Touched
`main.py`, `visual_rag_service.py`, new `ingestion_adapter.py`, `orchestrator_planner.py`, frontend chat input component, frontend default route.

### Acceptance Criteria
- Dropping any supported file type into chat produces a working ColPali index within the same session, without touching the admin upload flow.
- Fresh session with no aircraft selected does not reference MiG-21 anywhere in UI copy or default state.

---

## Phase 2 — Multi-Document & Citation Integrity

**Goal:** Support reasoning across multiple loaded documents safely, with correct citations.

### Changes
- [ ] Add `doc_id` to every `[VISUAL_REF]` and `[PAGE_REF]` SSE payload (currently page-number-only — ambiguous once >1 doc is loaded).
- [ ] Add **document versioning**: each manual gets a `revision_id`; re-uploads of a known manual create a new revision rather than overwriting, so old citations remain resolvable.
- [ ] Build a **diff agent** capability (`capability="diff"`) for comparing two revisions or two documents on demand.
- [ ] Extend `evaluation_service.py` citation scoring to validate `(doc_id, page_number)` pairs, not just page numbers.

### Files Touched
`agent_orchestrator.py`, `evaluation_service.py`, `colpali_retrieval_service.py`, Postgres schema (new `document_revisions` table).

### Acceptance Criteria
- A query spanning two loaded manuals returns citations unambiguously attributable to the correct source document.
- Re-uploading an amended manual does not break existing conversation history's citations.

---

## Phase 3 — Hardware-Aware Model Orchestration (Local-Only Advantage)

**Goal:** Make `model_service.py` aware of actual local resource constraints, not just binary "downloaded or not."

### Changes
- [ ] Build a **VRAM budget manager**: query available VRAM before dispatch; decide reuse / fresh load / fallback accordingly.
- [ ] Implement **model residency / warm-pool**: keep 1–2 hot models resident via Ollama `keep_alive`; log swap events and latency to the trace store.
- [ ] Add **quantization tiers** (Q4/Q5/Q8 GGUF) per capability in `AGENT_MODEL_MAP`, selectable via a hardware profile config.
- [ ] Ship 2–3 **hardware profiles** (8GB / 16GB / 24GB+ VRAM) that auto-select which models are enabled at startup.

### Files Touched
`model_service.py`, `config.py`, new `resource_manager.py`, `AGENT_MODEL_MAP` schema extended with quant variants.

### Acceptance Criteria
- On a constrained-VRAM machine, the system automatically degrades to smaller/quantized models instead of failing or thrashing.
- Model swap events are visible in trace output with latency numbers.

---

## Phase 4 — Retrieval Quality Upgrade

**Goal:** Push retrieval precision beyond raw ColPali top-k, using local compute headroom.

### Changes
- [ ] Add a **local reranker stage** (`bge-reranker-v2-m3` or similar) between ColPali retrieval and synthesis.
- [ ] Implement **hybrid retrieval**: combine ColPali visual similarity with local BM25 over extracted text; route strategy by intent classification (schematic-heavy vs. text-heavy pages).
- [ ] Add **graceful degradation**: if Qdrant/ColPali service is unavailable, fall back to BM25-only retrieval rather than failing the DAG node.

### Files Touched
`colpali_retrieval_service.py`, new `reranker_service.py`, new `bm25_fallback_service.py`, `orchestrator_planner.py`.

### Acceptance Criteria
- Reranked top-k measurably improves citation/faithfulness scores on a held-out query set (track before/after in `evaluation_service.py`).
- Killing the Qdrant service mid-session degrades retrieval quality but does not crash the chat stream.

---

## Phase 5 — Offline Resilience & Reproducibility

**Goal:** Guarantee the system runs fully air-gapped and reproducibly, with no silent runtime dependency on the internet.

### Changes
- [ ] Firewall backend containers so no egress happens after initial setup; document exactly which URLs are hit during install.
- [ ] Add a **`models.lock`** file pinning exact model versions/hashes for reproducible offline builds.
- [ ] Build a **local backup/restore CLI** snapshotting `qdrant_db/`, Postgres, and uploaded documents.
- [ ] Add a **structured error SSE event** (`[ERROR:{...}]`) so the frontend shows real failure states instead of a stalled stream on any node failure.
- [ ] Add per-model **health checks** at startup, surfaced via `/api/model/status`.

### Files Touched
`main.py`, new `backup_cli.py`, `docker-compose.yml`, `model_service.py`, deployment docs.

### Acceptance Criteria
- Fresh install on a machine with no internet access (after model pre-pull) runs end-to-end successfully.
- `backup_cli.py restore` reconstructs a working system from a snapshot.

---

## Phase 6 — Security Hardening (Defense-Platform Posture)

**Goal:** Match the security posture implied by the "defense platform" framing.

### Changes
- [ ] Encrypt `qdrant_db/` and uploaded manuals at rest (AES-256).
- [ ] Implement **local RBAC** (viewer / analyst / admin roles) enforced at the FastAPI dependency layer.
- [ ] Add **signed model manifests**: hash-check local GGUF/model files at startup; refuse to load on mismatch.
- [ ] Add an **immutable audit log**: every query, retrieved sources, and model version used, append-only.

### Files Touched
`main.py` (auth dependencies), new `audit_log_service.py`, `resource_manager.py` (manifest verification), Postgres schema (new `audit_log` table).

### Acceptance Criteria
- Tampering with a local model file is detected and blocked at startup.
- Every chat response has a corresponding, queryable audit log entry.

---

## Phase 7 — Observability Without Cloud Dependency

**Goal:** Replace/supplement LangSmith with a fully local observability stack.

### Changes
- [ ] Swap or dual-write traces to a self-hosted alternative (e.g., **Arize Phoenix**) or a custom Postgres-backed trace store.
- [ ] Build a lightweight local **resource dashboard** (Prometheus + Grafana, or a custom panel) showing VRAM usage, per-model latency, and queue depth in real time.

### Files Touched
`langsmith_service.py` (or replacement `trace_service.py`), new `metrics_exporter.py`, `docker-compose.yml`.

### Acceptance Criteria
- All trace/telemetry data is queryable with zero external network calls.
- Dashboard reflects live VRAM/model state during an active chat session.

---

## Phase 8 — New Specialist Agents & Feedback Loops

**Goal:** Extend the agent roster and close the improvement loop over time.

### Changes
- [ ] **Unit-safety agent**: cross-checks metric/imperial consistency in `avionics_math_engine.py` outputs against the source manual's convention.
- [ ] **Checklist/procedure extraction agent**: structured JSON extraction of emergency procedures for a dedicated UI panel.
- [ ] **User feedback loop**: thumbs up/down on responses feeding a correction dataset (mirroring the existing DermAI RLHF pattern).
- [ ] **Local fine-tuning loop**: periodic LoRA fine-tune of the synthesis model on low-faithfulness-score queries (Celery-scheduled, same pattern as DermAI's nightly retrain).

### Files Touched
`model_service.py` (`AGENT_MODEL_MAP` new capabilities), new `feedback_service.py`, new `finetune_pipeline.py` (Celery task), frontend feedback UI.

### Acceptance Criteria
- Emergency procedures render as structured, navigable steps rather than prose.
- Feedback signals are persisted and consumable by a scheduled fine-tuning job.

---

## Suggested Build Order

Given this is a solo/small-team local project, the phases are ordered for maximum leverage per unit effort:

1. **Phase 1** (generalize input) — unblocks everything else; currently the biggest UX blocker.
2. **Phase 3** (VRAM-aware orchestration) — highest "prototype → production" signal, and uniquely valuable *because* it's local.
3. **Phase 4** (retrieval quality) — directly improves answer quality, cheap relative to payoff.
4. **Phase 2** (multi-doc citations) — needed once Phase 1 makes multi-document sessions common.
5. **Phase 5 → 6 → 7 → 8** — harden, secure, observe, extend, roughly in that order.

---

## Open Questions to Resolve Before Starting

- Target hardware floor (minimum VRAM to support) — determines how aggressive quantization tiers need to be.
- Whether session-scoped documents should ever get promoted to the permanent library, and who approves that.
- Whether RBAC needs to support offline user provisioning (no external identity provider, given air-gap requirement).

---

*Last updated: reflects planning discussion as of the current session. Update phase checkboxes as work lands.*
