"""
backend/tools/kb_search.py
─────────────────────────────────────────────────────────────────
Knowledge Base Search Tool for AeroMind 2.0 (PLAN §7.6, Task 1.5).
Executes tenant-isolated vector search across EvidenceUnits.
workspace_id is strictly REQUIRED at every layer.
Enforces clearance levels when user_ctx is provided.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from knowledge.vector_store import VectorStore
from ingestion.pipeline import generate_deterministic_embedding
from tools.registry import UserContext

# Clearance rank hierarchy
CLEARANCE_RANKS: Dict[str, int] = {
    "UNCLASSIFIED": 1,
    "INTERNAL": 2,
    "RESTRICTED": 3,
    "CONFIDENTIAL": 4,
    "SECRET": 5,
}


def search_knowledge_base(
    query: str,
    workspace_id: str,
    top_k: int = 5,
    user_ctx: Optional[UserContext] = None,
    vector_store: Optional[VectorStore] = None,
) -> List[Dict[str, Any]]:
    """
    Searches indexed EvidenceUnits in the specified workspace.
    Fails closed if workspace_id is omitted or user context lacks permission.
    """
    if not workspace_id or not workspace_id.strip():
        raise ValueError("workspace_id is REQUIRED for knowledge base search (PLAN §11.3).")

    if user_ctx is not None:
        if not user_ctx.can_access_workspace(workspace_id):
            raise PermissionError(
                f"Access denied: User '{user_ctx.user_id}' does not have access to workspace '{workspace_id}'."
            )

    vstore = vector_store or VectorStore()
    q_vec = generate_deterministic_embedding(query, dimension=vstore.vector_size)

    raw_results = vstore.search(
        query_vector=q_vec,
        workspace_id=workspace_id,
        top_k=top_k,
    )

    hits: List[Dict[str, Any]] = []
    user_clearance = user_ctx.clearance_level.upper() if user_ctx else "SECRET"
    user_clearance_rank = CLEARANCE_RANKS.get(user_clearance, 2)

    for r in raw_results:
        payload = r.get("payload", {})
        doc_clearance = payload.get("classification_level", "INTERNAL").upper()
        doc_rank = CLEARANCE_RANKS.get(doc_clearance, 2)

        # Enforce clearance: do not leak classified chunks to lower-clearance users
        if doc_rank > user_clearance_rank:
            continue

        hits.append({
            "id": r["id"],
            "score": r["score"],
            "unit_id": payload.get("unit_id"),
            "source_ref": payload.get("source_ref"),
            "source_type": payload.get("source_type"),
            "extracted_text": payload.get("extracted_text"),
            "evidence_tag": payload.get("evidence_tag"),
            "confidence": payload.get("confidence", 1.0),
            "location": payload.get("location", {}),
            "workspace_id": payload.get("workspace_id"),
            "classification_level": payload.get("classification_level"),
        })

    return hits

