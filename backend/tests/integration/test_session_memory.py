"""
Integration tests for Session Memory (Task 1.11 / PLAN §7.2, §11.2).
Verifies:
1. Server-side session memory accumulates turns keyed by conversation_id.
2. Turn 2 references Turn 1's result without re-prompting or losing context.
3. Message reducers retain the complete turn history across checkpoints.
"""

import pytest
from orchestration.graph import run_task


def test_session_memory_second_turn_references_first():
    """Verifies that turn 2 accurately references turn 1's output."""
    conv_id = "conv_test_session_continuity"

    # Turn 1
    state1 = run_task(
        task="Draft a short note on system uptime",
        conversation_id=conv_id,
    )

    assert "99.94%" in state1["result"]
    assert len(state1["messages"]) >= 2  # HumanMessage + AIMessage

    # Turn 2: Follow-up referencing turn 1
    state2 = run_task(
        task="What was that uptime percentage again?",
        conversation_id=conv_id,
    )

    assert state2["conversation_id"] == conv_id
    # Must retain prior turn messages
    assert len(state2["messages"]) >= 4

    # Turn 2 result MUST reference turn 1's 99.94% value!
    assert "99.94%" in state2["result"]
    assert "earlier" in state2["result"].lower() or "previous" in state2["result"].lower()


def test_independent_conversations_do_not_leak_memory():
    """Verifies that separate conversation IDs do not share memory."""
    state_a = run_task(
        task="Draft a short note on system uptime",
        conversation_id="conv_tenant_a",
    )
    assert "99.94%" in state_a["result"]

    state_b = run_task(
        task="Draft response addressing general maintenance",
        conversation_id="conv_tenant_b",
    )
    # conv_b should only have its own 2 messages, not conv_a's
    assert len(state_b["messages"]) == 2
    assert "99.94%" not in state_b["result"]

