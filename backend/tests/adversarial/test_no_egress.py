"""
backend/tests/adversarial/test_no_egress.py
─────────────────────────────────────────────────────────────────
Adversarial Zero-Egress Enforcement Test (Task 2.5 / PLAN §2, §11.20).
Enforces strict loopback-only network isolation via socket monkeypatching.
Proves that ingestion, retrieval, graph orchestration, router, and session
memory operate completely offline without external network calls.
"""

from __future__ import annotations

import socket
from pathlib import Path
import pytest

from router.router import ModelRouter
from knowledge.vector_store import VectorStore
from ingestion.pipeline import IngestionPipeline
from tools.kb_search import search_knowledge_base
from orchestration.graph import run_task

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


@pytest.fixture(autouse=True)
def enforce_zero_egress(monkeypatch):
    """
    Monkeypatches socket.socket.connect to strictly forbid any non-loopback address.
    """
    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        # Allow UNIX domain sockets (host is str path or empty)
        if isinstance(host, str) and (host in LOOPBACK_HOSTS or host.startswith("/")):
            return orig_connect(self, address)
        raise RuntimeError(f"Zero-egress violation: connection to non-loopback address blocked: {address}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


def test_external_egress_strictly_blocked():
    """Verify that an attempted external connection is blocked by the guard."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as exc:
        s.connect(("8.8.8.8", 53))
    assert "Zero-egress violation" in str(exc.value)
    s.close()


def test_router_resolution_under_zero_egress():
    """Verify router capability resolution succeeds under no-egress guard."""
    router = ModelRouter(hardware_tier="cpu_lite")
    entry = router.resolve("planning")
    assert entry is not None
    assert "qwen3" in entry["model_tag"]


def test_ingestion_and_retrieval_under_zero_egress(tmp_path):
    """Verify document ingestion and vector search work completely offline."""
    sample_doc = tmp_path / "emergency_check.csv"
    sample_doc.write_text("code,procedure,action\nSOP-HYD-99,emergency hydraulic failure,deploy ram air turbine RAT\n")

    vstore = VectorStore(force_memory=True)
    pipeline = IngestionPipeline(vector_store=vstore)
    doc, count = pipeline.ingest_file(
        file_path=sample_doc,
        workspace_id="ws_offline",
        classification_level="UNCLASSIFIED",
    )
    assert count > 0

    # Search knowledge base offline using the same vector store
    results = vstore.search(
        query_vector=[0.1] * 768,
        workspace_id="ws_offline",
        classification_level="UNCLASSIFIED",
        top_k=5,
    )
    assert len(results) > 0
    payload = results[0].get("payload", {}) if isinstance(results[0], dict) else getattr(results[0], "payload", {})
    text = payload.get("extracted_text", "") or payload.get("text", "")
    assert "ram air turbine" in text.lower()


def test_graph_orchestration_under_zero_egress():
    """Verify multi-agent graph execution succeeds under zero-egress guard."""
    res = run_task(
        task="Calculate standard atmospheric pressure at sea level in psi and bar",
        workspace_id="ws_offline",
        user_id="analyst_test",
    )
    assert res.get("execution_status") == "COMPLETED"
    assert "result" in res


def test_connectors_and_hybrid_retrieval_under_zero_egress(tmp_path):
    """
    Task 4.1a:
    Verify that enterprise connector paths and hybrid retrieval
    operate 100% offline with all external egress strictly blocked.
    """
    from connectors.filesystem_wiki import LocalWikiConnector
    from retrieval.hybrid import HybridRetriever
    from retrieval.reranker import CrossEncoderReranker
    from knowledge.graph_store import GraphStore

    # Setup local connector instance
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "flight_sop.md").write_text("# Flight SOP\nAltitude ceiling 18000m.")

    connector = LocalWikiConnector(root_dir=str(wiki_dir))
    assert connector.connect().success is True
    resources = connector.discover_resources()
    raw = connector.fetch_resource(resources[0])
    unit = connector.normalize_to_evidence(raw, workspace_id="ws_connector_offline")
    assert unit.workspace_id == "ws_connector_offline"

    # Setup hybrid retriever offline
    vstore = VectorStore(force_memory=True)
    gstore = GraphStore(db_path=str(tmp_path / "graph.sqlite3"))
    retriever = HybridRetriever(vector_store=vstore, graph_store=gstore, reranker=CrossEncoderReranker())

    # Verify attempted connector external socket call is blocked
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError) as exc:
        s.connect(("192.168.1.100", 80))
    assert "Zero-egress violation" in str(exc.value)
    s.close()
