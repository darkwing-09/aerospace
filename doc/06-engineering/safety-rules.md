# Safety Rules: Pre-Action Checklist (AeroMind)

These rules come from PROJECT-IMPLEMENTATION-PLAN.md §16.4 and §3.2, with rules added for this repository. Read them before any change.

## Generic rules (plan §16.4)
- **Before editing an existing file:**
  - Is it a source doc or ADR (`PROJECT-IMPLEMENTATION-PLAN.md`, `doc/07-decisions/adr/*`)? Then you need the user's approval in this session.
  - Is it a load-bearing file, meaning the router (`backend/router/*`, and today `backend/model_service.py` / `AGENT_MODEL_MAP` in `backend/config.py`), the orchestration state or graph (`backend/orchestration/*`, and today `backend/agent_orchestrator.py`), or the tool registry? Then re-read the file and its tests, and call the change out at the next checkpoint.
  - Is it an existing AeroMind feature? Wrap or adapt it. Don't delete or rewrite it without approval.
- **Before adding a dependency:** check that it isn't already present. If it's new, write an ADR first covering why, the alternatives, and the cost of removing it later.
- **Before marking a task done:** did I run its test this session? Does it meet the task's specific acceptance criteria? Is `doc/01-status/PROJECT_STATE.md` updated?
- **Before claiming something works:** have I run it? If I couldn't, say so explicitly.
- **When a test fails:** find the real root cause and fix the problem, not the test. Never comment a test out, weaken an assertion, add a skip, or swallow an exception.
- **When requirements conflict:** stop, quote both statements with their sources, and wait.
- **Expensive-to-reverse decisions** need a checkpoint, not a passing mention. These are the DB schema, the Qdrant payload schema, the embedding model and the graph DB.
- **Never resolve an open question from plan §12, or conflicts C1–C8, silently.** Ask the user.

## AeroMind-specific rules
1. **Never run tests or scripts that write into the tracked `backend/data_repository/`.** Several of the existing tests write into it (`test_ingestion_adapter.py`, `test_multiagent_system.py`), as do the visual RAG index and the trace writer. Use a temp copy, or the `tmp_path` redirection in `tests/conftest.py` once QW7 is done. After any test run, `git status --porcelain` must show no changes under `backend/data_repository/`.
2. **No `:cloud` Ollama models.**
   - This host's Ollama lists `glm-5.1:cloud`, `glm-5:cloud` and `kimi-k2.5:cloud`. Those calls go to a remote service.
   - Never reference them in `.env`, `config/models.yaml`, the benchmarks or ad-hoc commands. Never pass them to `ollama run`.
   - The registry must reject them at load time (EXECUTION_PLAN 2.5).
3. **Never upload real or sensitive data to LangSmith or any other hosted service.**
   - LangSmith may only be used with the dev profile, on synthetic data, and with an explicitly set key (ADR-0006).
   - Under `ZERO_EGRESS_MODE=true` it must be impossible to use.
   - The same applies to Hugging Face Hub downloads during runtime or tests: set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.
4. **Don't commit `.env` or any secret.**
   - `backend/.env` is tracked today, though with empty keys and a clean history. Never add a real key to it.
   - Secrets belong in an untracked file or a secrets store, referenced by name.
   - Don't put tokens in CLI arguments, because they end up in shell history (`download_model.py` does this today).
   - Never print secret values in logs, audit details, benchmark output or reports. Redact to a 4-character prefix at most, or omit them entirely.
5. **Never present a fallback, template or heuristic output as verified.**
   - Today these all look like real results but aren't:
     - the random ColPali vectors
     - the evaluator's score floor
     - the canned "safety verification" message
     - the math engine's default numbers
     - the image placeholder text
   - Any new fallback must be marked `degraded`, `PARTIAL` or `UNCERTAIN`, must be visible to the user, and can never PASS the Critic (§11.5).
   - Docs and status reports use the explicit statuses from `doc/01-status/PROJECT_STATE.md`, such as `VERIFIED (mock/fallback)` rather than "works".
6. **Never silently substitute a model.** If the requested capability has no available model, fail loudly (`NoModelForCapability` or `MODEL_FAILURE`), or fail over to the next-ranked model *for the same capability tag* and audit it as `MODEL_FAILOVER`.
7. **Hardware tiers change capacity, never safety.** In every tier, the deterministic Critic layer, permission checks, audit logging, the injection guard and the egress guard stay on.
8. **Upload handling.** File names from clients are untrusted. Join them only through `security/paths.py::safe_join`, a realpath allowlist. Archives are depth- and size-limited, and links are rejected.
9. **Untrusted text in the UI.** Model and document text is never rendered as HTML. Markdown images and links go through an allowlist, and SSE control events are typed rather than in-band.
10. **Data licensing and privacy.** Don't use the three uploaded personal-looking PDFs in `backend/data_repository/uploads/`, or the DCS MiG-21 manual, as test fixtures or eval sets until the user has ruled on them. Fixtures are synthetic or sanitised only.
11. **Don't run destructive git operations without explicit approval:** no history rewrites, force-pushes, or `git rm` of tracked data (QW8 needs a user decision).
12. **Long or expensive runs need user approval.** That includes model pulls, downloading ColQwen2 (~3 GB) and full re-indexing of the 330-page manual. Downloads also count as egress.
