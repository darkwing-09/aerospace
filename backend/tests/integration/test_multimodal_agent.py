"""
Integration tests for Multimodal Agent (Task 1.6 / PLAN §7.2, §8.1, §11.4).
Verifies:
1. Visual inspection produces structured deliverables with non-empty EvidenceRef.
2. End-to-end execution through the graph on a fixture diagram passes the Critic gate.
3. Missing image artifacts produce unbacked claims that FAIL the Critic.
"""

from pathlib import Path
import pytest

from agents.multimodal_agent import MultimodalAgent
from orchestration.graph import minimal_graph, run_task

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
AVIONICS_DIAGRAM = FIXTURES_DIR / "avionics_diagram.png"
SCANNED_PAGE = FIXTURES_DIR / "scanned_page.png"


def test_multimodal_agent_direct_inspection():
    """Verifies that direct visual inspection produces non-empty evidence refs."""
    agent = MultimodalAgent()
    res = agent.inspect_visual_evidence(
        query="Which component connects to the booster actuator in the schematic?",
        image_path=AVIONICS_DIAGRAM,
    )

    assert "Main Hydraulic Pump" in res["content"] or "Booster Actuator" in res["content"]
    assert len(res["evidence_refs"]) > 0
    ref = res["evidence_refs"][0]
    assert ref["tag"] == "observed"
    assert ref["confidence"] >= 0.80
    assert "resolution" in res["metadata"]


def test_multimodal_graph_integration_passes_critic():
    """Verifies graph execution on fixture image: classify -> multimodal -> critic -> END."""
    initial_task = "Analyze the avionics diagram schematic to inspect booster actuator connections."
    state = run_task(
        task=initial_task,
        workspace_id="ws_avionics",
    )

    assert state["task_type"] == "multimodal"
    assert len(state["evidence"]) > 0
    assert state["evaluation"] is not None
    # Because evidence is non-empty and backed, Critic must PASS!
    assert state["evaluation"]["verdict"] == "PASS"
    assert "Booster Actuator" in state["result"]


def test_multimodal_missing_attachment_fails_critic():
    """When visual evidence is missing, deliverable has empty evidence and Critic FAILS."""
    state = run_task(
        task="Analyze this missing photo diagram",
        conversation_id="conv_missing_img",
    )
    # Even if classified as multimodal, if no file can be found/inspected:
    # We test with an invalid attachment
    from orchestration.graph import build_graph
    g = build_graph()
    custom_state = {
        "task": "Examine this schematic",
        "task_id": "task_bad_img",
        "user_id": "operator",
        "workspace_id": "ws_test",
        "conversation_id": "conv_bad",
        "parent_task_id": None,
        "attachments": ["/tmp/nonexistent_image_12345.png"],
        "messages": [],
        "tool_calls": [],
        "evidence": [],
        "agent_messages": [],
        "task_type": None,
        "plan": None,
        "evaluation": None,
        "execution_status": "RUNNING",
        "user_approval_granted": None,
        "retry_count": 0,
        "correlation_results": None,
        "continuation_proposal": None,
        "step_count": 0,
        "max_steps": 10,
        "done": False,
        "result": None,
    }

    final_state = g.invoke(
        custom_state,
        config={"configurable": {"thread_id": "thread_bad_img"}},
    )

    assert final_state["task_type"] == "multimodal"
    assert len(final_state["evidence"]) == 0
    assert final_state["evaluation"]["verdict"] == "FAIL"
    assert final_state["evaluation"]["needs_human_review"] is True

