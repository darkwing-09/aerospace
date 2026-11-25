"""
backend/agents/retrieval_agent.py
─────────────────────────────────────────────────────────────────
Retrieval Agent for AeroMind 2.0 (PLAN §7.2, Task 1.7).
Performs iterative workspace-scoped knowledge retrieval with <= 2 reformulations.
Evaluates sufficiency honestly:
- If evidence is found: emits sufficient status and verified evidence_refs.
- If evidence is absent: emits INSUFFICIENT_EVIDENCE with missing_information;
  NEVER fabricates or hallucinates an answer (PLAN §3.2, §11.3).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from orchestration.state import AgentMessage, EvidenceRef, WorkbenchState
from tools.kb_search import search_knowledge_base
from knowledge.vector_store import VectorStore


class RetrievalAgent:
    """
    Retrieval agent with bounded query reformulation and honesty gates.
    """

    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self.vector_store = vector_store or VectorStore()

    def reformulate_query(self, query: str, attempt: int) -> str:
        """
        Generates up to 2 query reformulations (PLAN §7.2, Task 1.7).
        Attempt 1: Focus on core nouns/technical keywords.
        Attempt 2: Strip interrogatives and punctuation.
        """
        # Remove common question filler
        cleaned = re.sub(
            r"^(what\s+is|what\s+are|how\s+does|can\s+you\s+tell\s+me|where\s+is|explain)\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip(" ?.,!")

        if attempt == 1:
            # Extract key capitalized and technical phrases
            words = [w for w in cleaned.split() if len(w) > 3 and w.lower() not in ("about", "which", "there", "their")]
            return " ".join(words) if words else cleaned
        elif attempt == 2:
            # Broaden query to alphanumeric tokens
            tokens = re.findall(r"\b[A-Za-z0-9_-]+\b", query)
            return " ".join(tokens[:5])
        return query

    def retrieve(
        self,
        query: str,
        workspace_id: str,
        top_k: int = 3,
        user_ctx: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Executes iterative retrieval loop with max 2 reformulations.
        Returns:
            {
                "status": "SUFFICIENT" | "INSUFFICIENT_EVIDENCE",
                "answer": str,
                "hits": List[Dict],
                "evidence_refs": List[EvidenceRef],
                "missing_information": List[str],
                "reformulations_tried": int,
            }
        """
        current_query = query
        hits: List[Dict[str, Any]] = []
        reformulations_tried = 0
        max_reformulations = 2

        for attempt in range(max_reformulations + 1):
            raw_hits = search_knowledge_base(
                query=current_query,
                workspace_id=workspace_id,
                top_k=top_k,
                user_ctx=user_ctx,
                vector_store=self.vector_store,
            )

            # Check if any hits have meaningful similarity
            good_hits = [h for h in raw_hits if h.get("score", 0.0) >= 0.15 and len(h.get("extracted_text", "").strip()) > 10]
            if good_hits:
                hits = good_hits
                break

            if attempt < max_reformulations:
                reformulations_tried += 1
                current_query = self.reformulate_query(query, attempt + 1)

        if not hits:
            # Unanswerable query — NEVER fabricate an answer (PLAN §3.2, §11.3)
            return {
                "status": "INSUFFICIENT_EVIDENCE",
                "answer": (
                    f"INSUFFICIENT_EVIDENCE: The knowledge base for workspace '{workspace_id}' "
                    f"does not contain verified information answering: '{query}'."
                ),
                "hits": [],
                "evidence_refs": [],
                "missing_information": [f"Documentation or manual section addressing '{query}'"],
                "reformulations_tried": reformulations_tried,
            }

        # Format answer citing top evidence
        evidence_refs: List[EvidenceRef] = []
        snippets = []
        for h in hits:
            ref: EvidenceRef = {
                "source_id": h["unit_id"],
                "tag": h.get("evidence_tag", "retrieved"),
                "confidence": min(1.0, float(h.get("score", 0.85))),
            }
            evidence_refs.append(ref)
            snippets.append(f"[{h['source_ref']}]: {h['extracted_text'][:200]}...")

        answer = (
            f"Based on verified documentation in workspace '{workspace_id}':\n"
            + "\n".join(snippets)
        )

        return {
            "status": "SUFFICIENT",
            "answer": answer,
            "hits": hits,
            "evidence_refs": evidence_refs,
            "missing_information": [],
            "reformulations_tried": reformulations_tried,
        }


def retrieval_agent_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    LangGraph node for the Retrieval Agent.
    """
    task = state.get("task", "")
    workspace_id = state.get("workspace_id", "default_workspace")
    task_id = state.get("task_id", "task_retrieval")

    agent = RetrievalAgent()
    retrieval_res = agent.retrieve(query=task, workspace_id=workspace_id)

    status = retrieval_res["status"]
    is_sufficient = status == "SUFFICIENT"
    evidence_refs = retrieval_res["evidence_refs"]

    agent_msg: AgentMessage = {
        "from_agent": "retrieval_agent",
        "to_agent": "critic",
        "task_id": task_id,
        "payload": {
            "status": status,
            "answer": retrieval_res["answer"],
            "missing_information": retrieval_res["missing_information"],
            "reformulations_tried": retrieval_res["reformulations_tried"],
        },
        "evidence_refs": evidence_refs,
        "inference": not is_sufficient,
        "confidence": 0.90 if is_sufficient else 0.0,
        "requires_human_approval": False,
        "agent_version": "1.0.0",
    }

    return {
        "agent_messages": [agent_msg],
        "evidence": evidence_refs,
        "result": retrieval_res["answer"],
        "execution_status": "COMPLETED" if is_sufficient else "FAILED",
        "step_count": state.get("step_count", 0) + 1,
    }

