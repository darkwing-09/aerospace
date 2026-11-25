"""
Unit tests for Tool Contract and Registry (Task 0.4 / PLAN §7.6, §7.7).
"""

import pytest
from tools.registry import (
    _ALL_TOOLS,
    BoundTool,
    ToolSpec,
    UserContext,
    get_tools_for,
)


def test_dangerous_tools_excluded_from_build():
    # Zero-egress & security invariant: dangerous tools must not exist in registry
    assert "web_fetch" not in _ALL_TOOLS
    assert "cloud_sync" not in _ALL_TOOLS
    assert "remote_shell" not in _ALL_TOOLS


def test_tool_specs_enforce_zero_egress():
    for name, spec in _ALL_TOOLS.items():
        assert isinstance(spec, ToolSpec)
        assert spec.network_required is False, f"Tool '{name}' violates zero-egress policy."


def test_get_tools_for_role_authorization():
    viewer = UserContext(
        user_id="user_viewer",
        role="VIEWER",
        allowed_workspaces=["ws_alpha"],
    )
    analyst = UserContext(
        user_id="user_analyst",
        role="ANALYST",
        allowed_workspaces=["ws_alpha"],
    )

    # Coding agent grants sandbox_exec (requires ANALYST)
    viewer_tools = get_tools_for("coding", viewer, "ws_alpha")
    viewer_tool_names = [t.spec.name for t in viewer_tools]
    assert "sandbox_exec" not in viewer_tool_names

    analyst_tools = get_tools_for("coding", analyst, "ws_alpha")
    analyst_tool_names = [t.spec.name for t in analyst_tools]
    assert "sandbox_exec" in analyst_tool_names


def test_workspace_isolation():
    user = UserContext(
        user_id="user_1",
        role="ANALYST",
        allowed_workspaces=["ws_permitted"],
    )
    # User cannot get tools for an unpermitted workspace
    unauthorized_tools = get_tools_for("retrieval", user, "ws_forbidden")
    assert unauthorized_tools == []


def test_bound_tool_invocation_permission_check():
    analyst = UserContext(
        user_id="user_analyst",
        role="ANALYST",
        allowed_workspaces=["ws_alpha"],
    )
    tools = get_tools_for("coding", analyst, "ws_alpha")
    sandbox_tool = next(t for t in tools if t.spec.name == "sandbox_exec")

    # Invocation inside permitted workspace succeeds
    res = sandbox_tool()
    assert "sandbox_exec" in res

    # Invoking against unauthorized workspace fails immediately outside LLM
    tampered_tool = BoundTool(spec=sandbox_tool.spec, user_ctx=analyst, workspace_id="ws_forbidden")
    with pytest.raises(PermissionError) as excinfo:
        tampered_tool()
    assert "Access denied" in str(excinfo.value)

