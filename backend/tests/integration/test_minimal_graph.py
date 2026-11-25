"""
Integration tests for Minimal LangGraph DAG (Task 0.5 / PLAN §8.1).
Tests classify → coding and classify → draft → critic paths.
"""

import pytest
from orchestration.graph import run_task


def test_coding_dag_execution():
    task = "write a function that checks if a number is prime, and test it"
    final_state = run_task(task)

    assert final_state["task_type"] == "code_gen"
    assert final_state["execution_status"] == "COMPLETED"
    assert final_state["done"] is True
    assert len(final_state["tool_calls"]) >= 1

    tool_call = final_state["tool_calls"][0]
    assert tool_call["tool_name"] == "sandbox_exec"
    assert tool_call["succeeded"] is True
    assert "PRIME_CHECK_VERIFIED" in tool_call["output"]
    assert "All 8 test cases passed" in final_state["result"]


def test_forced_failing_code_test():
    task = "write a function that will force fail test"
    final_state = run_task(task)

    assert final_state["task_type"] == "code_gen"
    assert final_state["execution_status"] == "FAILED"
    assert final_state["needs_human_review"] is True
    assert len(final_state["tool_calls"]) >= 1
    assert final_state["tool_calls"][0]["succeeded"] is False


def test_drafting_dag_fails_critic_without_evidence():
    # PLAN §3.2 / §8.10: Unbacked factual drafts MUST fail the Critic
    task = "draft a short note summarizing last week's uptime"
    final_state = run_task(task)

    assert final_state["task_type"] == "drafting"
    assert final_state["execution_status"] == "COMPLETED"
    assert final_state["done"] is True

    # Critic evaluation
    eval_rep = final_state.get("evaluation", {})
    assert eval_rep.get("verdict") == "FAIL"
    assert eval_rep.get("faithfulness") == 0.0
    assert final_state["needs_human_review"] is True
    assert "Missing evidence_refs" in eval_rep.get("reason", "")
    assert "No supporting evidence" in final_state.get("review_reason", "")

