import re
from typing import List, Dict, Any, Optional
from knowledge.vector_store import VectorStore, generate_deterministic_vector
from knowledge.graph_store import GraphStore
from retrieval.reranker import CrossEncoderReranker

class HybridRetriever:
    """
    Unified Multi-Signal Hybrid Retriever for AeroMind 2.0 (ADR-0010, PLAN §8.4, Task 3.12).
    Combines:
    1. Dense Vector Retrieval (Qdrant evidence_chunks)
    2. Lexical / Keyword Scoring
    3. Knowledge Graph Traversal (entities and edges)
    Fused via Reciprocal Rank Fusion (RRF) and scored with CrossEncoderReranker.
    """
    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: Optional[GraphStore] = None,
        reranker: Optional[CrossEncoderReranker] = None
    ):
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.reranker = reranker or CrossEncoderReranker()

    def search(
        self,
        query: str,
        workspace_id: str,
        top_k: int = 5,
        user_clearance: str = "INTERNAL"
    ) -> List[Dict[str, Any]]:
        if not workspace_id:
            raise ValueError("workspace_id is required for hybrid retrieval")

        # 1. Signal 1: Vector Search
        q_vec = generate_deterministic_vector(query, dim=self.vector_store.vector_size)
        vector_hits = self.vector_store.search(
            query_vector=q_vec,
            workspace_id=workspace_id,
            top_k=top_k * 3,
            classification_level=user_clearance
        )

        candidate_map: Dict[str, Dict[str, Any]] = {}
        for r in vector_hits:
            payload = r.get("payload", {})
            uid = payload.get("unit_id") or r.get("id")
            text = payload.get("extracted_text") or r.get("text", "")
            candidate_map[uid] = {
                "unit_id": uid,
                "text": text,
                "source_ref": payload.get("source_ref", ""),
                "workspace_id": payload.get("workspace_id", workspace_id),
                "classification_level": payload.get("classification_level", "INTERNAL"),
                "vector_score": r.get("score", 0.0)
            }

        # 2. Signal 2: Lexical / Keyword Scoring
        q_tokens = set(re.findall(r"\w+", query.lower()))
        lexical_ranked = []
        for uid, cand in candidate_map.items():
            c_tokens = set(re.findall(r"\w+", cand["text"].lower()))
            overlap = len(q_tokens.intersection(c_tokens))
            lexical_ranked.append((uid, overlap))
        lexical_ranked.sort(key=lambda x: x[1], reverse=True)

        # 3. Signal 3: Knowledge Graph Traversal
        graph_unit_ids = set()
        if self.graph_store:
            # Check if query contains any known entity names in workspace
            with self.graph_store._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT node_id, name FROM graph_nodes WHERE workspace_id = ?", (workspace_id,))
                nodes = cursor.fetchall()
                for n in nodes:
                    if n["name"].lower() in query.lower() or n["node_id"].lower() in query.lower():
                        edges = self.graph_store.get_edges(workspace_id=workspace_id, source_id=n["node_id"])
                        for e in edges:
                            graph_unit_ids.update(e.evidence_ids)

        # 4. Reciprocal Rank Fusion (RRF, k=60)
        K_RRF = 60
        rrf_scores: Dict[str, float] = {uid: 0.0 for uid in candidate_map}

        # Vector rank contribution (weight = 1.0)
        for rank, hit in enumerate(vector_hits):
            uid = hit.get("id") or hit.get("unit_id")
            if uid in rrf_scores:
                rrf_scores[uid] += 1.0 / (K_RRF + (rank + 1))

        # Lexical rank contribution (weight = 0.8)
        for rank, (uid, _) in enumerate(lexical_ranked):
            if uid in rrf_scores:
                rrf_scores[uid] += 0.8 / (K_RRF + (rank + 1))

        # Graph signal bonus (weight = 1.2)
        for uid in candidate_map:
            if uid in graph_unit_ids:
                rrf_scores[uid] += 1.2 / (K_RRF + 1)

        # Rank candidates by RRF
        sorted_candidates = sorted(
            candidate_map.values(),
            key=lambda c: rrf_scores.get(c["unit_id"], 0.0),
            reverse=True
        )

        # 5. Cross-Encoder Reranking
        top_candidates = sorted_candidates[: top_k * 2]
        reranked = self.reranker.rerank(query=query, candidates=top_candidates, top_k=top_k)

        # Map to final output schema
        final_results = []
        for r in reranked:
            final_results.append({
                "unit_id": r["unit_id"],
                "text": r["text"],
                "source_ref": r.get("source_ref", ""),
                "score": r.get("rerank_score", 0.0),
                "rrf_score": round(rrf_scores.get(r["unit_id"], 0.0), 4),
                "workspace_id": r["workspace_id"]
            })

        return final_results
