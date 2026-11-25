# ADR-0001: Canonical source of truth and deployment-profile scope
**Status**: Accepted   **Date**: 2026-11-04 (Accepted) / 2026-11-03 (Proposed)

## Context
AeroMind 2.0 is being turned into a private multi-agent platform following `PROJECT-IMPLEMENTATION-PLAN.md` (repo root; byte-identical to `/home/darkwing/Desktop/workbench/PROJECT-IMPLEMENTATION-PLAN.md`, checked with `diff` on 2026-11-03).

The repo already holds several design documents that overlap and sometimes contradict each other:
- `README.md` advertises LangSmith Cloud tracing (`README.md:26-29`).
- `conversation.md` claims there are "no external API calls" (`conversation.md:184-187`).
- `MIGRATION.md` holds an 8-phase roadmap, with only Phase 1 checked (`MIGRATION.md:26-33`).
- `FRONTEND.md` is a UI copy and design plan, not current state (`FRONTEND.md:3-6`).
- `bench/FIX_PROPOSALS.md` lists three verified defects with proposed fixes.

The plan's authority order is defined in PLAN §3.1. Two scope decisions also govern every later phase.

**1. Profile scope.** PLAN §5.3 (carried over from the reference ADR-0001) requires dual profiles:
> `WORKBENCH_ENV=hf` (or `dev`): hosted endpoints for fast iteration. **Synthetic/sanitized data only.** … `WORKBENCH_ENV=local` (or `prod`): local Ollama/vLLM, zero egress.

The project owner's recorded directive (`conversation.md:50`, Session 3) says:
> "MAKE SURE THE ENTIRE SYSTEM SHOULD BE LOCALLY HOSTED , WITH NO ONLINE CONNECTION !"

These conflict. The plan wants a hosted dev path, while the owner asked for no online connection at all.

**2. Air-gap vs. isolated network.** This is an open question (PLAN §12.2). It affects network policy (PLAN §8.13, §14) and must be resolved before Phase 2 / M4.

## Options considered
**A. The plan is canonical, local-only profile (no `hf` block).**
- Pros:
  - Honours the owner's directive.
  - The dev machine can already run local models: Ollama is installed with qwen3:4b-instruct-2507, qwen2.5-coder:1.5b, qwen3-vl:2b and nomic-embed-text (checked with `ollama list` on 2026-11-03).
  - No hosted credentials to manage.
  - The no-egress test can run from day one.
- Cons:
  - Iteration on the dev laptop (Intel i7-1185G7, iGPU only, no CUDA) is slow. B1 measured qwen2.5:3b at 9.11 tok/s (`bench/results/b1_per_model_AS_IS.json:18`).
  - The PLAN §7.1 invariant "every capability in `hf` is in `local`" becomes trivially true.

**B. The plan is canonical, dual profile (`hf` dev with synthetic data + `local` prod), exactly as PLAN §5.3.**
- Pros:
  - Fast iteration on large hosted models.
  - Matches the reference implementation.
- Cons:
  - Directly contradicts `conversation.md:50`.
  - Creates an egress code path.
  - Needs a strict synthetic-data discipline.
  - HF tokens become secrets to manage. `download_model.py:7` already takes the token as a CLI argument.

**C. The plan is canonical, local-only by default, with an optional `hf` block disabled unless an explicit dev flag is set and the egress guard allows it.**
- Pros: keeps the option open without creating a default egress path.
- Cons:
  - It's still a code path that has to be excluded from production builds (PLAN §2 "exclude, don't disable").
  - It adds test surface.

**D. Keep the legacy docs (`MIGRATION.md`) as canonical and treat the plan as advisory.**
- Pros: no relabelling.
- Cons:
  - `MIGRATION.md` lacks contracts, acceptance criteria and adversarial tests.
  - The owner explicitly asked to follow the plan.

## Decision (Accepted: 2026-11-04)
1. `PROJECT-IMPLEMENTATION-PLAN.md` is canonical, in the PLAN §3.1 authority order:
   1. the plan (`PROJECT-IMPLEMENTATION-PLAN.md`)
   2. `doc/07-decisions/adr/*.md` (Accepted ADRs)
   3. legacy design docs (`README.md`, `MIGRATION.md`, `FRONTEND.md`, `conversation.md`, `bench/FIX_PROPOSALS.md`), as **rationale only**
   4. `doc/04-plan/EXECUTION_PLAN.md`
   5. `doc/01-status/PROJECT_STATE.md`
2. Profile scope: **Option A (local-only profile, zero egress)** is adopted per the owner directive ("MAKE SURE THE ENTIRE SYSTEM SHOULD BE LOCALLY HOSTED, WITH NO ONLINE CONNECTION!").
   - Zero egress is strictly enforced: no `:cloud` Ollama models, no hosted HF calls, no LangSmith cloud tracing, no CDN assets, no external font links.
   - `config/models.yaml` defines the `local` environment only, partitioned into hardware tiers.
3. Air-gap vs. isolated network: Target is **air-gapped local deployment**. Implemented against the zero-egress abstraction with socket-level egress enforcement in tests, offline HuggingFace/transformers flags, and Docker `internal: true` container networking.
4. Hardware tiers: Device-aware hardware tiers per **ADR-0007** (`cpu_lite`, `gpu_standard`, `gpu_high`, `gpu_multi`, `apple_full`) are integrated into the profile rule. Hardware tiers adjust capacity only (parallel calls, plan depth, model sizes); safety gates, embedding determinism, audit logging, and authorization are tier-invariant.

## Alternatives rejected and why
- **D:** it has no falsifiable acceptance criteria.
- **B:** rejected as the default because it contradicts a recorded owner directive. It isn't rejected outright; it's the owner's call.

## Consequences
- Every phase checkpoint is measured against plan acceptance criteria, not `MIGRATION.md` checkboxes.
- If A is chosen:
  - `config/models.yaml` has only `local` (plus hardware-tier blocks, ADR-0007).
  - The §7.1 parity test becomes "every enabled agent's capability resolves in every tier".
  - LangSmith becomes a removal candidate (ADR-0006).
- Cost to change later: going from A to B is cheap (add a block). Going from B to A after hosted-only code paths have crept in is expensive.
- Files affected later: `config/models.yaml`, `backend/config.py` (`LANGCHAIN_ENDPOINT` at `:39`), `backend/langsmith_service.py`, `download_model.py`, `deploy/zero_egress.env`.

## Status of Open Items
- **OI-1:** RESOLVED (2026-11-04): Option A (local-only profile) chosen.
- **OI-2:** RESOLVED (2026-11-04): Air-gapped target, enforced via local-only abstraction, offline flags, and internal-only Docker network.
- **OI-3:** `conversation.md` stays in repo as historical rationale log only.

## Verification status
- Verified this session:
  - Both plan copies are identical (`diff`).
  - Ollama local models are present (`ollama list`).
  - Ollama also exposes `*:cloud` models (glm-5.1, glm-5, kimi-k2.5), which are remote paths through the same daemon. This is relevant to "no online connection".
- Not validated: any egress measurement of the running app. B10's `air_gapped: True` is hardcoded (`bench/b10_sovereignty.py:176`).
