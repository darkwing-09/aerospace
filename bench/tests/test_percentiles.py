"""
bench/tests/test_percentiles.py
─────────────────────────────────────────────────────────────────
Unit tests for benchmark percentile calculation routines (Task 2.4).
"""

import pytest
from bench.percentiles import calculate_percentile, calculate_stats


def test_empty_list():
    assert calculate_percentile([], 50.0) is None
    stats = calculate_stats([])
    assert stats["median"] is None
    assert stats["p95"] is None
    assert stats["count"] == 0


def test_single_element():
    val = calculate_percentile([42.0], 95.0)
    assert val == 42.0
    stats = calculate_stats([42.0])
    assert stats["median"] == 42.0
    assert stats["p95"] == 42.0
    assert stats["count"] == 1


def test_five_samples_percentile():
    # 5 samples: [10, 20, 30, 40, 50]
    # Old bug: index = int(5 * 0.95) - 1 = 3 (value 40, which was p75 not p95)
    # Correct linear interpolation:
    # rank = 0.95 * (5 - 1) = 3.8
    # val = s[3]*0.2 + s[4]*0.8 = 40*0.2 + 50*0.8 = 48.0
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    p95 = calculate_percentile(samples, 95.0)
    assert p95 == 48.0
    assert p95 > 40.0, "p95 must not fall back to the 4th sample of 5"


def test_twenty_samples_percentile():
    # 20 samples: integers 1 to 20
    # rank = 0.95 * 19 = 18.05
    # val = 19 * 0.95 + 20 * 0.05 = 19.05
    samples = list(range(1, 21))
    p50 = calculate_percentile(samples, 50.0)
    p95 = calculate_percentile(samples, 95.0)
    assert p50 == 10.5
    assert abs(p95 - 19.05) < 1e-4


def test_hundred_samples_percentile():
    # 100 samples from 1 to 100
    samples = list(range(1, 101))
    p50 = calculate_percentile(samples, 50.0)
    p95 = calculate_percentile(samples, 95.0)
    assert p50 == 50.5
    assert abs(p95 - 95.05) < 1e-4


def test_calculate_stats_structure():
    samples = [100.0, 200.0, 300.0, 400.0, 500.0]
    stats = calculate_stats(samples)
    assert stats["median"] == 300.0
    assert stats["min"] == 100.0
    assert stats["max"] == 500.0
    assert stats["count"] == 5
    assert stats["p95"] == 480.0
    assert stats["values"] == samples


def test_invalid_percentile_range():
    with pytest.raises(ValueError):
        calculate_percentile([1, 2, 3], -1.0)
    with pytest.raises(ValueError):
        calculate_percentile([1, 2, 3], 101.0)
