# ADR-0008: Knowledge Graph Store Architecture for Entity and Relation Storage
**Status**: Accepted   **Date**: 2026-11-04

## Context
In Phase 3 (V1 System), AeroMind introduces the **Correlation Agent** and cross-document reasoning. This capability requires representing and traversing a Knowledge Graph composed of entities (subsystems, equipment IDs, maintenance SOP steps, telemetry variables, fault codes) and directed, typed relationship edges (`references`, `corroborates`, `contradicts`, `co-occurs-in`, `temporally-adjacent-to`).

### Corpus Sizing Measurements
Measured across existing project assets and fixtures:
- **Synthetic Test & Evaluation Fixtures** (`backend/tests/fixtures/`, `eval/fixtures/`):
  - 5 multimodal fixtures (SOP PDF, scanned flight log, telemetry spreadsheet, cockpit diagram, audio transcript).
  - ~15 distinct document pages, ~50 avionics/equipment entities, ~120 relationship edges.
- **Realistic Aviation Corpus** (`backend/pdfs/mig21bis.pdf` and sample telemetry logs):
  - ~350 document pages, ~1,200 entities (subsystems, instruments, fuel valves, operating limits), ~3,500 relationship edges.
- **Target V1 Enterprise Instance**:
  - Up to 100 manuals/documents per workspace, ~10,000–50,000 entity nodes, ~50,000–250,000 edges.

### Architectural Constraints
1. **Zero-egress & local execution**: No external graph database cloud calls.
2. **`cpu_lite` footprint**: Must run smoothly on the Intel i7 reference host with minimal RAM overhead and zero background daemon processes.
3. **Hard tenant isolation**: Every node and edge must belong to a specific `workspace_id`, and queries must strictly filter by workspace.
4. **Deterministic and inspectable**: Edge provenance must link directly to `EvidenceUnit` IDs (`evidence_ids`).

---

## Options Considered

### A. Dedicated Graph Database Daemon (Neo4j or Memgraph)
- **Pros**: Native graph traversal engine, Cypher query language, enterprise scale (>10M nodes).
- **Cons**: Requires running a separate container or JVM process consuming 1.5–3.0 GB of RAM (unacceptable on `cpu_lite` alongside SLM inference); introduces external network port dependencies; complex backup/restore mechanics.

### B. Pure In-Memory Graph (NetworkX only)
- **Pros**: Fast Python execution of graph algorithms.
- **Cons**: Lacks ACID disk persistence, transactional write safety, persistent indexing, or multi-process query access. `networkx` is currently not installed in the standard environment.

### C. In-Process SQLite Graph Store with Recursive Traversal (Selected)
- **Pros**:
  - Uses Python standard library `sqlite3`: zero external dependencies and zero new packages required.
  - Native ACID persistence in local SQLite file (`data_repository/graph.sqlite3` or temp directory in tests).
  - Strict tenant partitioning via `workspace_id` indexed columns on `graph_nodes` and `graph_edges`.
  - Highly performant: indexed traversal on `(workspace_id, source_id, edge_type)` and `(workspace_id, target_id)`.
  - Multi-hop traversal using SQLite Recursive CTEs (`WITH RECURSIVE`) supports n-hop neighbor queries, path finding, and sub-graph extraction in sub-millisecond time for corpus sizes up to 10^6 edges.
  - Can export sub-graphs to dictionary/adjacency representations without external dependencies.
- **Cons**: Complex graph analytics (e.g. PageRank, community detection) require in-memory calculation rather than built-in Cypher procedures.

---

## Decision
**Option C: In-Process SQLite Graph Store (`backend/knowledge/graph_store.py`)**.

### Schema Specification
1. **`graph_nodes`**:
   - `node_id` (TEXT, PRIMARY KEY compound with `workspace_id`)
   - `workspace_id` (TEXT, NOT NULL, INDEXED)
   - `name` (TEXT, NOT NULL)
   - `entity_type` (TEXT, NOT NULL: `equipment`, `procedure`, `metric`, `document`, `component`)
   - `properties` (TEXT JSON: canonical attributes, aliases, description)
   - `created_at` (TEXT ISO 8601)

2. **`graph_edges`**:
   - `edge_id` (TEXT PRIMARY KEY)
   - `workspace_id` (TEXT, NOT NULL, INDEXED)
   - `source_id` (TEXT, NOT NULL)
   - `target_id` (TEXT, NOT NULL)
   - `edge_type` (TEXT, NOT NULL: `references`, `corroborates`, `contradicts`, `co-occurs-in`, `temporally-adjacent-to`)
   - `confidence` (REAL NOT NULL, 0.0 to 1.0)
   - `evidence_ids` (TEXT JSON list of `EvidenceUnit.unit_id` references)
   - `properties` (TEXT JSON)
   - `created_at` (TEXT ISO 8601)

3. **Compound Indexes**:
   - `idx_nodes_ws_type`: `(workspace_id, entity_type)`
   - `idx_edges_source`: `(workspace_id, source_id, edge_type)`
   - `idx_edges_target`: `(workspace_id, target_id, edge_type)`

### Consequences
- **Positive**: Clean zero-dependency implementation, zero socket egress, hard tenant isolation, sub-millisecond local queries, reproducible across all hardware tiers.
- **Negative**: If an installation scales to >10^7 edges across thousands of workspaces, a pluggable adapter to Memgraph/Neo4j can be introduced without changing agent contracts.

