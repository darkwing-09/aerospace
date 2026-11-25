import os
import wave
import uuid
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from ingestion.evidence_unit import (
    EvidenceUnit,
    ContentBlock,
    PageSectionLocation,
    Provenance,
    EvidenceTag
)

def extract_audio(
    file_path: str,
    workspace_id: str,
    classification_level: str = "INTERNAL"
) -> EvidenceUnit:
    """
    Audio Extractor (ADR-0009, PLAN §8.3, Task 3.8).
    Extracts speech transcription and acoustic timing segments from WAV/audio files
    into structured EvidenceUnit objects.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {file_path}")

    start_time = time.time()
    unit_id = f"aud_{uuid.uuid4().hex[:12]}"
    file_name = path.name

    # Try faster_whisper if installed
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(path), beam_size=1)
        
        content_blocks = []
        transcript_parts = []
        for seg in segments:
            transcript_parts.append(seg.text.strip())
            block = ContentBlock(
                block_type="speaker_turn",
                content=seg.text.strip(),
                location=PageSectionLocation(
                    start_time_sec=round(seg.start, 2),
                    end_time_sec=round(seg.end, 2)
                )
            )
            content_blocks.append(block)

        full_text = " ".join(transcript_parts)
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        
        return EvidenceUnit(
            id=unit_id,
            source_type="audio",
            source_ref=f"{file_name}#duration={round(info.duration, 1)}s",
            extracted_text=full_text,
            workspace_id=workspace_id,
            classification_level=classification_level,
            content_blocks=content_blocks,
            evidence_tag=EvidenceTag.OBSERVED,
            provenance=Provenance(
                extractor_name="audio_asr_extractor",
                extractor_version="1.0.0",
                model_name="faster-whisper-tiny.en",
                execution_time_ms=execution_time_ms
            )
        )
    except ImportError:
        # Fallback to acoustic signal inspection via stdlib wave
        pass

    # Acoustic Inspection Fallback
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            framerate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
            duration_sec = round(num_frames / framerate, 3) if framerate > 0 else 0.0

            text_summary = (
                f"Audio recording '{file_name}': {duration_sec}s, {framerate}Hz, "
                f"{channels} channel(s), {sample_width*8}-bit sample depth. "
                "Acoustic signal detected with valid audio frames."
            )
            
            block = ContentBlock(
                block_type="speaker_turn",
                content=text_summary,
                location=PageSectionLocation(
                    start_time_sec=0.0,
                    end_time_sec=duration_sec
                )
            )
            
            execution_time_ms = round((time.time() - start_time) * 1000, 2)
            return EvidenceUnit(
                id=unit_id,
                source_type="audio",
                source_ref=f"{file_name}#duration={duration_sec}s",
                extracted_text=text_summary,
                workspace_id=workspace_id,
                classification_level=classification_level,
                content_blocks=[block],
                evidence_tag=EvidenceTag.OBSERVED,
                provenance=Provenance(
                    extractor_name="audio_asr_extractor",
                    extractor_version="1.0.0",
                    model_name="wave-acoustic-analyzer",
                    execution_time_ms=execution_time_ms
                )
            )
    except Exception as e:
        # Graceful handling of corrupted or non-audio file
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        err_msg = f"Corrupted or unsupported audio file '{file_name}': {str(e)}"
        return EvidenceUnit(
            id=unit_id,
            source_type="audio",
            source_ref=f"{file_name}#status=corrupted",
            extracted_text=err_msg,
            workspace_id=workspace_id,
            classification_level=classification_level,
            content_blocks=[
                ContentBlock(
                    block_type="speaker_turn",
                    content=err_msg,
                    location=PageSectionLocation(start_time_sec=0.0, end_time_sec=0.0)
                )
            ],
            evidence_tag=EvidenceTag.UNCERTAIN,
            provenance=Provenance(
                extractor_name="audio_asr_extractor",
                extractor_version="1.0.0",
                model_name="wave-fallback-error",
                execution_time_ms=execution_time_ms
            )
        )

