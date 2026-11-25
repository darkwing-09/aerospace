import pytest
from pathlib import Path
from ingestion.extractors.audio import extract_audio
from ingestion.evidence_unit import EvidenceUnit, EvidenceTag

def test_extract_audio_fixture():
    fixture_path = Path(__file__).resolve().parent.parent / "fixtures" / "audio_note.wav"
    assert fixture_path.exists(), f"Audio fixture missing: {fixture_path}"
    
    unit = extract_audio(
        file_path=str(fixture_path),
        workspace_id="ws-audio-test"
    )
    
    assert isinstance(unit, EvidenceUnit)
    assert unit.source_type == "audio"
    assert unit.workspace_id == "ws-audio-test"
    assert len(unit.content_blocks) >= 1
    
    block = unit.content_blocks[0]
    assert block.block_type == "speaker_turn"
    assert block.location is not None
    assert block.location.start_time_sec is not None
    assert block.location.end_time_sec is not None
    assert block.location.start_time_sec <= block.location.end_time_sec
    assert unit.provenance is not None
    assert unit.provenance.extractor_name == "audio_asr_extractor"

def test_extract_audio_corrupted_file(tmp_path):
    bad_audio = tmp_path / "corrupted.wav"
    bad_audio.write_text("NOT A REAL WAV FILE")
    
    unit = extract_audio(
        file_path=str(bad_audio),
        workspace_id="ws-audio-test"
    )
    
    assert isinstance(unit, EvidenceUnit)
    assert unit.evidence_tag == EvidenceTag.UNCERTAIN
    assert "error" in unit.extracted_text.lower() or "unsupported" in unit.extracted_text.lower() or "corrupted" in unit.extracted_text.lower()

