import pytest
import tempfile
import os
from memory.store import MemoryStore, MemoryEntry
from memory.scoping import can_access, filter_by_scope
from agents.memory_agent import MemoryAgent

@pytest.fixture
def temp_memory_store():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_memory.sqlite3")
        store = MemoryStore(db_path=db_path)
        yield store

def test_cross_workspace_isolation_adversarial(temp_memory_store):
    """
    Pitfall §11.3 & Task 3.6:
    Write in Workspace A, query from Workspace B -> strictly empty or denied.
    """
    store = temp_memory_store
    agent = MemoryAgent(store=store)
    
    # Store sensitive maintenance procedure in Workspace Alpha
    entry_alpha = MemoryEntry(
        id="mem-1",
        workspace_id="workspace-alpha",
        user_id="engineer-1",
        memory_type="procedure",
        key="hydraulic_press_calib",
        value={"calib_psi": 220, "operator": "Capt. Smith"},
        classification_level="INTERNAL"
    )
    store.upsert(entry_alpha)
    
    # Query from Workspace Alpha succeeds
    read_alpha = agent.recall(
        key="hydraulic_press_calib",
        workspace_id="workspace-alpha",
        user_clearance="INTERNAL"
    )
    assert read_alpha is not None
    assert read_alpha.value["calib_psi"] == 220
    
    # Adversarial query from Workspace Beta must return None
    read_beta = agent.recall(
        key="hydraulic_press_calib",
        workspace_id="workspace-beta",
        user_clearance="INTERNAL"
    )
    assert read_beta is None
    
    # Search in Beta returns empty
    search_beta = agent.search(
        workspace_id="workspace-beta",
        user_clearance="TOP_SECRET",
        query="hydraulic"
    )
    assert len(search_beta) == 0

def test_classification_level_and_downgrade(temp_memory_store):
    """
    Clearance hierarchy enforcement:
    A user with CONFIDENTIAL clearance cannot read SECRET or TOP_SECRET memory.
    Downgrading clearance restricts reads immediately.
    """
    store = temp_memory_store
    agent = MemoryAgent(store=store)
    ws = "ws-defense"
    
    store.upsert(MemoryEntry(
        id="mem-sec",
        workspace_id=ws,
        user_id="pilot-99",
        memory_type="fact",
        key="radar_frequency_hop",
        value={"hopping_rate_hz": 1200},
        classification_level="SECRET"
    ))
    
    # User with SECRET clearance can read
    read_secret = agent.recall(
        key="radar_frequency_hop",
        workspace_id=ws,
        user_clearance="SECRET"
    )
    assert read_secret is not None
    assert read_secret.value["hopping_rate_hz"] == 1200
    
    # User with CONFIDENTIAL clearance is denied
    read_conf = agent.recall(
        key="radar_frequency_hop",
        workspace_id=ws,
        user_clearance="CONFIDENTIAL"
    )
    assert read_conf is None
    
    # User with INTERNAL clearance is denied
    read_internal = agent.recall(
        key="radar_frequency_hop",
        workspace_id=ws,
        user_clearance="INTERNAL"
    )
    assert read_internal is None
    
    # Search with lower clearance does not expose SECRET memory
    search_results = agent.search(
        workspace_id=ws,
        user_clearance="CONFIDENTIAL",
        query="radar"
    )
    assert len(search_results) == 0

