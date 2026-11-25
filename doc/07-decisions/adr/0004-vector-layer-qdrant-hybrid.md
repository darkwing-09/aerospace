# ADR-0004: Vector layer — Qdrant hybrid (text-chunk collection + optional ColPali page index)
**Status**: Accepted   **Date**: 2026-11-04 (Accepted) / 2026-11-03 (Proposed)

## Context
AeroMind already uses Qdrant: `qdrant-client 1.19.0` in system python, embedded on disk at `backend/data_repository/qdrant_db` (`backend/config.py:57`). That matches PLAN §8.4 (Qdrant, reference ADR-0004). The current design, however, violates the plan in five ways.

**1. Fake embeddings.**
- ColQwen2 loads only if `ENABLE_COLPALI_DOWNLOAD=true` (`backend/colpali_retrieval_service.py:118-119`). Otherwise vectors come from `numpy.random` seeded by Python's salted `hash()` (`:142`, `:154`, `:169`).
- On 2026-11-03 the same query ("engine fire emergency procedure") in three separate processes returned three disjoint top-5 page sets: `[175,181,300,257,328]`, `[195,240,310,70,173]`, `[214,215,131,20,21]`.
- This is pitfall §11.8. Vectors persisted in one process don't match queries in another.

**2. Collection per document.** Collections are named `colpali_{doc_id}`, with point id = page number (`:87`, `:226`). There's no workspace payload, no payload indexes, and no cross-document search.

**3. Silent fallback.** On a disk-lock error it falls back to `QdrantClient(":memory:")` without telling anyone (`:75-77`).

**4. Page level only.** Pages are the only unit, and tables are flattened through a CSV/XLSX→PDF conversion that keeps 15/10 rows (`backend/ingestion_adapter.py:145`, `:180`).

**5. Retrieval never comes back empty.** `query_points` always returns `top_k` (`:304-310`), so the keyword fallback (`backend/visual_rag_service.py:237-283`) rarely runs. There's also no sufficiency signal.

PLAN §8.4 requires:
- a COSINE collection with a real embedding model through the router's `embedding` capability
- payload `unit_id, workspace_id, classification_level, source_type, source_ref, extracted_text, evidence_tag, confidence, ingested_at, location, acls`
- payload indexes on `workspace_id`, `classification_level` and `source_type`
- batch upsert of 100
- a deterministic point id `hash(unit.id, chunk_idx)`
- `search()` that **requires** `workspace_id`

It also notes the embedding model is expensive to reverse.

## Options considered
**A. Hybrid.** Add a single plan-conformant `evidence_chunks` collection (dense text embeddings) as the primary retrieval path. Keep ColPali multi-vector as an **optional** secondary page index (`colpali_pages`, one collection with a `workspace_id` + `doc_id` payload), used only when real ColQwen2 weights are present. Merge results before reranking (PLAN §8.5, V1).
- Pros:
  - Plan-conformant.
  - Preserves AeroMind's visual RAG differentiator.
  - Works on the CPU tier (ADR-0007).
- Cons: two indexes to keep consistent.

**B. Text chunks only. Drop ColPali.**
- Pro: simplest.
- Con: loses page-image retrieval for diagram-heavy manuals and P&IDs.

**C. ColPali only. Make it real.**
- Pro: one index.
- Con:
  - About 3 GB of weights (`bench/FIX_PROPOSALS.md:113-137`), slow on CPU.
  - No chunk-level `source_ref`.
  - Doesn't satisfy EvidenceUnit retrieval or tables.

**D. Switch to another vector DB.** No reason to; Qdrant matches the plan.

## Decision (Accepted: 2026-11-04)
Option A.
- **Remove the random/hash fallback vectors.** If ColQwen2 is unavailable, the ColPali index is simply **not used**, and this is reported as `pending_capabilities` / the visual index being unavailable. It is never faked. (If a deterministic stand-in is kept for tests, it must use `hashlib`, not `hash()`, and be labelled `degraded`.)
- **Fail loud on a Qdrant lock** (or switch to a Qdrant server), never `:memory:` silently.
- **Embedding model:** recommend **bge-m3** for every hardware tier. It's multilingual including Indic, has 8k context, and at 568M parameters it is CPU-feasible. The alternative is `nomic-embed-text`, which is already installed in Ollama, as an interim. **This choice is the owner's** (PLAN §12.7).

## Alternatives rejected and why
- **B:** discards a working differentiator (the page images and viewer sync).
- **C:** no chunk-level evidence; too heavy for the `cpu_lite` tier.
- **D:** no benefit.

## Consequences
- **Files:**
  - new: `backend/knowledge/{vector_store,embeddings}.py`, `backend/retrieval/hybrid.py`
  - wrapped: `backend/colpali_retrieval_service.py`, `backend/visual_rag_service.py`
  - migrated: the existing per-document collections (re-ingest; the old data is not reusable because its vectors are random)
- **The payload schema needs human approval before large-scale ingestion** (PLAN task 1.1).
- **Changing the embedding model later = full re-ingestion.** It must be the same across hardware tiers (ADR-0007), or indexes become device-specific.
- The committed `backend/data_repository/qdrant_db/*` should be untracked. That's a repo-hygiene owner decision.

## Open items
- **OI-1:** embedding model, bge-m3 vs. nomic-embed-text vs. other (PLAN §12.7).
- **OI-2:** embedded Qdrant vs. Qdrant server for MVP (concurrency; the lock issue).
- **OI-3:** keep ColPali at all on non-GPU tiers?

## Verification status
- Random retrieval was reproduced on 2026-11-03 (three processes, disjoint results).
- `qdrant-client 1.19.0` and `colpali-engine 0.3.18` are installed in system python.
- ColQwen2 weights are not present, and the download was not attempted (egress).
- No new collection has been created.
