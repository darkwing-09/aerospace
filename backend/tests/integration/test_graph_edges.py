import pytest
import tempfile
import os
from ingestion.evidence_unit import EvidenceUnit, PageSectionLocation
from knowledge.graph_store import GraphStore, GraphNode
from knowledge.graph_edges import compute_and_persist_edges

@pytest.fixture
def temp_graph_store():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_edges_graph.sqlite3")
        store = GraphStore(db_path=db_path)
        yield store

def test_co_occurrence_and_reference_edges(temp_graph_store):
    store = temp_graph_store
    ws = "ws-avionics"
    
    # Pre-populate known entities in graph
    store.upsert_node(GraphNode(node_id="pump-104", workspace_id=ws, name="Main Fuel Pump 104", entity_type="equipment"))
    store.upsert_node(GraphNode(node_id="sop-fuel-flow", workspace_id=ws, name="SOP Fuel Flow Check", entity_type="procedure"))
    
    unit1 = EvidenceUnit(
        id="doc1_p1_u1",
        source_type="pdf",
        source_ref="manual.pdf#page=1",
        extracted_text="For Main Fuel Pump 104 operation, refer to SOP Fuel Flow Check step 3.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=1, line_number=1)
    )
    
    edges = compute_and_persist_edges(units=[unit1], graph_store=store, workspace_id=ws)
    assert len(edges) >= 2
    
    edge_types = {e.edge_type for e in edges}
    assert "co-occurs-in" in edge_types
    assert "references" in edge_types
    
    # Verify persisted in store
    persisted = store.get_edges(workspace_id=ws, source_id="pump-104")
    assert len(persisted) >= 1
    assert any("doc1_p1_u1" in p.evidence_ids for p in persisted)

def test_temporal_adjacency_edges(temp_graph_store):
    store = temp_graph_store
    ws = "ws-flight"
    
    store.upsert_node(GraphNode(node_id="engine-start", workspace_id=ws, name="Engine Start", entity_type="procedure"))
    store.upsert_node(GraphNode(node_id="taxi-clearance", workspace_id=ws, name="Taxi Clearance", entity_type="procedure"))
    
    unit1 = EvidenceUnit(
        id="log_u1",
        source_type="csv",
        source_ref="flight_log.csv#row=1",
        extracted_text="Step 1: Engine Start completed at 10:05.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=1, line_number=1)
    )
    unit2 = EvidenceUnit(
        id="log_u2",
        source_type="csv",
        source_ref="flight_log.csv#row=2",
        extracted_text="Step 2: Taxi Clearance received at 10:08.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=1, line_number=2)
    )
    
    edges = compute_and_persist_edges(units=[unit1, unit2], graph_store=store, workspace_id=ws)
    temporal_edges = [e for e in edges if e.edge_type == "temporally-adjacent-to"]
    assert len(temporal_edges) >= 1
    assert temporal_edges[0].source_id == "engine-start"
    assert temporal_edges[0].target_id == "taxi-clearance"
    assert "log_u1" in temporal_edges[0].evidence_ids or "log_u2" in temporal_edges[0].evidence_ids

def test_corroboration_and_contradiction_edges(temp_graph_store):
    store = temp_graph_store
    ws = "ws-limits"
    
    store.upsert_node(GraphNode(node_id="fuel-temp-sensor", workspace_id=ws, name="Fuel Temperature Sensor", entity_type="equipment"))
    store.upsert_node(GraphNode(node_id="oil-temp-sensor", workspace_id=ws, name="Oil Temperature Sensor", entity_type="equipment"))
    
    # Contradictory statements on fuel temp sensor maximum limit
    u_sop = EvidenceUnit(
        id="sop_limit",
        source_type="pdf",
        source_ref="sop.pdf#page=5",
        extracted_text="Fuel Temperature Sensor operating limit maximum 50 C.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=5)
    )
    u_bulletin = EvidenceUnit(
        id="bulletin_limit",
        source_type="pdf",
        source_ref="bulletin.pdf#page=1",
        extracted_text="Fuel Temperature Sensor operating limit updated to maximum 65 C, contradicts earlier 50 C limit.",
        workspace_id=ws,
        location=PageSectionLocation(page_number=1)
    )
    
    edges = compute_and_persist_edges(units=[u_sop, u_bulletin], graph_store=store, workspace_id=ws)
    contra_edges = [e for e in edges if e.edge_type == "contradicts"]
    assert len(contra_edges) >= 1
    assert "sop_limit" in contra_edges[0].evidence_ids
    assert "bulletin_limit" in contra_edges[0].evidence_ids
