# AeroMind 2.0 documentation

Everything written for the AeroMind 2.0 engagement lives here. The folder numbers give the reading order.

```
doc/
├── README.md                               ← you are here (index)
├── 00-start-here/
│   └── PROMPT.md                           ← the single prompt for a coding agent to follow the whole setup
├── 01-status/
│   └── PROJECT_STATE.md                    ← live status: baseline, what's done, test results, blockers. Read first, update last.
├── 02-analysis/
│   ├── PROJECT-ANALYSIS.md                 ← Stage 1: what the project is today (every claim cited file:line)
│   └── adaptation-map.md                   ← Stage 3: project vs. plan, component by component (EXISTS/PARTIAL/MISSING/CONFLICTS)
├── 03-architecture/
│   ├── IMPROVEMENT-PROPOSAL.md             ← Stage 4: UI/UX, features, industries, performance, security, roadmap
│   └── MULTI-SLM-ARCHITECTURE.md           ← Stage 4 §4.4: capability router, hardware tiers, cascade, scheduling, Critic, worked example
├── 04-plan/
│   └── EXECUTION_PLAN.md                   ← task-by-task plan: QW1–QW11, Phases 0–5, acceptance criteria, exact test commands
├── 05-frontend/
│   └── FRONTEND.md                         ← frontend design spec + tickable walkthrough (FE-0 … FE-11, 61 steps)
├── 06-engineering/
│   ├── conventions.md                      ← code layout, naming, tests, SSE event naming
│   └── safety-rules.md                     ← pre-action checklist (never write to tracked data, no :cloud models, …)
└── 07-decisions/
    └── adr/
        ├── README.md                       ← ADR index
        ├── 0001-canonical-source-of-truth.md
        ├── 0002-requirements-authority.md
        ├── 0003-orchestration-substrate-langgraph.md
        ├── 0004-vector-layer-qdrant-hybrid.md
        ├── 0005-model-registry-schema-extension.md
        ├── 0006-observability-local-first.md
        └── 0007-device-aware-hardware-tiers.md
```

## Related files outside `doc/` (they must stay where they are)

| Path | Why it lives there |
|---|---|
| `PROJECT-IMPLEMENTATION-PLAN.md` (repo root) | The canonical implementation plan you supplied. It isn't modified. |
| `.claude/skills/aeromind-frontend/` | Claude Code only loads project skills from `.claude/skills/`. It holds the frontend design rules, tokens, event contract and checklist. |
| `config/hardware_profiles.yaml` | Runtime config read by the backend at startup (hardware tiers). |
| `README.md`, `MIGRATION.md`, `FRONTEND.md`, `conversation.md`, `bench/FIX_PROPOSALS.md` | The original project docs. Kept unchanged, as rationale only (ADR-0001). |

## Status at a glance (see `01-status/PROJECT_STATE.md` for details)

- **Phase −1** (discovery and docs): done and approved.
- **Quick wins**: QW1, QW2, QW3, QW5 and QW11 are implemented. `cd backend && python3 -B -m pytest -p no:cacheprovider tests -q` gives 43 passed.
- **QW4 and QW6–QW10**: waiting on your decisions.
- **Phases 0–5**: not started.
