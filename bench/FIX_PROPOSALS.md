# AeroMind — Proposed Minimal Fixes

These are three targeted fixes to close the most critical gaps between the
code and the presentation claims. **Do not apply yet** — review first.

---

## Fix (a): Fail-Closed Model Resolution

**Problem:** When Ollama returns 404 for a requested model (e.g. `qwen2.5-math:7b`
is configured but not pulled), `model_service.py` L386-390 silently replaces the
model name with `settings.OLLAMA_MODEL` (qwen2.5:3b) and retries. The user and the
DAG trace both show the specialist model name, but qwen2.5:3b actually ran.

**Fix:** Raise an error instead of falling back. Return a clear error message
through the SSE stream so the frontend can display it.

**File:** `backend/model_service.py`, lines 385-390

**Current code:**
```python
# If model not found (404), fall back to default model
if resp.status_code == 404 and selected_model != settings.OLLAMA_MODEL:
    print(f"[AeroMind Debug] Model '{selected_model}' not found in Ollama. Falling back to '{settings.OLLAMA_MODEL}'...")
    generate_payload["model"] = settings.OLLAMA_MODEL
    if "images" in generate_payload and not any(v in settings.OLLAMA_MODEL.lower() for v in ["gemma4", "vision", "vl"]):
        del generate_payload["images"]
```

**Proposed replacement:**
```python
# FAIL-CLOSED: If the specialist model is not installed, abort this node.
# Do NOT silently fall back — that hides the real model from traces and evals.
if resp.status_code == 404 and selected_model != settings.OLLAMA_MODEL:
    err_msg = (
        f"Model '{selected_model}' (capability={capability}) is not installed. "
        f"Run: ollama pull {selected_model}"
    )
    print(f"[AeroMind FAIL-CLOSED] {err_msg}")
    await queue.put(f"\n[MODEL_MISSING:{selected_model}] {err_msg}")
    await queue.put(None)
    return
```

**Effort:** ~15 minutes. 6 lines changed, no new dependencies.

**Impact:** The system becomes honest about which model actually runs. Traces
and evaluation scores will be accurate. The frontend already handles `[ERROR:…]`
tokens so the user gets a clear message.

---

## Fix (b): Real Optimizer/Verifier LLM Call

**Problem:** `agent_orchestrator.py` L406-427 emits an `[AGENT_STATUS]` event
saying "safety_validator" is running and an `[AGENT_THOUGHT]` with a hardcoded
thought string, but **never actually calls any model**. The verification is
cosmetic — the user sees a UI card saying "verified" but no LLM reviewed anything.

**Fix:** Add a real Ollama call that sends the synthesised response to the
verification model for a one-pass audit. Stream the result as a thought.

**File:** `backend/agent_orchestrator.py`, after line 417

**Proposed addition** (insert between the AGENT_STATUS yield and the hardcoded thought):
```python
        # ── REAL VERIFICATION CALL ─────────────────────────────────
        verification_prompt = (
            f"You are a safety and accuracy auditor for military aircraft documentation.\n"
            f"Review the following AI-generated response for:\n"
            f"1. Factual accuracy against the source manual\n"
            f"2. Safety-critical errors (wrong procedures, limits, values)\n"
            f"3. Hallucinated information not in the source\n\n"
            f"User question: {user_query}\n\n"
            f"AI response:\n{full_response}\n\n"
            f"Provide a brief audit verdict (PASS/CAUTION/FAIL) with specific issues found."
        )
        verifier_response = ""
        async for v_token in model_service_instance.stream_response(
            aircraft_id,
            [{"role": "user", "content": verification_prompt}],
            context="",
            capability="verification",
        ):
            verifier_response += v_token

        val_thought = verifier_response.strip() if verifier_response.strip() else (
            "Cross-verifying procedure against safety protocols. No issues found."
        )
```

**Also:** Remove the hardcoded `val_thought` string at lines 410-414 since
the LLM now produces the real thought.

**Effort:** ~30 minutes. ~20 lines added, the verification model needs to be
installed (`qwen2.5:3b-instruct` or reuse `qwen2.5:3b`).

**Impact:** The "verification" stage becomes real. The LLM output gets logged
in traces and visible in the Prompt Inspector. However, this doubles the
end-to-end latency since it's a sequential call. On CPU, expect +20-40 seconds
per query.

---

## Fix (c): Real ColPali/ColQwen2 Embeddings

**Problem:** `colpali_retrieval_service.py` L136-159 generates deterministic
pseudo-random vectors instead of real visual embeddings. The ColQwen2 model
download is gated behind a try/except that silently fails if the weights aren't
cached. This means all "visual RAG" retrieval is effectively random.

**Fix:** 
1. Set `ENABLE_COLPALI_DOWNLOAD=true` (currently implicit false)
2. Download ColQwen2 weights (~3 GB)
3. Index only a subset of pages (first 20 pages of mig21bis.pdf) since we are CPU-only
4. The existing code already has the real embedding path — we just need the model weights

**File:** `backend/config.py` — no code changes needed, just model download.

**Steps:**
```bash
# 1. Download ColQwen2 model weights (~3 GB)
python3 -c "
from colpali_engine.models import ColQwen2, ColQwen2Processor
model = ColQwen2.from_pretrained(
    'vidore/colqwen2-v1.0',
    torch_dtype='float32',
    device_map='cpu',
)
processor = ColQwen2Processor.from_pretrained('vidore/colqwen2-v1.0')
print('ColQwen2 downloaded and cached.')
"

# 2. Re-index first 20 pages only (CPU-safe)
# The existing index_document() method handles this, but we need to
# modify MAX_VISUAL_PAGES in .env or pass a limit:
# MAX_VISUAL_PAGES=20
```

**File change:** `backend/colpali_retrieval_service.py` line 122-134 — no code
change needed. The try/except will succeed once the weights are cached.

**Optional improvement:** Add an explicit check + log at startup:
```python
# In _load_model(), after the try/except:
if not self.model:
    print("[ColPali] ⚠️ WARNING: Running with FALLBACK vectors. "
          "Retrieval results are NOT based on visual content. "
          "Run: python3 -c 'from colpali_engine.models import ColQwen2; "
          "ColQwen2.from_pretrained(\"vidore/colqwen2-v1.0\")'")
```

**Effort:** ~45 minutes (mostly download time). Zero code changes to the
retrieval logic itself — it already supports real embeddings.

**Impact:** Visual retrieval becomes functional. The system will actually find
relevant pages based on visual content (diagrams, tables, schematics) rather
than random noise. However, CPU-only indexing of 20 pages will take ~10-15
minutes. Query latency will increase by ~2-5 seconds per retrieval on CPU.

---

## Summary

| Fix | Effort | Risk | Impact on Benchmarks |
|-----|--------|------|---------------------|
| (a) Fail-closed | 15 min | Low — error path is already handled | B5: C1 may error if models missing. Honest traces. |
| (b) Real verifier | 30 min | Medium — doubles latency | B1: adds one more model call. B5: C1 latency increases. |
| (c) Real ColPali | 45 min + download | Low — existing code path | B8: retrieval benchmarks become meaningful. |

**Total effort:** ~90 minutes + model download time.
**Recommended order:** (a) → (c) → (b), because (a) is the smallest change
with the biggest honesty gain, and (c) unlocks retrieval benchmarks.
