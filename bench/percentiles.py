"""
bench/percentiles.py
─────────────────────────────────────────────────────────────────
Accurate percentile and statistical calculation routines for AeroMind benchmarks.
Uses linear interpolation between nearest ranks (equivalent to numpy percentile / NIST).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Union


def calculate_percentile(values: List[float], p: float) -> Optional[float]:
    """
    Computes the p-th percentile (0.0 <= p <= 100.0) using linear interpolation.
    
    Formula:
        rank = (p / 100) * (N - 1)
        val = s[low] * (1 - weight) + s[high] * weight
    """
    if not values:
        return None
    if p < 0.0 or p > 100.0:
        raise ValueError(f"Percentile must be between 0 and 100, got {p}")

    s = sorted(values)
    n = len(s)
    if n == 1:
        return float(s[0])

    rank = (p / 100.0) * (n - 1)
    low = math.floor(rank)
    high = math.ceil(rank)

    if low == high:
        return float(s[int(low)])

    weight = rank - low
    val = s[low] * (1.0 - weight) + s[high] * weight
    return float(val)


def calculate_stats(arr: List[float]) -> Dict[str, Any]:
    """
    Calculates summary statistics for a metric:
    - median (p50)
    - p95
    - min
    - max
    - sample count
    - raw values
    """
    if not arr:
        return {
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
            "count": 0,
            "values": arr,
        }

    s = sorted(arr)
    med = calculate_percentile(s, 50.0)
    p95 = calculate_percentile(s, 95.0)

    return {
        "median": round(med, 2) if med is not None else None,
        "p95": round(p95, 2) if p95 is not None else None,
        "min": round(min(s), 2),
        "max": round(max(s), 2),
        "count": len(arr),
        "values": arr,
    }
