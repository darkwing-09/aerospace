"""
Integration tests for Full Audit Trail (Task 1.12 / PLAN §7.8, §8.17, §11.19, ADR-0006).
Verifies:
1. Complete trail: REQUEST -> PLAN -> AGENT_DISPATCH -> MODEL_CALL -> TOOL_CALL -> EVALUATION -> RESPONSE
   can be reconstructed for a multi-step task.
2. No raw prompt or document text leaks into the event details (pitfall §11.19).
3. All audit events are append-only, JSON-serializable, and scrubbed.
"""

from pathlib import Path
import json
import pytest

from observability.audit import AuditEvent, AuditLogger
from orchestration.graph import run_task
from tools.registry import UserContext, get_tools_for

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DIAGRAM_PNG = FIXTURES_DIR / "avionics_diagram.png"
MESSY_XLSX = FIXTURES_DIR / "messy_avionics_data.xlsx"


def test_full_audit_trail_reconstruction(tmp_path, monkeypatch):
    """Verifies complete trail: REQUEST -> PLAN -> AGENT_DISPATCH -> MODEL_CALL -> TOOL_CALL -> EVALUATION -> RESPONSE."""
    test_logger = AuditLogger(log_dir=tmp_path)
    monkeypatch.setattr("observability.audit.audit_logger", test_logger)
    monkeypatch.setattr("orchestration.graph.audit_logger", test_logger)
    monkeypatch.setattr("agents.critic_agent.audit_logger", test_logger)
    monkeypatch.setattr("tools.registry.audit_logger", test_logger)

    # 1. Execute a tool call directly to generate TOOL_CALL event
    analyst_user = UserContext(user_id="lead_analyst", role="ANALYST", allowed_workspaces=["ws_mro"])
    bound_tools = get_tools_for("coding", analyst_user, "ws_mro")
    assert len(bound_tools) > 0
    # Invoking bound tool triggers TOOL_CALL emission
    bound_tools[0](code="print(1+1)", language="python")

    # 2. Run multi-step task to trigger REQUEST, PLAN, AGENT_DISPATCH, MODEL_CALL, EVALUATION, RESPONSE
    task = "First inspect diagram of the hydraulic circuit and then calculate fuel burned during climb"
    state = run_task(
        task=task,
        workspace_id="ws_mro",
        user_id="lead_analyst",
        attachments=[str(DIAGRAM_PNG), str(MESSY_XLSX)],
    )

    # Read audit trail from JSONL log
    log_file = tmp_path / "audit.jsonl"
    assert log_file.exists()

    events = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    event_types = [e["event_type"] for e in events]

    # Verify all expected milestone events in the trail
    assert "REQUEST" in event_types
    assert "PLAN" in event_types
    assert "AGENT_DISPATCH" in event_types
    assert "MODEL_CALL" in event_types
    assert "TOOL_CALL" in event_types
    assert "EVALUATION" in event_types
    assert "RESPONSE" in event_types

    # Verify NO raw task prompt or document text leaked into details (pitfall §11.19)
    forbidden_snippets = [
        "First inspect diagram of the hydraulic circuit and then calculate fuel burned during climb",
        "print(1+1)",
        "sapfir radar",
    ]

    for e in events:
        details_str = json.dumps(e.get("details", {})).lower()
        for snippet in forbidden_snippets:
            assert snippet.lower() not in details_str, f"Leaked raw text in event {e['event_type']}: {snippet}"

        # Attributable identity check
        assert e["workspace_id"] == "ws_mro"
        assert e["user_id"] == "lead_analyst"
        assert "timestamp" in e

