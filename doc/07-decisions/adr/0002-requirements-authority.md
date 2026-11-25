# ADR-0002: Requirements authority (no separate PRD/TRD)
**Status**: Accepted   **Date**: 2026-11-04 (Accepted) / 2026-11-03 (Proposed)

## Context
PLAN §9 task 0.2 asks to "confirm this plan + `tasks/*.md` acceptance criteria are the requirements spec (don't create separate PRD/TRD that will drift)".

AeroMind already has its own phased roadmap in `MIGRATION.md`:
- Phase 0, the baseline: MiG-21 hardcoded, fixed `AGENT_MODEL_MAP`, LangSmith as a cloud dependency (`MIGRATION.md:11-15`).
- Phase 1, marked done (`:26-33`).
- Phases 2–8, all unchecked:

| MIGRATION phase | Content | Lines |
|---|---|---|
| 2 | Citation `doc_id`s | `:50` |
| 3 | VRAM budgeting | `:69-72` |
| 4 | Reranker / BM25 | `:88-90` |
| 5 | Offline `models.lock`, backup, `[ERROR]` events | `:106-110` |
| 6 | Encryption, roles, signed manifests, audit | `:126-129` |
| 7 | Local observability | `:145-146` |
| 8 | New agents / LoRA loop | `:162-165` |

`README.md` and `conversation.md` add claims with no acceptance criteria. Examples: "zero hallucination" math (`README.md:12`) and "faithfulness 78%" (`conversation.md:167-173`). The 78% is an artefact of a floor in `backend/evaluation_service.py:50`, reproduced on 2026-11-03.

## Options considered
**A. Plan + `doc/04-plan/EXECUTION_PLAN.md` + `tasks/phase-N-tasks.md` acceptance criteria are the only spec. `MIGRATION.md` is folded in as rationale.**
- Pro: one source, with falsifiable criteria.
- Con: `MIGRATION.md` checkboxes go stale (they're kept read-only).

**B. Write a new PRD/TRD merging both.**
- Con: a third document that will drift. This is pitfall §11.20.

**C. Keep `MIGRATION.md` as the spec and map plan items into it.**
- Con: it has no acceptance criteria or adversarial gates.

## Decision (Accepted: 2026-11-04)
Option A. `PROJECT-IMPLEMENTATION-PLAN.md` plus `doc/04-plan/EXECUTION_PLAN.md` task acceptance criteria are the authoritative specification. `MIGRATION.md` and `FRONTEND.md` are kept as rationale only, and no separate PRD/TRD will be created (avoiding drift per §11.20).
`MIGRATION.md` phases map onto plan phases as rationale and backlog inputs:

| MIGRATION.md phase | Folded into plan phase / task |
|---|---|
| 0 baseline (`:11-15`) | Phase −1 baseline in `doc/01-status/PROJECT_STATE.md` |
| 1 generalise documents (done, `:26-33`) | preserved; re-verified in Phase 1.2–1.4 |
| 2 citations with `doc_id` (`:50`) | §8.10 evidence rendering, Phase 1.10/1.12 |
| 3 VRAM budgeting (`:69-72`) | §8.2 `vram_gb` + ADR-0005 / ADR-0007, Phase 0.4b |
| 4 reranker / BM25 (`:88-90`) | Phase 3.12 |
| 5 offline lock, backup, `[ERROR]` (`:106-110`) | Phase 2.1 (hashes), §8.18 DR, quick win QW1 |
| 6 encryption, RBAC, signed manifests, audit (`:126-129`) | Phase 1.12, 3.10, Phase 4 |
| 7 local observability (`:145-146`) | ADR-0006, Phase 4.4 |
| 8 new agents / LoRA (`:162-165`) | agents: §6 roster only; LoRA is out of scope (PLAN §1.5 "not a fine-tuning platform"), so it's an owner question |

## Alternatives rejected and why
- **B:** drift.
- **C:** not falsifiable.

## Consequences
- New requirements enter only as plan amendments through ADRs, or as task specs (PLAN §16.3).
- Claims in `README.md` must be re-earned by passing tests before they're restated.
- Files: `doc/04-plan/EXECUTION_PLAN.md`, `tasks/phase-*.md` (to be created); `MIGRATION.md` untouched.

## Open items
- **OI-1:** keep the LoRA fine-tuning loop (`MIGRATION.md:162-165`) at all, given PLAN §1.5?
- **OI-2:** who signs off acceptance criteria per phase (owner only, or owner + domain reviewer)?

## Verification status
- `MIGRATION.md` line references were read on 2026-11-03.
- No acceptance tests exist yet. The baseline is 8 passed / 2 failed (see `doc/01-status/PROJECT_STATE.md`).
