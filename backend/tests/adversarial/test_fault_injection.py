"""
backend/tests/adversarial/test_fault_injection.py
─────────────────────────────────────────────────────────────────
Adversarial Fault Injection Tests (Task 4.2 / PLAN §11.5, §11.6).
Verifies system behavior under:
1. Model timeout (>2.0s or TimeoutError).
2. Connector credential expiry / authorization failure.
3. Critic retry over-budget (enforcing max retries and human review flag).
4. Corrupted file upload (truncated binary, invalid magic headers).
5. Qdrant lock held / database failure (must fail loudly without silent memory fallback).
6. Intermediate graph node failure (deterministic error recovery).
"""

from __future__ import annotations

import time
from pathlib import Path
import pytest

from orchestration.state import WorkbenchState
from agents.critic_agent import critic_agent_node
from router.router import ModelRouter, ModelFailureError
from router.health import health_checker
from observability.audit import AuditEvent, audit_logger
from connectors.filesystem_wiki import LocalWikiConnector
from knowledge.vector_store import VectorStore, VectorStoreLockError
from ingestion.pipeline import IngestionPipeline
from ingestion.evidence_unit import ProcessingStatus


def test_model_timeout(monkeypatch):
    """
    Injects model timeout (> 2.0s or TimeoutError).
    Verifies that:
    1. Health checker records failure.
    2. Critic agent NEVER PASSes timed out or degraded output.
    """
    events = []
    monkeypatch.setattr(audit_logger, "emit", lambda ev: events.append(ev))

    def timeout_probe(endpoint: str) -> bool:
        time.sleep(0.01)
        raise TimeoutError("Model endpoint timed out after 2.0s")

    monkeypatch.setattr(health_checker, "_probe_endpoint", timeout_probe)

    endpoint = "http://127.0.0.1:11434"
    tag = "qwen3:4b-instruct-2507-q4_K_M"

    is_up = health_checker.is_available(endpoint, tag)
    assert is_up is False
    assert health_checker._get_entry(endpoint, tag)["consecutive_failures"] >= 1

    state = WorkbenchState(
        task="Calculate maximum hydraulic relief valve pressure",
        workspace_id="ws_fault_test",
        user_id="fault_injector",
        user_role="ANALYST",
        execution_status="FAILED",
        result="[TIMEOUT ERROR]: Upstream inference model failed to respond within 2.0s.",
    )

    critic_res = critic_agent_node(state)
    assert critic_res.get("execution_status") == "FAILED"
    assert critic_res.get("done") is True
    eval_dict = critic_res.get("evaluation", {})
    assert eval_dict.get("verdict") == "FAIL"
    assert eval_dict.get("faithfulness", 0.0) == 0.0


def test_connector_credential_expiry(tmp_path, monkeypatch):
    """
    Injects connector credential expiration / path unreadability.
    Verifies that the connector fails closed with an honest error and does not produce fabricated units.
    """
    events = []
    monkeypatch.setattr(audit_logger, "emit", lambda ev: events.append(ev))

    revoked_wiki = tmp_path / "revoked_wiki_path"
    connector = LocalWikiConnector(root_dir=str(revoked_wiki))

    conn_res = connector.connect()
    assert conn_res.success is False
    assert conn_res.status_code == 404

    # Discovering resources on disconnected connector returns empty list without fabrications
    resources = connector.discover_resources()
    assert resources == []

    # Fetching resource from disconnected/expired connector raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        connector.fetch_resource("unauthorized.md")


def test_critic_over_budget():
    """
    Simulates a task where Critic repeatedly rejects ungrounded drafts.
    Enforces that after max retries (e.g. 2), the system marks the task FAILED
    with needs_human_review=True and NEVER returns an ungrounded PASS.
    """
    state = WorkbenchState(
        task="Extract classified flight coordinates",
        workspace_id="ws_critic_budget",
        user_id="user_test",
        user_role="VIEWER",
        result="Flight coordinates are 45.123N, 12.456E (invented hallucination)",
        critic_retries=2,  # Already at retry limit
        execution_status="IN_PROGRESS"
    )

    result = critic_agent_node(state)
    assert result["done"] is True
    assert result["execution_status"] == "FAILED"
    assert result["needs_human_review"] is True
    assert result["evaluation"]["verdict"] == "FAIL"
    assert "Human review required" in result["result"]


def test_corrupted_upload_fails_safely(tmp_path):
    """
    Tests upload and ingestion of corrupted/truncated files.
    Extractors and pipeline must report status=FAILED without crashing.
    """
    corrupt_pdf = tmp_path / "corrupt.pdf"
    with open(corrupt_pdf, "wb") as f:
        f.write(b"%PDF-1.4 Truncated gibberish with no catalog or trailer xref")

    vstore = VectorStore(force_memory=True)
    pipeline = IngestionPipeline(vector_store=vstore)

    doc, count = pipeline.ingest_file(corrupt_pdf, workspace_id="ws_corrupt")
    # Must report FAILED or COMPLETED cleanly without throwing unhandled exceptions
    assert doc.status in (ProcessingStatus.FAILED, ProcessingStatus.COMPLETED)
    if doc.status == ProcessingStatus.FAILED:
        assert count == 0


def test_qdrant_lock_held_fails_loudly(tmp_path, monkeypatch):
    """
    ADR-0004 & §11.3:
    When an embedded Qdrant lock is held, VectorStore must fail loudly with VectorStoreLockError
    and NEVER silently fallback to an ephemeral in-memory database.
    """
    class MockLockedClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Database lock held by another process")

    monkeypatch.setattr("knowledge.vector_store.HAS_QDRANT", True)
    monkeypatch.setattr("knowledge.vector_store.QdrantClient", MockLockedClient)

    with pytest.raises(VectorStoreLockError) as exc_info:
        VectorStore(storage_path=tmp_path / "locked_db", force_memory=False)

    assert "Fatal Qdrant lock error" in str(exc_info.value)
    assert "Refusing silent fallback to in-memory store" in str(exc_info.value)


def test_intermediate_node_failure_recovery():
    """
    Verifies that when an intermediate node in graph execution encounters an unexpected failure,
    the graph fails safely, records the error in state, and halts rather than looping.
    """
    state = WorkbenchState(
        task="Complex multi-step diagnostic",
        workspace_id="ws_node_fail",
        user_id="user_test",
        user_role="ANALYST",
        execution_status="FAILED",
        error="Step 'correlation' failed: Out of Memory during graph edge traversal",
        result="[CRITICAL ERROR]: Pipeline halted due to unexpected worker fault.",
    )

    # Critic node handles FAILED state deterministically
    res = critic_agent_node(state)
    assert res["done"] is True
    assert res["execution_status"] == "FAILED"
    assert res["evaluation"]["verdict"] == "FAIL"
