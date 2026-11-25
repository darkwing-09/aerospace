import pytest
from knowledge.entity_resolution import (
    resolve_entity_pair,
    benchmark_entity_resolution,
    LABELLED_BENCHMARK_PAIRS
)

def test_benchmark_dataset_integrity():
    # Must have at least 20 hand-labelled pairs
    assert len(LABELLED_BENCHMARK_PAIRS) >= 20
    positives = [p for p in LABELLED_BENCHMARK_PAIRS if p["is_match"]]
    negatives = [p for p in LABELLED_BENCHMARK_PAIRS if not p["is_match"]]
    assert len(positives) >= 8
    assert len(negatives) >= 8

def test_entity_resolution_floors():
    """
    Task 3.2 acceptance criteria:
    Assert precision >= 0.95 and recall >= 0.80 on the 20 hand-labelled benchmark pairs.
    High precision prevents bogus graph links.
    """
    metrics = benchmark_entity_resolution(approach="hybrid_canonical")
    precision = metrics["precision"]
    recall = metrics["recall"]
    f1 = metrics["f1"]
    
    print(f"\n[Entity Resolution Benchmark] Hybrid Canonical: Precision={precision:.3f}, Recall={recall:.3f}, F1={f1:.3f}")
    assert precision >= 0.95, f"Precision floor violated: {precision} < 0.95"
    assert recall >= 0.80, f"Recall floor violated: {recall} < 0.80"

def test_critical_hard_negatives():
    """
    Distinct equipment numbers must never resolve to the same entity.
    """
    # Number differences must strictly fail
    res1 = resolve_entity_pair("Fuel pump No.1", "Fuel pump No.2")
    assert not res1["is_match"]
    assert res1["confidence"] < 0.5
    
    res2 = resolve_entity_pair("Radar RP-22", "Radar RP-21")
    assert not res2["is_match"]
    assert res2["confidence"] < 0.5
    
    res3 = resolve_entity_pair("Altimeter VD-20", "Altimeter VD-10")
    assert not res3["is_match"]
    assert res3["confidence"] < 0.5

def test_canonical_abbreviations_match():
    # Abbreviation and prefix matches
    res1 = resolve_entity_pair("Pump 104", "P-104")
    assert res1["is_match"]
    assert res1["confidence"] >= 0.75
    
    res2 = resolve_entity_pair("MiG-21bis", "MiG 21 bis")
    assert res2["is_match"]
    assert res2["confidence"] >= 0.80
    
    res3 = resolve_entity_pair("Airspeed Indicator", "ASI")
    assert res3["is_match"]
    assert res3["confidence"] >= 0.75

