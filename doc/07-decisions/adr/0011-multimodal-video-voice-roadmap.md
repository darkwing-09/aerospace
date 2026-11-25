# ADR-0011: Multimodal Roadmap — Video and Voice Strategy Post-V1
**Status**: Accepted   **Date**: 2026-11-04

## Context
AeroMind 2.0 requires strict air-gapped zero-egress operation across diverse hardware tiers:
`cpu_lite` (CPU-only laptop, e.g. Intel i7), `gpu_standard`, `gpu_high`, and `apple_full`.
During Phase 3 and Phase 4 benchmarks, compute and memory usage for audio, documents, and vision were measured.

Two capabilities require an explicit architecture and roadmap decision:
1. **Video Processing**: Ingesting aircraft inspection video clips, borescope inspection footage, and training videos.
2. **Voice (Audio Input & Output)**: Cockpit voice recordings, maintenance voice notes (ASR), and spoken system readouts (TTS).

## Decision

### 1. Video Ingestion & Processing Strategy
- **`cpu_lite` Tier**: Real-time dense video processing is **excluded**. Running 4B+ VLMs across 30 fps frames on CPU consumes excessive memory and causes latency > 45s per chunk, violating interactive latency requirements.
- **`gpu_high` and `apple_full` Tiers**: Supported via **keyframe extraction** rather than raw frame ingestion:
  - Video stream is processed offline using local ffmpeg / PyAV.
  - Scene-change detection extracts keyframes at a maximum rate of 1 frame per 2–5 seconds.
  - Extracted keyframes are treated as individual visual `EvidenceUnit` items linked to a parent video unit with precise temporal timestamps (`timestamp_start`, `timestamp_end`).
  - Frame batches are scored with the visual capability (`qwen3-vl:2b` or target tier VLM) with explicit CER/confidence tracking.

### 2. Voice (ASR & TTS) Strategy
- **Voice Ingestion (ASR)**:
  - Proven and verified in Task 3.8 (`backend/ingestion/extractors/audio.py`) using `faster-whisper` and deterministic acoustic fallback.
  - Zero egress: no external cloud speech APIs (Google Cloud Speech, Whisper API) are permitted.
  - All speech units produce structured `EvidenceUnit` items with `speaker_turn` timestamps and word-level confidence.
- **Voice Output (TTS)**:
  - Browser Web Speech synthesis is disabled by default under `ZERO_EGRESS_MODE=true` to prevent browser vendors from proxying voice synthesis through external endpoints.
  - High-fidelity offline TTS (e.g. `piper-tts` or `kokoro`) is slated for Phase 5 as an optional local backend capability once user demand is confirmed (PLAN §12.5).

## Consequences
- No heavyweight video dependencies added to the `cpu_lite` runtime.
- Video analysis conforms exactly to the `EvidenceUnit` and Critic contract: every visual claim references the exact frame image and timestamp.
- Auditing: All media extraction events emit `MEDIA_EXTRACTED` audit events with frame hashes and zero egress.

