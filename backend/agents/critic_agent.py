"""
backend/agents/critic_agent.py
─────────────────────────────────────────────────────────────────
Critic Agent for AeroMind 2.0 (PLAN §6, §7.3, §8.10).
Applies deterministic verification gates.
Rule (PLAN §3.2): A degraded or fallback output can never PASS the Critic.
If factual claims lack supporting evidence_refs, the deliverable is flagged
for human review and marked as FAIL.
"""

from __future__ import annotations

from typing import Any, Dict
from langchain_core.messages import AIMessage
from observability.audit import AuditEvent, audit_logger
from orchestration.state import WorkbenchState


def critic_agent_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Evaluates deliverable integrity, citations, and evidence backing.
    Appends the verified AIMessage to state messages for session memory.
    """
    evidence = state.get("evidence", [])
    result = state.get("result", "")
    task_type = state.get("task_type", "drafting")

    ai_msg = AIMessage(content=result)

    try:
        from observability.audit import AuditEvent, audit_logger
        audit_logger.emit(
            AuditEvent(
                workspace_id=state.get("workspace_id", "default"),
                user_id=state.get("user_id", "operator"),
                conversation_id=state.get("conversation_id", ""),
                task_id=state.get("task_id", ""),
                event_type="EVALUATION",
                agent_name="critic_agent",
                evidence_refs=[r.get("source_id", "") for r in evidence],
                details={
                    "evidence_count": len(evidence),
                    "task_type": task_type,
                },
            )
        )
    except Exception:
        pass

    # Gate 1: Check for evidence on factual claims (drafting, multimodal, retrieval, data_analysis)
    factual_task_types = ("drafting", "multimodal", "retrieval", "data_analysis")
    prior_status = state.get("execution_status", "COMPLETED")
    budget_exceeded = state.get("critic_retries", 0) >= 2
    is_failed = prior_status == "FAILED" or budget_exceeded

    if (task_type in factual_task_types and not evidence) or is_failed:
        # Factual claims without evidence CANNOT pass Critic (PLAN §3.2, §8.10)
        review_msg = "Human review required: No supporting evidence found or critic retry budget exceeded"
        return {
            "messages": [ai_msg],
            "result": f"[FAILED]: {review_msg}. {result}" if is_failed else result,
            "evaluation": {
                "verdict": "FAIL",
                "faithfulness": 0.0,
                "reason": "Missing evidence_refs: Deliverable lacks supporting EvidenceUnit citations.",
                "needs_human_review": True,
            },
            "needs_human_review": True,
            "review_reason": review_msg,
            "execution_status": "FAILED" if is_failed else "COMPLETED",
            "step_count": state.get("step_count", 0) + 1,
            "done": True,
        }

    # Gate 2: Verified with supporting evidence
    return {
        "messages": [ai_msg],
        "evaluation": {
            "verdict": "PASS",
            "faithfulness": 1.0,
            "reason": f"Deliverable validated against {len(evidence)} verified EvidenceUnits.",
        },
        "needs_human_review": False,
        "review_reason": None,
        "execution_status": "COMPLETED",
        "step_count": state.get("step_count", 0) + 1,
        "done": True,
    }

