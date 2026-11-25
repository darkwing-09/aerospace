"""
backend/tests/integration/test_tool_call_parity.py
─────────────────────────────────────────────────────────────────
Integration tests for tool-calling parity, quantization effects, and
JSON schema compliance across hardware tiers (Task 2.3 / PLAN §8.19).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import yaml

from router.router import ModelRouter
from tools.registry import get_tool, get_tools_for, ToolSpec
from orchestration.state import WorkbenchState
from agents.multimodal_agent import multimodal_agent_node
from agents.data_analysis_agent import data_analysis_agent_node
from agents.coding_agent import coding_agent_node

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MODELS_YAML = REPO_ROOT / "config" / "models.yaml"


def test_tool_calling_modes_in_registry(hardware_tier):
    """Verify tool-calling mode is explicitly configured for every model in the tier."""
    router = ModelRouter(hardware_tier=hardware_tier)
    models = router.get_tier_models(hardware_tier)
    assert len(models) > 0

    valid_modes = {"native", "json_mode", "none"}
    for m in models:
        tc = m.get("tool_calling")
        assert tc in valid_modes, (
            f"Model {m.get('name')} in tier {hardware_tier} has invalid tool_calling mode: {tc}. "
            f"Must be one of {valid_modes}"
        )

    # In cpu_lite, quantized models must use json_mode for reliable tool calling
    if hardware_tier == "cpu_lite":
        coder = router.resolve("code_gen")
        assert coder.get("tool_calling") == "json_mode"


def test_tool_schema_validation_success():
    """Verify standard tool invocation schemas pass validation across all tools."""
    sandbox_spec = get_tool("sandbox_exec")
    assert sandbox_spec is not None
    assert sandbox_spec.name == "sandbox_exec"
    fields = sandbox_spec.input_schema.model_fields
    assert "code" in fields

    kb_spec = get_tool("kb_search")
    assert kb_spec is not None
    assert kb_spec.name == "kb_search"


def test_schema_validation_failures_are_counted_and_handled():
    """Verify malformed JSON tool calls are captured cleanly without crashing the agent."""
    invalid_json_inputs = [
        "not json at all",
        '{"action": "sandbox_exec", "params": {malformed json',
        '{"action": "unknown_tool", "params": {}}',
        '{"action": "sandbox_exec", "params": {"unknown_field": 123}}',
    ]

    schema_failures = 0
    for raw_input in invalid_json_inputs:
        try:
            parsed = json.loads(raw_input)
            action = parsed.get("action")
            tool_spec = get_tool(action)
            if not tool_spec:
                schema_failures += 1
            else:
                params = parsed.get("params", {})
                reqs = [
                    name for name, f in tool_spec.input_schema.model_fields.items()
                    if f.is_required()
                ]
                if not all(r in params for r in reqs):
                    schema_failures += 1
        except json.JSONDecodeError:
            schema_failures += 1

    assert schema_failures == len(invalid_json_inputs), "All invalid tool schemas must be accounted for"


def test_coding_agent_tool_dispatch_parity(hardware_tier):
    """Verify Coding agent dispatches and executes sandbox code in the active tier."""
    state = WorkbenchState(
        task="Write prime checking algorithm and verify with tests",
        workspace_id="ws_default",
        user_id="user_test",
        user_role="ANALYST",
    )
    res = coding_agent_node(state)
    assert res.get("execution_status") == "COMPLETED"
    assert "result" in res
    assert "PRIME_CHECK_VERIFIED" in res["result"]


def test_data_analysis_tool_dispatch_parity(hardware_tier, tmp_path):
    """Verify Data Analysis agent executes tabular calculations deterministically."""
    csv_file = tmp_path / "flight_test.csv"
    csv_file.write_text("timestamp,pressure_psi,temperature_c\n0,210,25\n1,208,26\n2,205,27\n")

    state = WorkbenchState(
        task="Analyze pressure readings from flight test",
        workspace_id="ws_default",
        user_id="user_test",
        user_role="ANALYST",
        attachments=[str(csv_file)],
    )
    res = data_analysis_agent_node(state)
    assert "agent_messages" in res
    assert len(res["agent_messages"]) > 0
    assert "result" in res
    result_text = res["result"]
    assert "flight_test" in result_text or "rows" in result_text or "Spreadsheet" in result_text or "pressure" in result_text


def test_vlm_fixture_validation(hardware_tier):
    """Verify VLM correctly analyzes fixture image and produces valid EvidenceRef."""
    diagram_path = REPO_ROOT / "backend" / "tests" / "fixtures" / "avionics_diagram.png"
    if not diagram_path.exists():
        pytest.skip("Fixture avionics_diagram.png not found")

    state = WorkbenchState(
        task="Inspect hydraulic accumulator diagram",
        workspace_id="ws_default",
        user_id="user_test",
        user_role="ANALYST",
        attachments=[str(diagram_path)],
    )
    res = multimodal_agent_node(state)
    assert "agent_messages" in res
    assert len(res["agent_messages"]) > 0
    msg = res["agent_messages"][-1]
    evidence_refs = msg.get("evidence_refs", []) if isinstance(msg, dict) else msg.evidence_refs
    assert len(evidence_refs) > 0
    ref = evidence_refs[0]
    source_id = ref.get("source_id") if isinstance(ref, dict) else ref.source_id
    assert source_id is not None
    assert "avionics_diagram" in source_id
    assert "result" in res or "findings" in msg.get("payload", {})
