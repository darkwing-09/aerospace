import pytest
from orchestration.graph import evaluate_continuation, continuation_node, run_task
from orchestration.state import WorkbenchState

def test_continuation_proposes_when_relevance_above_threshold():
    """
    Task 3.7:
    Obvious adjacent next step (e.g. Q3 analysis completed and Q4 dataset/next phase present)
    must produce a continuation proposal when relevance >= relevance_threshold (0.75).
    """
    state: WorkbenchState = {
        "task": "Analyze Q3 avionics telemetry and fuel consumption report",
        "task_id": "t-1",
        "user_id": "pilot",
        "workspace_id": "ws-squadron",
        "conversation_id": "c-1",
        "parent_task_id": None,
        "attachments": ["q3_avionics_telemetry.csv"],
        "messages": [],
        "tool_calls": [],
        "evidence": [],
        "agent_messages": [],
        "task_type": "data_analysis",
        "plan": None,
        "evaluation": {"verdict": "PASS"},
        "execution_status": "COMPLETED",
        "user_approval_granted": None,
        "retry_count": 0,
        "correlation_results": None,
        "continuation_proposal": None,
        "step_count": 3,
        "max_steps": 10,
        "done": True,
        "result": "Q3 avionics telemetry analysis completed. Significant pressure drop detected on fuel pump 104 during high-altitude climb. Q4 dataset available.",
        "artifacts": [],
        "needs_human_review": False,
        "review_reason": None,
    }
    
    updated = continuation_node(state)
    assert updated.get("continuation_proposal") is not None
    proposal = updated["continuation_proposal"]
    assert len(proposal) > 15
    assert "q4" in proposal.lower() or "fuel pump" in proposal.lower() or "inspect" in proposal.lower()

def test_continuation_stays_silent_when_no_adjacent_step():
    """
    Task 3.7:
    Completed standalone query with no obvious adjacent next step must remain silent
    (continuation_proposal is None).
    """
    state: WorkbenchState = {
        "task": "What is the tire pressure specification for the main landing gear?",
        "task_id": "t-2",
        "user_id": "technician",
        "workspace_id": "ws-maint",
        "conversation_id": "c-2",
        "parent_task_id": None,
        "attachments": [],
        "messages": [],
        "tool_calls": [],
        "evidence": [],
        "agent_messages": [],
        "task_type": "retrieval",
        "plan": None,
        "evaluation": {"verdict": "PASS"},
        "execution_status": "COMPLETED",
        "user_approval_granted": None,
        "retry_count": 0,
        "correlation_results": None,
        "continuation_proposal": None,
        "step_count": 2,
        "max_steps": 10,
        "done": True,
        "result": "Per maintenance manual section 4.2, the main landing gear tire pressure specification is 8.0 +/- 0.5 bar.",
        "artifacts": [],
        "needs_human_review": False,
        "review_reason": None,
    }
    
    updated = continuation_node(state)
    assert updated.get("continuation_proposal") is None

def test_continuation_stays_silent_on_critic_failure():
    """
    A degraded or failed Critic evaluation can never trigger a continuation proposal.
    """
    state: WorkbenchState = {
        "task": "Analyze Q3 avionics telemetry",
        "task_id": "t-3",
        "user_id": "analyst",
        "workspace_id": "ws-squadron",
        "conversation_id": "c-3",
        "parent_task_id": None,
        "attachments": ["q3_data.csv"],
        "messages": [],
        "tool_calls": [],
        "evidence": [],
        "agent_messages": [],
        "task_type": "data_analysis",
        "plan": None,
        "evaluation": {"verdict": "FAIL"},
        "execution_status": "FAILED",
        "user_approval_granted": None,
        "retry_count": 0,
        "correlation_results": None,
        "continuation_proposal": None,
        "step_count": 2,
        "max_steps": 10,
        "done": True,
        "result": "Incomplete analysis.",
        "artifacts": [],
        "needs_human_review": True,
        "review_reason": "Critic failed",
    }
    
    updated = continuation_node(state)
    assert updated.get("continuation_proposal") is None

