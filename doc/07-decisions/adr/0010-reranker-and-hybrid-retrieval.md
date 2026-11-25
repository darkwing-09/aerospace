# ADR-0010: Hybrid Multi-Signal Retrieval and Cross-Encoder Reranker
**Status**: Accepted   **Date**: 2026-11-04

## Context
Pure vector embedding search in complex aerospace engineering manuals exhibits well-known limitations:
1. Exact technical alphanumeric codes (e.g. `P-104`, `RP-22`, `SPS-141`) get buried under broad semantic matches.
2. Procedural dependencies and multi-hop correlations (e.g. a valve referencing a maintenance SOP step) are invisible to vector-only distance.
3. Dense bi-encoder embeddings lack fine-grained cross-attention between specific query terms and candidate text chunks.

PLAN §8.4 and Task 3.12 require a unified **Hybrid Retrieval Architecture** combining dense vector search, lexical keyword matching, graph traversal, and a final cross-encoder reranking stage.

---

## Decision

### 1. Multi-Signal Fusion (Reciprocal Rank Fusion - RRF)
Implement 3-signal (and optional 4-signal with ColPali on GPU tiers) search in `backend/retrieval/hybrid.py`:
- **Signal 1: Dense Vector Retrieval** (Qdrant `evidence_chunks` with cosine similarity).
- **Signal 2: Exact Keyword / Lexical Scoring** (BM25 / exact token match for part numbers, numbers, and codes).
- **Signal 3: Knowledge Graph Traversal** (Entities matched in query expanded via `GraphStore` edges).
- **Fusion**: Standard Reciprocal Rank Fusion ($RRF = \sum \frac{w_i}{k + r_i}$, $k=60$) merges candidate sets into a consolidated top-$N$ candidate pool.

### 2. Cross-Encoder Reranker
Implement `backend/retrieval/reranker.py`:
- Specification: `bge-reranker-v2-m3`.
- Local execution on `cpu_lite` using optimized cross-attention scoring.
- Re-scores top-$N$ candidates (e.g. $N=20$) to produce top-$K$ final chunks ($K=5$) with high precision.
- Zero-egress: weights are purely local; when neural reranker weights are unavailable, falls back to deterministic multi-token cross-matching without network requests.

### Consequences
- **Positive**: Significantly increases retrieval precision on exact part numbers and multi-hop questions; preserves workspace isolation at every stage.
- **Negative**: Adds 10–50ms compute overhead to query execution on `cpu_lite`, which is well within acceptable latency budgets.

