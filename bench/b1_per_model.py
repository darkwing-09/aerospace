#!/usr/bin/env python3
"""
B1 — Per-Model Performance (AS_IS, CPU-only)
─────────────────────────────────────────────
For each locally-installed Ollama model:
  - Cold load time (keep_alive=0 then first call)
  - Warm time-to-first-token
  - Tokens/second (eval_count / eval_duration)
  - Peak RSS of the ollama process
  - Peak system RAM used

Repeats each measurement 5 times, reports median and p95.
"""

import json, time, statistics, subprocess, os, sys, re
from pathlib import Path
import httpx

OLLAMA = "http://127.0.0.1:11434"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

PROMPT = (
    "Explain the startup procedure for a turbojet engine in exactly 500 words. "
    "Include fuel flow sequence, ignition timing, spool-up RPM targets, "
    "EGT limits, and oil pressure checks. Be precise and technical."
)

REPEATS = 5


def get_local_models():
    """Return list of locally-installed (non-cloud) model names."""
    r = httpx.get(f"{OLLAMA}/api/tags", timeout=10)
    r.raise_for_status()
    models = []
    for m in r.json().get("models", []):
        size = m.get("size", 0)
        if size and size > 1000:  # skip cloud stubs
            models.append(m["name"])
    return models


def unload_all():
    """Force unload all models by setting keep_alive=0."""
    try:
        tags = httpx.get(f"{OLLAMA}/api/tags", timeout=10).json()
        for m in tags.get("models", []):
            if m.get("size", 0) > 1000:
                httpx.post(f"{OLLAMA}/api/generate", json={
                    "model": m["name"], "prompt": "", "keep_alive": 0
                }, timeout=30)
    except Exception:
        pass
    time.sleep(2)


def get_ollama_rss_kb():
    """Get RSS of ollama_llama_server or ollama process in KB."""
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "rss,comm"], text=True, timeout=5
        )
        total = 0
        for line in out.strip().split("\n"):
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and "ollama" in parts[1].lower():
                total += int(parts[0])
        return total
    except Exception:
        return 0


def get_system_mem_used_kb():
    """Get used system memory in KB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            info = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", 0)
        return total - avail
    except Exception:
        return 0


def bench_model(model_name: str) -> dict:
    results = {
        "model": model_name,
        "cold_load_ms": [],
        "warm_ttft_ms": [],
        "tokens_per_sec": [],
        "peak_rss_mb": [],
        "peak_sys_ram_mb": [],
        "total_duration_ms": [],
        "prompt_eval_tps": [],
    }

    for i in range(REPEATS):
        # ── Cold load ──────────────────────────────
        unload_all()
        time.sleep(1)

        rss_before = get_ollama_rss_kb()
        ram_before = get_system_mem_used_kb()

        t0 = time.monotonic()
        resp = httpx.post(f"{OLLAMA}/api/generate", json={
            "model": model_name,
            "prompt": PROMPT,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 200,
                "num_ctx": 2048,
            },
            "keep_alive": "5m",
        }, timeout=600)
        wall_ms = (time.monotonic() - t0) * 1000
        data = resp.json()

        rss_after = get_ollama_rss_kb()
        ram_after = get_system_mem_used_kb()

        load_ns = data.get("load_duration", 0)
        prompt_eval_ns = data.get("prompt_eval_duration", 0)
        eval_ns = data.get("eval_duration", 0)
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)
        total_ns = data.get("total_duration", 0)

        cold_load_ms = load_ns / 1e6
        tok_per_sec = (eval_count / (eval_ns / 1e9)) if eval_ns > 0 else 0
        prompt_tps = (prompt_eval_count / (prompt_eval_ns / 1e9)) if prompt_eval_ns > 0 else 0

        # TTFT = load + prompt eval
        ttft_ms = (load_ns + prompt_eval_ns) / 1e6

        results["cold_load_ms"].append(round(cold_load_ms, 1))
        results["warm_ttft_ms"].append(round(ttft_ms, 1))  # first iter is cold
        results["tokens_per_sec"].append(round(tok_per_sec, 2))
        results["peak_rss_mb"].append(round(max(rss_after, rss_before) / 1024, 1))
        results["peak_sys_ram_mb"].append(round(max(ram_after, ram_before) / 1024, 1))
        results["total_duration_ms"].append(round(total_ns / 1e6, 1))
        results["prompt_eval_tps"].append(round(prompt_tps, 2))

        # ── Warm call ──────────────────────────────
        if i == 0:
            # do a second call while model is warm to get warm TTFT
            t1 = time.monotonic()
            resp2 = httpx.post(f"{OLLAMA}/api/generate", json={
                "model": model_name,
                "prompt": PROMPT,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                    "num_ctx": 2048,
                },
            }, timeout=600)
            d2 = resp2.json()
            warm_load = d2.get("load_duration", 0)
            warm_pe = d2.get("prompt_eval_duration", 0)
            warm_ttft = (warm_load + warm_pe) / 1e6
            results["warm_ttft_ms_actual"] = round(warm_ttft, 1)
            results["warm_tps"] = round(
                (d2.get("eval_count", 0) / (d2.get("eval_duration", 1) / 1e9))
                if d2.get("eval_duration", 0) > 0 else 0, 2
            )

    # Compute stats
    def stats(arr):
        if not arr:
            return {"median": None, "p95": None, "values": arr}
        s = sorted(arr)
        med = statistics.median(s)
        p95_idx = max(0, int(len(s) * 0.95) - 1)
        return {"median": round(med, 2), "p95": round(s[p95_idx], 2), "values": arr}

    summary = {
        "model": model_name,
        "cold_load_ms": stats(results["cold_load_ms"]),
        "warm_ttft_ms": results.get("warm_ttft_ms_actual", None),
        "warm_tps": results.get("warm_tps", None),
        "generation_tps": stats(results["tokens_per_sec"]),
        "prompt_eval_tps": stats(results["prompt_eval_tps"]),
        "peak_rss_mb": stats(results["peak_rss_mb"]),
        "peak_sys_ram_mb": stats(results["peak_sys_ram_mb"]),
        "total_duration_ms": stats(results["total_duration_ms"]),
        "raw": results,
    }
    return summary


def main():
    models = get_local_models()
    print(f"[B1] Found {len(models)} local models: {models}")

    all_results = []
    for m in models:
        print(f"\n[B1] Benchmarking: {m}")
        try:
            r = bench_model(m)
            all_results.append(r)
            print(f"  Cold load median: {r['cold_load_ms']['median']} ms")
            print(f"  Gen tok/s median: {r['generation_tps']['median']}")
            print(f"  Peak RSS median: {r['peak_rss_mb']['median']} MB")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({"model": m, "error": str(e)})

    out_file = RESULTS_DIR / "b1_per_model_AS_IS.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[B1] Results saved to {out_file}")


if __name__ == "__main__":
    main()
