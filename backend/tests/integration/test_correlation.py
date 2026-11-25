import json
import pytest
from pathlib import Path
from agents.correlation_agent import CorrelationAgent, CorrelationResult

@pytest.fixture
def fixtures_data():
    fixtures_path = Path(__file__).resolve().parent.parent / "fixtures" / "correlation_fixtures.json"
    with open(fixtures_path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_positive_correlation_case(fixtures_data):
    agent = CorrelationAgent()
    pos = fixtures_data["positive_case"]
    
    result = agent.correlate(
        doc_a=pos["doc_a"],
        doc_b=pos["doc_b"],
        workspace_id="ws-test"
    )
    
    assert isinstance(result, CorrelationResult)
    assert result.related is True
    assert result.confidence >= 0.75
    assert result.edge_type in ["CORROBORATES", "REFERENCES", "CO_OCCURS"]
    assert len(result.shared_entities) >= 1
    assert "Main Fuel Pump 104" in result.shared_entities or "P-104" in result.shared_entities or "Aircraft #21" in result.shared_entities
    assert len(result.explanation) > 20

def test_negative_control_correlation_case(fixtures_data):
    agent = CorrelationAgent()
    neg = fixtures_data["negative_case"]
    
    result = agent.correlate(
        doc_a=neg["doc_a"],
        doc_b=neg["doc_b"],
        workspace_id="ws-test"
    )
    
    assert isinstance(result, CorrelationResult)
    assert result.related is False
    assert result.confidence < 0.50
    assert result.edge_type == "NO_RELIABLE_CONNECTION"
    assert len(result.shared_entities) == 0
    assert "no reliable" in result.explanation.lower() or "unrelated" in result.explanation.lower() or "distinct" in result.explanation.lower()

