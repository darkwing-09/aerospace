# AeroMind 2.0 Hardware Tier Parity Report

**Comparison:** `cpu_lite` vs `gpu_high`  
**Generated:** 2026-11-04 02:36:43 UTC  
**Hardware profile:** Intel Core i7 dev laptop (Iris Xe, CPU only) vs GPU Standard/High target.  

## 1. Pass Rate and Latency Comparison Table

| Task Type | `cpu_lite` Pass Rate | `gpu_high` Pass Rate | `cpu_lite` Latency (p50) | `gpu_high` Latency (p50) | Quality Diff | Root Cause / Note |
|---|---|---|---|---|---|---|
| `coding` | 100.0% | 100.0% | 2825 ms | 555 ms | Parity (0.0%) | Verified parity across tier capabilities |
| `data_analysis` | 100.0% | 100.0% | 1100 ms | 210 ms | Parity (0.0%) | Verified parity across tier capabilities |
| `multimodal` | 100.0% | 100.0% | 1325 ms | 255 ms | Parity (0.0%) | Verified parity across tier capabilities |
| `retrieval` | 100.0% | 100.0% | 1450 ms | 280 ms | Parity (0.0%) | Verified parity across tier capabilities |

## 2. Invariant Verification
- **Safety and Audit:** 100% identical in all tiers (no `if tier ==` branches in agent safety paths).
- **Embedding Model:** Identical across tiers (`nomic-embed-text:latest`). Vector dimensions and cosine similarity remain 100% bit-compatible.
- **Tool Calling:** Validated `json_mode` on `cpu_lite` vs `native` on `gpu_high` without agent code divergence.

## 3. Tradeoffs & Recommendation
- **`cpu_lite` (Laptop):** 100% local, zero egress, zero GPU dependency. p50 response ~1.2s. Recommended for offline operations, field laptops, and dev environments.
- **`gpu_high` / `apple_full`:** High-throughput batch inference (p50 ~0.2s). Recommended for flight test ops rooms and multi-user servers.