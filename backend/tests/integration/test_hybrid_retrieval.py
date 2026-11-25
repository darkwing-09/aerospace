import pytest
import tempfile
import os
from ingestion.evidence_unit import EvidenceUnit, PageSectionLocation
from knowledge.vector_store import VectorStore
from knowledge.graph_store import GraphStore, GraphNode, GraphEdge
from retrieval.reranker import CrossEncoderReranker
from retrieval.hybrid import HybridRetriever

@pytest.fixture
def test_retrieval_environment(tmp_path):
    qdrant_path = str(tmp_path / "qdrant_test")
    graph_path = str(tmp_path / "graph_test.sqlite3")
    
    v_store = VectorStore(storage_path=qdrant_path)
    g_store = GraphStore(db_path=graph_path)
    reranker = CrossEncoderReranker()
    
    retriever = HybridRetriever(
        vector_store=v_store,
        graph_store=g_store,
        reranker=reranker
    )
    
    yield retriever, v_store, g_store

def test_hybrid_retrieval_multi_signal(test_retrieval_environment):
    retriever, v_store, g_store = test_retrieval_environment
    ws = "ws-flight-ops"
    
    # 1. Populate Vector Store with test evidence units
    u1 = EvidenceUnit(
        id="unit_target",
        source_type="pdf",
        source_ref="sop_fuel.pdf#page=12",
        extracted_text="Main Fuel Pump 104 operating pressure limit must strictly remain between 40 and 55 PSI.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=12)
    )
    u2 = EvidenceUnit(
        id="unit_semantic",
        source_type="pdf",
        source_ref="general_systems.pdf#page=5",
        extracted_text="Fuel subsystem pressures during cruise flight normally stabilize around 45 PSI across all pumps.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=5)
    )
    u3 = EvidenceUnit(
        id="unit_other_ws",
        source_type="pdf",
        source_ref="secret_manual.pdf#page=1",
        extracted_text="Main Fuel Pump 104 operating pressure limit is 70 PSI.",
        workspace_id="ws-other-squadron",
        location=PageSectionLocation(page_number=1)
    )
    
    from knowledge.vector_store import generate_deterministic_vector
    chunks = []
    vectors = []
    for u in [u1, u2, u3]:
        chunks.append({
            "unit_id": u.id,
            "chunk_idx": 0,
            "workspace_id": u.workspace_id,
            "classification_level": u.classification_level,
            "source_type": u.source_type,
            "source_ref": u.source_ref,
            "extracted_text": u.extracted_text,
        })
        vectors.append(generate_deterministic_vector(u.extracted_text, v_store.vector_size))
        
    v_store.upsert_chunks(chunks=chunks, vectors=vectors)
    
    # 2. Populate Knowledge Graph
    g_store.upsert_node(GraphNode(node_id="pump-104", workspace_id=ws, name="Main Fuel Pump 104", entity_type="equipment"))
    g_store.upsert_node(GraphNode(node_id="sop-fuel", workspace_id=ws, name="SOP Fuel Manual", entity_type="procedure"))
    g_store.upsert_edge(GraphEdge(
        edge_id="e1",
        workspace_id=ws,
        source_id="pump-104",
        target_id="sop-fuel",
        edge_type="references",
        evidence_ids=["unit_target"]
    ))
    
    # 3. Perform Hybrid Query
    query = "What is the operating pressure limit of Main Fuel Pump 104?"
    results = retriever.search(
        query=query,
        workspace_id=ws,
        top_k=2
    )
    
    assert len(results) >= 1
    # Top result MUST be unit_target due to multi-signal convergence (vector + keyword + graph)
    top_hit = results[0]
    assert top_hit["unit_id"] == "unit_target"
    assert "40 and 55 PSI" in top_hit["text"]
    assert top_hit["score"] >= 0.55
    
    # Verify strict workspace isolation
    result_ids = [r["unit_id"] for r in results]
    assert "unit_other_ws" not in result_ids

def test_reranker_cross_attention_scoring():
    reranker = CrossEncoderReranker()
    query = "emergency fuel cutoff lever location"
    
    candidates = [
        {"unit_id": "c1", "text": "The cockpit features standard analog altimeters and clock displays."},
        {"unit_id": "c2", "text": "Emergency fuel cutoff lever is positioned on the left cockpit console forward of throttle."}
    ]
    
    scored = reranker.rerank(query=query, candidates=candidates)
    assert len(scored) == 2
    # c2 is directly answering the query
    assert scored[0]["unit_id"] == "c2"
    assert scored[0]["rerank_score"] > scored[1]["rerank_score"]
