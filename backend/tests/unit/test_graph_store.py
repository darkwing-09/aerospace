import pytest
import tempfile
import os
from knowledge.graph_store import GraphStore, GraphNode, GraphEdge

@pytest.fixture
def temp_graph_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_graph.sqlite3")
        store = GraphStore(db_path=db_path)
        yield store

def test_node_upsert_and_retrieval(temp_graph_db):
    store = temp_graph_db
    node = GraphNode(
        node_id="pump-104",
        workspace_id="ws-aviation",
        name="Main Fuel Pump 104",
        entity_type="equipment",
        properties={"subsystem": "fuel", "operating_pressure_psi": 45}
    )
    store.upsert_node(node)
    
    fetched = store.get_node(node_id="pump-104", workspace_id="ws-aviation")
    assert fetched is not None
    assert fetched.node_id == "pump-104"
    assert fetched.name == "Main Fuel Pump 104"
    assert fetched.entity_type == "equipment"
    assert fetched.properties["subsystem"] == "fuel"
    assert fetched.properties["operating_pressure_psi"] == 45

def test_workspace_isolation(temp_graph_db):
    store = temp_graph_db
    node_a = GraphNode(
        node_id="valve-1",
        workspace_id="tenant-alpha",
        name="Bleed Valve",
        entity_type="equipment"
    )
    store.upsert_node(node_a)
    
    # Query from another workspace must return None
    fetched = store.get_node(node_id="valve-1", workspace_id="tenant-beta")
    assert fetched is None

    # Query from correct workspace returns the node
    fetched_correct = store.get_node(node_id="valve-1", workspace_id="tenant-alpha")
    assert fetched_correct is not None

def test_edge_upsert_and_queries(temp_graph_db):
    store = temp_graph_db
    # Create two nodes
    n1 = GraphNode(node_id="sop-fuel-flow", workspace_id="ws-1", name="SOP Fuel Flow", entity_type="procedure")
    n2 = GraphNode(node_id="valve-101", workspace_id="ws-1", name="Fuel Valve 101", entity_type="equipment")
    store.upsert_node(n1)
    store.upsert_node(n2)
    
    edge = GraphEdge(
        edge_id="e-1",
        workspace_id="ws-1",
        source_id="sop-fuel-flow",
        target_id="valve-101",
        edge_type="references",
        confidence=0.95,
        evidence_ids=["eu-101", "eu-102"],
        properties={"step": 3}
    )
    store.upsert_edge(edge)
    
    # Query outgoing edges
    outgoing = store.get_edges(workspace_id="ws-1", source_id="sop-fuel-flow")
    assert len(outgoing) == 1
    assert outgoing[0].edge_id == "e-1"
    assert outgoing[0].edge_type == "references"
    assert outgoing[0].confidence == 0.95
    assert "eu-101" in outgoing[0].evidence_ids
    assert outgoing[0].properties["step"] == 3

    # Query with wrong workspace returns empty
    empty_edges = store.get_edges(workspace_id="ws-2", source_id="sop-fuel-flow")
    assert len(empty_edges) == 0

def test_multi_hop_neighbors_and_paths(temp_graph_db):
    store = temp_graph_db
    ws = "ws-test"
    # A -> B -> C -> D
    nodes = [
        GraphNode(node_id="A", workspace_id=ws, name="Node A", entity_type="equipment"),
        GraphNode(node_id="B", workspace_id=ws, name="Node B", entity_type="equipment"),
        GraphNode(node_id="C", workspace_id=ws, name="Node C", entity_type="equipment"),
        GraphNode(node_id="D", workspace_id=ws, name="Node D", entity_type="equipment"),
    ]
    for n in nodes:
        store.upsert_node(n)
        
    edges = [
        GraphEdge(edge_id="e1", workspace_id=ws, source_id="A", target_id="B", edge_type="references", confidence=1.0),
        GraphEdge(edge_id="e2", workspace_id=ws, source_id="B", target_id="C", edge_type="corroborates", confidence=0.9),
        GraphEdge(edge_id="e3", workspace_id=ws, source_id="C", target_id="D", edge_type="references", confidence=0.8),
    ]
    for e in edges:
        store.upsert_edge(e)
        
    # 1-hop from A
    hop1 = store.get_neighbors(node_id="A", workspace_id=ws, max_depth=1)
    assert "B" in hop1
    assert "C" not in hop1
    
    # 2-hop from A
    hop2 = store.get_neighbors(node_id="A", workspace_id=ws, max_depth=2)
    assert "B" in hop2
    assert "C" in hop2
    assert "D" not in hop2

    # Path finding A -> D
    paths = store.find_paths(source_id="A", target_id="D", workspace_id=ws, max_depth=4)
    assert len(paths) >= 1
    assert paths[0] == ["A", "B", "C", "D"]

