# ADR-0006: Observability — local-first audit and tracing (LangSmith dev-only or removed)
**Status**: Proposed   **Date**: 2026-11-03

## Context
**Cloud tracing.**
- `backend/langsmith_service.py:20-24` sets `LANGCHAIN_TRACING_V2` and the endpoint whenever a key is present.
- `create_run_trace` uploads the query, up to 500 characters of the response, the evaluation and the plan to `https://api.smith.langchain.com` (`:89-98`; endpoint default `backend/config.py:39`).
- That is cloud egress of document-derived content, which conflicts with PLAN §1.4 (privacy, provable) and the owner's "no online connection" directive (`conversation.md:50`).
- Keys are empty today (`backend/.env`, history checked 2026-11-03).

**Local traces.**
- Full-text JSON traces are written to `backend/data_repository/traces/` (`langsmith_service.py:80-86`), and 28 of them are committed to git.
- They're served **unauthenticated** at `GET /api/prompts/inspect` (`backend/main.py:298-304`) and shown to anyone in `PromptInspectorModal.jsx`.

**Missing pieces.** There's no `AuditEvent`, failure taxonomy, secret scrubbing or per-model metrics. `/api/health` reports `langsmith_cloud_enabled` (`main.py:91`).

**What the plan requires.**
- PLAN §7.8 / §8.14: an append-only `AuditEvent`; details hold hashes and counts, never raw text; `scrub_secrets`.
- JSONL and CEF exporters with a high-water mark.
- OpenTelemetry to a **local-only** collector at V1+.

## Options considered
**A. Remove LangSmith.** Local JSONL audit + OTel SDK → local collector (e.g. OTel Collector → local Jaeger/Tempo + Prometheus/Grafana in the compose file).
- Pro: zero egress by construction.
- Con: loses the LangSmith UI. That's acceptable, because an admin dashboard is proposed instead.

**B. Keep LangSmith in a dev profile only, excluded from production builds, and allowed only when the egress guard permits it and data is synthetic.**
- Pro: keeps a familiar tool for dev.
- Con: still a code path to exclude ("exclude, don't disable", PLAN §2). Only meaningful if ADR-0001 picks a dual profile.

**C. Self-host the LangSmith platform.**
- Con: an enterprise licence and a heavy dependency; it's an owner decision.

## Decision (proposed)
Option A by default, with Option B only if ADR-0001 resolves to a dual profile.
- **New modules:**
  - `backend/observability/audit.py`: AuditEvent + JSONL append-only writer + `scrub_secrets`.
  - `backend/observability/exporter.py`: JSONL/CEF with a high-water mark.
  - `backend/observability/tracing.py`: OTel spans per graph node, model call and tool call.
- **`/api/prompts/inspect` becomes ADMIN-only** and workspace-filtered. It returns audit records (hashes and counts), not raw prompts, except in an explicit dev mode.
- `langsmith_service.py` is **wrapped**, not deleted: its `create_run_trace` call site goes through the audit writer, and its cloud branch is compiled out in the local profile.

## Alternatives rejected and why
- **C:** cost and footprint before the MVP.
- **B as default:** contradicts the owner's directive.

## Consequences
- OTel SDK, Collector and dashboards are new dependencies; their versions are pinned in a follow-up ADR when they land in Phase 4.4.
- **Files:**
  - new: `backend/observability/*`, `deploy/otel-collector.yaml`
  - modified: `backend/main.py` (route authz), `backend/langsmith_service.py`, `frontend/src/components/PromptInspectorModal.jsx`
- The committed traces should be untracked (repo hygiene, an owner decision).
- Cost to change later: low for the exporters, high for the AuditEvent schema once the SIEM consumes it.

## Open items
- **OI-1:** audit, scratch and memory retention periods (PLAN §12.13).
- **OI-2:** SIEM target and CEF vendor string.
- **OI-3:** remove LangSmith entirely vs. dev-only (depends on ADR-0001 OI-1).

## Verification status
- The egress code path was confirmed by reading.
- No live network capture was done. B10's verdict is hardcoded (`bench/b10_sovereignty.py:176`), and its socket snapshot is system-wide, not per process.
