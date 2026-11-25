"""
Integration tests for Graph Scenarios (Task 1.10 / PLAN §8.1, §11.1, §11.5, §11.6).
Verifies:
1. Simple lookup executes directly via retrieval -> critic -> END.
2. Multi-step task triggers Planner DAG decomposition, dispatching, and synthesis.
3. Ambiguous intent routes to clarify with WAITING_FOR_USER status.
4. Mid-task failure is caught honestly by Critic gate with FAIL verdict.
5. SSE adapter streams typed Server-Sent Events cleanly.
"""

from pathlib import Path
import json
import pytest

from orchestration.graph import run_task, stream_graph_sse

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MAINTENANCE_PDF = FIXTURES_DIR / "maintenance_sop.pdf"
DIAGRAM_PNG = FIXTURES_DIR / "avionics_diagram.png"
MESSY_XLSX = FIXTURES_DIR / "messy_avionics_data.xlsx"


def test_simple_lookup_scenario():
    """Simple query routes directly to retrieval -> critic -> END."""
    state = run_task(
        task="Retrieve hydraulic operating pressure specification from the maintenance manual",
        workspace_id="ws_sop",
    )

    assert state["task_type"] == "retrieval"
    assert state["execution_status"] in ("COMPLETED", "FAILED")
    assert state["evaluation"] is not None
    assert "verdict" in state["evaluation"]


def test_multistep_task_scenario():
    """Multi-step query triggers Planner, Dispatcher, and Synthesis nodes."""
    task = "First inspect diagram of the hydraulic circuit and then calculate fuel burned during climb"
    state = run_task(
        task=task,
        workspace_id="ws_multi",
        attachments=[str(DIAGRAM_PNG), str(MESSY_XLSX)],
    )

    assert state["task_type"] == "multistep"
    assert state["plan"] is not None
    assert state["plan"]["total_subtasks"] >= 2
    assert len(state["agent_messages"]) >= 2
    assert "Consolidated Multi-Step Flight Engineering Synthesis" in state["result"]
    assert state["evaluation"]["verdict"] == "PASS"


def test_ambiguous_task_goes_to_clarify():
    """Ambiguous query routes to clarify node and pauses with WAITING_FOR_USER."""
    state = run_task(
        task="fix the thing on the plane",
        workspace_id="ws_test",
    )

    assert state["task_type"] == "clarify"
    assert state["execution_status"] == "WAITING_FOR_USER"
    assert state["done"] is True
    assert "clarify" in state["result"].lower() or "specify" in state["result"].lower()


def test_injected_mid_task_failure():
    """Subtask with unbacked factual claims FAILS the Critic gate."""
    state = run_task(
        task="draft a short note summarizing last week's unbacked uptime metrics",
        workspace_id="ws_fail",
    )

    assert state["task_type"] == "drafting"
    assert state["evaluation"]["verdict"] == "FAIL"
    assert state["evaluation"]["needs_human_review"] is True


def test_sse_stream_adapter_emits_typed_events():
    """Verifies stream_graph_sse yields valid SSE format with typed events."""
    events = list(
        stream_graph_sse(
            task="Retrieve hydraulic pressure specification from manual",
            workspace_id="ws_stream",
        )
    )

    event_text = "".join(events)
    assert "event: task_start\n" in event_text
    assert "event: final_response\n" in event_text
    assert "event: done\n" in event_text

    # Parse data JSON payloads
    for frame in events:
        lines = frame.strip().split("\n")
        assert len(lines) >= 2
        assert lines[0].startswith("event: ")
        assert lines[1].startswith("data: ")
        json_payload = lines[1][6:]
        data = json.loads(json_payload)
        assert isinstance(data, dict)

