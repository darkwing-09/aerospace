# ADR-0003: Orchestration substrate — LangGraph StateGraph wrapping existing workers
**Status**: Accepted   **Date**: 2026-11-04 (Accepted) / 2026-11-03 (Proposed)

## Context
Today's orchestration is a hand-rolled asyncio generator, `MultiAgentOrchestrator.execute_query_stream` (`backend/agent_orchestrator.py:150-456`). It has these problems:
- **The planner isn't a model.** It's a keyword heuristic that returns one of four fixed templates, although its docstring claims it is an SLM (`backend/orchestrator_planner.py:137-212`, `:229-230`).
- **The DAG is emitted to the UI but not executed** (`agent_orchestrator.py:192`). Execution is three hard-wired booleans, `run_visual`, `run_math` and `run_logistics` (`:209-211`), passed to `asyncio.gather` (`:266-270`). This is pitfall §11.6, "built but not wired".
- **The "Safety & SOP Verification" agent makes no check.** It emits a canned status and thought (`:406-427`).
- There's no typed state, checkpointer, cancellation, approval interrupt, step cap or retry budget (PLAN §8.1, §11.11).
- The SSE contract `/api/chat/stream` (`backend/main.py:309-356`) uses in-band `[TAG:json]` frames, which the frontend parses at `frontend/src/hooks/useChat.js:95-257`.

PLAN §8.1 specifies a LangGraph `StateGraph` with nodes gateway_context → classify_intent → planner → dispatch → workers → critic → synthesize → task_evaluation → approval_gate → continuation, plus a real checkpointer. PLAN §0.6 says that if the target uses a different orchestration framework, propose an ADR rather than ripping it out. AeroMind uses no framework.

Installed in system `python3` (checked 2026-11-03): `langgraph 1.2.11`, `langgraph-checkpoint 4.2.0`, `langchain-core 1.5.4`. These match the PLAN §13 reference versions. They are **not** in `backend/requirements.txt` or `backend/venv`.

## Options considered
**A. LangGraph `StateGraph`, wrapping the existing workers as node functions.**
- `visual_rag_service.retrieve_visual_context` becomes the multimodal/retrieval node.
- `AvionicsMathEngine.calculate` becomes a deterministic tool.
- `universal_ingestion.search_multi_dataset` becomes a data-analysis tool.
- `model_service.stream_response` goes behind the router.
- An `sse_adapter` translates graph events into today's `[AGENT_STATUS:…]` frames, and later into typed `event:` frames.
- Pros:
  - Plan-conformant: reducers, `interrupt`, checkpointer, reference versions.
  - Existing features are preserved.
  - The streaming UX is unchanged for the frontend.
- Cons:
  - A new major dependency (hence this ADR).
  - LangGraph/LangChain upgrades can change tool-calling (PLAN §13), so they must be pinned.

**B. Keep hand-rolled asyncio and add a DAG executor, checkpoint store, interrupt and cancel ourselves.**
- Pro: no dependency.
- Con: re-implements checkpointing and interrupts; higher bug risk; diverges from the plan's tests and pitfalls.

**C. Another framework (e.g. a CrewAI-style or custom actor system).**
- Con: no plan alignment and no reference tests.

## Decision (Accepted: 2026-11-04)
Option A.
- **Graph location:** `backend/orchestration/graph.py`, with state in `backend/orchestration/state.py` per PLAN §7.3.
- **Checkpointer:** `langgraph-checkpoint` SQLite in dev, Postgres in prod (the Postgres move gets its own ADR).
- **Checkpoint key:** a unique `task_id`, workspace-checked on load.
- **Wrapping:** `execute_query_stream` stays as a thin wrapper that runs the graph and yields through `sse_adapter`. `/api/chat/stream` keeps its request/response shape until the frontend moves to typed events (frontend ADR to follow).
- **Pins:** `langgraph==1.2.11`, `langgraph-checkpoint==4.2.0`, `langchain-core==1.5.4`.

## Alternatives rejected and why
- **B:** rebuilds what LangGraph already provides, the exact area where the reference implementation's pitfalls clustered (§11.1, §11.2, §11.11).
- **C:** no reference contract or tests.

## Consequences
- **Load-bearing change** (PLAN §3.2): it must be called out at the checkpoint where it lands.
- **Files affected:**
  - new: `backend/orchestration/{state,graph,task_graph,persistence,prompts}.py`, `backend/agents/*.py`
  - wrapped: `backend/agent_orchestrator.py`
  - replaced behind a flag: `backend/orchestrator_planner.py` templates become deterministic-first planner rules
  - modified: `backend/requirements.txt` (pins)
- **Wiring test required** (pitfall §11.6): a spy on each subsystem, asserting it is invoked through the compiled graph.
- **Cost to change later:** high once checkpoints are persisted, because the state schema is serialized.

## Open items
- **OI-1:** which interpreter is canonical. `backend/venv` (3.13.12, missing qdrant_client, colpali_engine, reportlab and pytest) or system `python3` (has everything)? Owner decision.
- **OI-2:** the approval authority for `approval_gate` (PLAN §12.4).

## Verification status
- LangGraph imports and versions were confirmed in system `python3` on 2026-11-03.
- No graph has been built or run. Today's orchestrator was observed only through code reading and the baseline tests (8 passed, 2 failed; the orchestrator stream test failed because it's async and no async plugin is installed).
