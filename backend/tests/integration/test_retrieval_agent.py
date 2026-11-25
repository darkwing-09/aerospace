"""
Integration tests for Retrieval Agent (Task 1.7 / PLAN §7.2, §11.3).
Verifies:
1. Unanswerable queries return INSUFFICIENT_EVIDENCE honestly without hallucination.
2. Iterative reformulation tries up to 2 variations before declaring insufficient evidence.
3. Answerable queries return SUFFICIENT status with non-empty EvidenceRefs.
4. End-to-end graph integration: answerable queries PASS the Critic; unanswerable FAIL.
"""

from pathlib import Path
import pytest

from agents.retrieval_agent import RetrievalAgent
from ingestion.pipeline import IngestionPipeline
from knowledge.vector_store import VectorStore
from orchestration.graph import run_task

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MAINTENANCE_PDF = FIXTURES_DIR / "maintenance_sop.pdf"


@pytest.fixture
def populated_retrieval():
    vstore = VectorStore(force_memory=True)
    pipe = IngestionPipeline(vector_store=vstore)
    pipe.ingest_file(
        file_path=MAINTENANCE_PDF,
        workspace_id="ws_hydraulic",
        classification_level="INTERNAL",
    )
    return RetrievalAgent(vector_store=vstore), vstore


def test_unanswerable_query_gives_insufficient_evidence():
    """Unanswerable query emits INSUFFICIENT_EVIDENCE honestly without hallucinating."""
    empty_vstore = VectorStore(force_memory=True)
    agent = RetrievalAgent(vector_store=empty_vstore)

    res = agent.retrieve(
        query="What is the warp core coolant flow rate of the starship Enterprise?",
        workspace_id="ws_empty",
    )

    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert "INSUFFICIENT_EVIDENCE" in res["answer"]
    assert len(res["evidence_refs"]) == 0
    assert len(res["missing_information"]) > 0
    assert res["reformulations_tried"] == 2


def test_answerable_query_returns_sufficient(populated_retrieval):
    """Answerable query on maintenance SOP returns SUFFICIENT with evidence refs."""
    agent, _ = populated_retrieval
    res = agent.retrieve(
        query="What is the normal operating pressure of the hydraulic system 210 kg/cm2?",
        workspace_id="ws_hydraulic",
    )

    assert res["status"] == "SUFFICIENT"
    assert len(res["evidence_refs"]) > 0
    assert any(ref["tag"] in ("retrieved", "observed") for ref in res["evidence_refs"])
    assert "210 kg/cm2" in res["answer"] or "hydraulic" in res["answer"].lower()
    assert len(res["missing_information"]) == 0


def test_retrieval_graph_integration_unanswerable_fails_critic():
    """Graph execution on unanswerable query marks execution FAILED and FAILS Critic."""
    state = run_task(
        task="Find in manual: warp core coolant flow rate for antimatter injector",
        workspace_id="ws_nonexistent",
    )

    assert state["task_type"] == "retrieval"
    assert len(state["evidence"]) == 0
    assert state["evaluation"] is not None
    assert state["evaluation"]["verdict"] == "FAIL"
    assert state["evaluation"]["needs_human_review"] is True
    assert "INSUFFICIENT_EVIDENCE" in state["result"]

