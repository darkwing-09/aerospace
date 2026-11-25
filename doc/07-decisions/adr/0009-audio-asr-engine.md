# ADR-0009: Local Offline ASR Audio Ingestion Engine
**Status**: Accepted   **Date**: 2026-11-04

## Context
AeroMind prototype originally relied on browser Web Speech APIs (`webkitSpeechRecognition`), which exfiltrates audio to cloud endpoints (Google speech servers) and fails in air-gapped or zero-egress environments. Task 3.8 and PLAN §8.3 / §11.1 require local, zero-egress audio transcription for pilot voice notes, cockpit radio logs, and technician audio memos.

### Requirements
1. **Zero Egress**: All ASR inference must run locally on device with zero cloud connectivity.
2. **`cpu_lite` Efficiency**: Model inference must operate within the Intel i7 laptop CPU resource budget without blocking LLM operations.
3. **Structured Timestamps**: Output must segment into timed speaker turns (`start_time_sec`, `end_time_sec`) embedded inside `EvidenceUnit.content_blocks`.
4. **Resilient Fallback**: In environments without CTranslate2/faster-whisper binaries, the system must not crash; it must extract audio metadata, compute acoustic energy intervals, and emit tagged `EvidenceUnit` units.

---

## Options Considered

### A. Cloud Speech-to-Text APIs (Google Cloud Speech, OpenAI Whisper API)
- **Rejected**: Complete violation of zero-egress requirement and air-gap target profile.

### B. Original PyTorch `openai-whisper`
- **Pros**: Reference implementation.
- **Cons**: High memory consumption, slow CPU execution (~3–5x real-time on i7), heavy PyTorch dependencies.

### C. `faster-whisper` (CTranslate2) with Deterministic Acoustic Fallback (Selected)
- **Pros**:
  - Up to 4x faster than PyTorch Whisper with 50% less RAM using 8-bit quantized weights (`int8` on CPU).
  - Native support for `whisper-tiny.en` and `whisper-base.en` models (<150 MB).
  - Precise word-level and segment-level timestamps.
  - Fully offline, air-gapped operation.
  - Deterministic signal fallback module when model weights are not loaded.

---

## Decision
Adopt **`faster-whisper`** architecture for local audio transcription in `backend/ingestion/extractors/audio.py`.
- Primary engine: `faster-whisper` (model: `base.en` or `tiny.en` in `cpu_lite`).
- Generates `EvidenceUnit` with `modality="audio"`, `source_type="audio"`, and `ContentBlock(block_type="speaker_turn", ...)`.
- Fallback mode: Deterministic signal analysis (WAV header inspection, sample rate, duration, and energy segmentation) with `evidence_tag=EvidenceTag.UNCERTAIN` when neural weights are absent.

