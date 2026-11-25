# Architecture Decision Records — AeroMind 2.0

Template: PROJECT-IMPLEMENTATION-PLAN.md §16.2. ADRs amend or clarify the plan (authority order PLAN §3.1).

**Rules:**
- Never edit an Accepted ADR. Supersede it instead.
- Open items are never resolved silently.

| ADR | Title | Status | Proposed decision |
|---|---|---|---|
| [0001](0001-canonical-source-of-truth.md) | Canonical source of truth and profile scope | Accepted | The plan is canonical, legacy docs are rationale. Local-only profile (zero egress), air-gapped target, hardware tiers integrated |
| [0002](0002-requirements-authority.md) | Requirements authority | Accepted | Plan + EXECUTION_PLAN + task acceptance criteria are the spec. MIGRATION.md phases are mapped in as rationale |
| [0003](0003-orchestration-substrate-langgraph.md) | Orchestration substrate | Accepted | A LangGraph 1.2.11 StateGraph wraps the existing workers. The SSE contract is kept through an adapter. Checkpointer SQLite→Postgres |
| [0004](0004-vector-layer-qdrant-hybrid.md) | Vector layer | Accepted | Qdrant hybrid: a plan-conformant text-chunk collection plus an optional real-ColPali page index. Fake vectors are removed. Interim embedding model nomic-embed-text |
| [0005](0005-model-registry-schema-extension.md) | Model registry schema extension | Proposed | Extend models.yaml (quant, latency, quality, tool_calling, tier, prompt_profile, tier blocks) and add new tags. Reject `:cloud` and non-loopback endpoints. Fail closed. Add MODEL_ESCALATION |
| [0006](0006-observability-local-first.md) | Observability | Proposed | Local JSONL audit + OTel local collector. LangSmith removed, or dev-only. Traces endpoint ADMIN-only |
| [0007](0007-device-aware-hardware-tiers.md) | Device-aware hardware tiers | Proposed | A startup probe selects cpu_lite/gpu_standard/gpu_high/gpu_multi/apple_full through config only. Safety and the embedding model are tier-invariant |
| [0008](0008-graph-store-architecture.md) | Knowledge Graph store architecture | Accepted | In-process SQLite-backed graph store for entity and relation storage. Strict workspace_id isolation, zero external dependencies, recursive CTE traversal |
| [0009](0009-audio-asr-engine.md) | Local offline ASR audio ingestion engine | Accepted | faster-whisper CTranslate2 offline speech recognition with deterministic acoustic fallback and timed speaker turns |
| [0010](0010-reranker-and-hybrid-retrieval.md) | Hybrid multi-signal retrieval and cross-encoder reranker | Accepted | 3-way RRF fusion (vector + keyword + graph) with bge-reranker-v2-m3 cross-encoder rescoring |
| [0011](0011-multimodal-video-voice-roadmap.md) | Multimodal Roadmap — Video and Voice Strategy Post-V1 | Accepted | Keyframe extraction for video on GPU tiers; faster-whisper local ASR; zero-egress offline voice synthesis |
