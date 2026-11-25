import inspect
import re
from pathlib import Path

FORBIDDEN_FIXTURE_TERMS = [
    "waypoint",
    "storage bin",
    "o-rings",
    "requisition",
    "debrief",
    "fl250",
    "maint_rep_01",
    "telem_log_01",
    "nav_debrief_99",
    "warehouse_po_99"
]

def test_correlation_agent_contains_no_fixture_special_casing():
    """
    Pitfall §11.9 & Task 3.5:
    Ensure that correlation_agent.py does not contain any hard-coded keywords
    or special-casing for the negative control fixtures.
    """
    agent_path = Path(__file__).resolve().parent.parent.parent / "agents" / "correlation_agent.py"
    assert agent_path.exists(), f"Agent file not found: {agent_path}"
    
    code = agent_path.read_text(encoding="utf-8").lower()
    
    for term in FORBIDDEN_FIXTURE_TERMS:
        pattern = r"\b" + re.escape(term.lower()) + r"\b"
        match = re.search(pattern, code)
        assert match is None, f"Found hardcoded fixture term '{term}' in correlation_agent.py! General logic must be used instead."
