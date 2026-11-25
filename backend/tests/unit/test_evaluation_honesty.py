import pytest
from evaluation_service import evaluation_service


def test_empty_response_faithfulness_and_safety():
    """An empty response must score <= 10 faithfulness and never show VERIFIED_SAFE."""
    report = evaluation_service.evaluate_response(
        query="MiG-21 emergency engine relight procedure",
        response_text="",
        retrieved_contexts=[
            {
                "page_number": 42,
                "text": "Engine relight procedure: throttle IDLE, emergency fuel pump ON, minimum speed 550 km/h.",
                "is_schematic": True,
            }
        ],
    )
    faithfulness = report.get("heuristic_faithfulness", report.get("faithfulness_score"))
    assert faithfulness is not None
    assert faithfulness <= 10, f"Empty response faithfulness must be <= 10, got {faithfulness}"
    assert report.get("safety_compliance") != "VERIFIED_SAFE", "Empty response must never be marked VERIFIED_SAFE"


def test_nonsense_against_unrelated_context():
    """Nonsense against unrelated context must score < 30 faithfulness."""
    report = evaluation_service.evaluate_response(
        query="Normal flight operations",
        response_text="The quick brown fox jumps over the lazy dog in the middle of summer sunshine.",
        retrieved_contexts=[
            {
                "page_number": 12,
                "text": "MiG-21 hydraulic pressure system operates at 210 kg/cm2 with dual redundant lines.",
                "is_schematic": False,
            }
        ],
    )
    faithfulness = report.get("heuristic_faithfulness", report.get("faithfulness_score"))
    assert faithfulness is not None
    assert faithfulness < 30, f"Nonsense against unrelated context must score < 30, got {faithfulness}"
    assert report.get("safety_compliance") != "VERIFIED_SAFE", "Never mark unverified output as VERIFIED_SAFE"


def test_non_emergency_query_never_verified_safe():
    """Non-emergency queries must never produce the misleading VERIFIED_SAFE badge."""
    report = evaluation_service.evaluate_response(
        query="What is the main gear tire pressure?",
        response_text="Main gear tire pressure is 8 atmospheres.",
        retrieved_contexts=[
            {"page_number": 5, "text": "Main landing gear tire pressure 8 atmospheres.", "is_schematic": False}
        ],
    )
    assert report.get("safety_compliance") != "VERIFIED_SAFE"


def test_heuristic_keys_present():
    """Outputs must be renamed to heuristic_* for honesty."""
    report = evaluation_service.evaluate_response(
        query="MiG-21 climb rate",
        response_text="Climb rate is 120 m/s at sea level.",
        retrieved_contexts=[{"page_number": 10, "text": "Maximum rate of climb 120 m/s.", "is_schematic": False}],
    )
    assert "heuristic_faithfulness" in report
    assert "heuristic_citation" in report
    assert "heuristic_safety" in report

