#!/usr/bin/env python3
"""
B2 — Model-Switch Overhead (AS_IS, CPU-only)
─────────────────────────────────────────────
Measures time to swap from model A to model B for every pair of
locally-installed models. Tests with keep_alive=0 (immediate unload).
"""

import json, time, statistics
from pathlib import Path
import httpx

OLLAMA = "http://127.0.0.1:11434"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SHORT_PROMPT = "What is 2+2? Answer in one word."
REPEATS = 3


def get_local_models():
    r = httpx.get(f"{OLLAMA}/api/tags", timeout=10)
    models = []
    for m in r.json().get("models", []):
        if m.get("size", 0) > 1000:
            models.append(m["name"])
    return models


def unload_model(model_name):
    """Unload a specific model."""
    try:
        httpx.post(f"{OLLAMA}/api/generate", json={
            "model": model_name, "prompt": "", "keep_alive": 0
        }, timeout=30)
    except Exception:
        pass
    time.sleep(1)


def load_and_query(model_name):
    """Load model and run a short query. Return Ollama timing dict."""
    resp = httpx.post(f"{OLLAMA}/api/generate", json={
        "model": model_name,
        "prompt": SHORT_PROMPT,
        "stream": False,
        "options": {"num_predict": 10, "num_ctx": 512},
    }, timeout=300)
    return resp.json()


def measure_switch(from_model, to_model):
    """Measure switch: load A, unload A, load B. Return switch_ms."""
    # Warm up A
    load_and_query(from_model)
    time.sleep(0.5)

    # Unload A
    t0 = time.monotonic()
    unload_model(from_model)

    # Load B
    data_b = load_and_query(to_model)
    switch_wall_ms = (time.monotonic() - t0) * 1000

    load_b_ms = data_b.get("load_duration", 0) / 1e6
    unload_model(to_model)

    return {
        "switch_wall_ms": round(switch_wall_ms, 1),
        "load_b_ms": round(load_b_ms, 1),
    }


def main():
    models = get_local_models()
    print(f"[B2] Found {len(models)} local models: {models}")

    results = []
    for from_m in models:
        for to_m in models:
            if from_m == to_m:
                continue
            pair_key = f"{from_m} → {to_m}"
            print(f"[B2] Measuring: {pair_key}")
            measurements = []
            for _ in range(REPEATS):
                try:
                    r = measure_switch(from_m, to_m)
                    measurements.append(r)
                except Exception as e:
                    print(f"  ERROR: {e}")

            if measurements:
                walls = [m["switch_wall_ms"] for m in measurements]
                loads = [m["load_b_ms"] for m in measurements]
                results.append({
                    "from": from_m,
                    "to": to_m,
                    "switch_wall_ms_median": round(statistics.median(walls), 1),
                    "load_b_ms_median": round(statistics.median(loads), 1),
                    "raw": measurements,
                })
                print(f"  Median wall: {results[-1]['switch_wall_ms_median']} ms")

    out_file = RESULTS_DIR / "b2_model_switch_AS_IS.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[B2] Results saved to {out_file}")


if __name__ == "__main__":
    main()
