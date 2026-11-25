"""
bench/load.py
─────────────────────────────────────────────────────────────────
Concurrency & Load Benchmark for AeroMind 2.0 (Task 4.3 / PLAN §8.13).
Measures p50, p95, p99 latencies and throughput under concurrency levels (4, 8, 16).
Uses linear interpolation percentile calculations from bench.percentiles.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure backend and bench are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

# Resolve venv site-packages if needed
VENV_SITE = REPO_ROOT / "backend" / "venv" / "lib" / "python3.13" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

from bench.percentiles import calculate_percentile
from orchestration.graph import run_task
from config import HARDWARE


BENCHMARK_TASKS = [
    "What is the maximum hydraulic pressure for MiG-21 relief valves?",
    "Check emergency fuel isolation procedure when pressure drops below 20 PSI",
    "Calculate fuel flow rate at 5000 meters for 15 minutes",
    "Inspect landing gear retraction hydraulic sequence and tolerances",
]


def execute_single_query(task_text: str, worker_id: int) -> Dict[str, Any]:
    """Executes a single realistic pipeline request and measures elapsed wall time."""
    t0 = time.perf_counter()
    succeeded = True
    error_msg = None
    try:
        res = run_task(task_text, workspace_id=f"ws_load_worker_{worker_id}")
        if not res or not res.get("done"):
            succeeded = False
            error_msg = "Task did not return done=True"
    except Exception as exc:
        succeeded = False
        error_msg = str(exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "latency_ms": elapsed_ms,
        "succeeded": succeeded,
        "error": error_msg,
    }


def run_concurrency_level(concurrency: int, requests_per_worker: int) -> Dict[str, Any]:
    """Runs a pool of workers at the specified concurrency level."""
    total_requests = concurrency * requests_per_worker
    latencies: List[float] = []
    errors: int = 0

    print(f"\n[Load Test] Concurrency={concurrency} (total {total_requests} requests)...")
    start_time = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(total_requests):
            task_idx = i % len(BENCHMARK_TASKS)
            task_text = BENCHMARK_TASKS[task_idx]
            worker_id = i % concurrency
            futures.append(executor.submit(execute_single_query, task_text, worker_id))

        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            latencies.append(res["latency_ms"])
            if not res["succeeded"]:
                errors += 1

    total_wall_sec = time.perf_counter() - start_time
    throughput_rps = (total_requests / total_wall_sec) if total_wall_sec > 0 else 0.0

    p50 = calculate_percentile(latencies, 50.0) or 0.0
    p95 = calculate_percentile(latencies, 95.0) or 0.0
    p99 = calculate_percentile(latencies, 99.0) or 0.0

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "wall_time_seconds": round(total_wall_sec, 2),
        "throughput_rps": round(throughput_rps, 2),
        "errors": errors,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "min_ms": round(min(latencies), 2) if latencies else 0.0,
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="AeroMind 2.0 Concurrency and Load Benchmark")
    parser.add_argument("--concurrency", type=str, default="4,8,16", help="Comma-separated concurrency levels")
    parser.add_argument("--requests-per-worker", type=int, default=2, help="Number of requests per worker thread")
    parser.add_argument("--out", type=str, default="bench/results/load_tier_concurrency.json", help="Output JSON path")
    args = parser.parse_args()

    levels = [int(c.strip()) for c in args.concurrency.split(",") if c.strip()]
    tier_name = HARDWARE.get("tier", "cpu_lite")
    hw_info = HARDWARE

    print(f"=================================================================")
    print(f" AeroMind 2.0 Concurrency & Load Benchmark (Task 4.3)")
    print(f" Hardware Tier: {tier_name}")
    print(f" Concurrency Levels: {levels}")
    print(f" Hardware Note: dev hardware (i7-1185G7, CPU only), not representative")
    print(f"=================================================================")

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware_tier": tier_name,
        "hardware_info": hw_info,
        "hardware_note": "dev hardware (i7-1185G7, CPU only), not representative",
        "concurrency_benchmarks": [],
    }

    print("\n| Concurrency | Requests | Wall Time (s) | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Errors |")
    print("|-------------|----------|---------------|-------------------|----------|----------|----------|--------|")

    for c in levels:
        metrics = run_concurrency_level(c, requests_per_worker=args.requests_per_worker)
        results["concurrency_benchmarks"].append(metrics)
        print(f"| {metrics['concurrency']:11d} | {metrics['total_requests']:8d} | {metrics['wall_time_seconds']:13.2f} | {metrics['throughput_rps']:17.2f} | {metrics['p50_ms']:8.2f} | {metrics['p95_ms']:8.2f} | {metrics['p99_ms']:8.2f} | {metrics['errors']:6d} |")

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\n[OK] Results written to {out_path}")


if __name__ == "__main__":
    main()
