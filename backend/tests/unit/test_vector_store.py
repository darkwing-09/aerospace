"""
Unit tests for Vector Store (Task 1.1 / PLAN §8.4, §11.3, ADR-0004).
"""

from unittest.mock import patch
import pytest
from knowledge.vector_store import (
    VectorStore,
    generate_point_id,
)


def test_deterministic_point_id():
    id1 = generate_point_id("unit_sop_01", 0)
    id2 = generate_point_id("unit_sop_01", 0)
    id3 = generate_point_id("unit_sop_01", 1)

    assert id1 == id2
    assert id1 != id3


def test_upsert_and_workspace_isolated_search():
    store = VectorStore(force_memory=True, vector_size=4)

    chunk_a = {
        "unit_id": "unit_alpha",
        "chunk_idx": 0,
        "workspace_id": "ws_defense_alpha",
        "classification_level": "SECRET",
        "source_type": "pdf",
        "source_ref": "sop.pdf#page=1",
        "extracted_text": "Hydraulic system normal pressure 210 kg/cm2",
        "evidence_tag": "observed",
        "confidence": 0.99,
    }
    vec_a = [1.0, 0.0, 0.0, 0.0]

    chunk_b = {
        "unit_id": "unit_bravo",
        "chunk_idx": 0,
        "workspace_id": "ws_commercial_bravo",
        "classification_level": "INTERNAL",
        "source_type": "pdf",
        "source_ref": "commercial.pdf#page=1",
        "extracted_text": "Commercial airliner hydraulic fluid specifications",
        "evidence_tag": "observed",
        "confidence": 0.95,
    }
    vec_b = [0.0, 1.0, 0.0, 0.0]

    count = store.upsert_chunks([chunk_a, chunk_b], [vec_a, vec_b])
    assert count == 2

    # Query matching vector A inside workspace alpha
    results_alpha = store.search(query_vector=[0.9, 0.1, 0.0, 0.0], workspace_id="ws_defense_alpha", top_k=5)
    assert len(results_alpha) == 1
    assert results_alpha[0]["payload"]["workspace_id"] == "ws_defense_alpha"
    assert results_alpha[0]["payload"]["unit_id"] == "unit_alpha"

    # Query matching vector A inside workspace bravo (cross-tenant attempt)
    results_bravo = store.search(query_vector=[0.9, 0.1, 0.0, 0.0], workspace_id="ws_commercial_bravo", top_k=5)
    # Should ONLY return bravo's chunks, never alpha's
    for r in results_bravo:
        assert r["payload"]["workspace_id"] == "ws_commercial_bravo"
        assert r["payload"]["unit_id"] != "unit_alpha"


def test_missing_workspace_id_raises_value_error():
    store = VectorStore(force_memory=True, vector_size=4)

    bad_chunk = {
        "unit_id": "unit_no_ws",
        "chunk_idx": 0,
        # workspace_id omitted
        "extracted_text": "Unattributed chunk",
    }
    with pytest.raises(ValueError) as excinfo:
        store.upsert_chunks([bad_chunk], [[0.1, 0.2, 0.3, 0.4]])
    assert "workspace_id is REQUIRED" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        store.search(query_vector=[0.1, 0.2, 0.3, 0.4], workspace_id="")
    assert "workspace_id is required" in str(excinfo.value)


def test_lock_error_fails_loudly_without_silent_memory_fallback(tmp_path):
    # Simulate a disk lock error on QdrantClient
    with patch("knowledge.vector_store.HAS_QDRANT", True):
        with patch("knowledge.vector_store.QdrantClient", side_effect=Exception("Database lock held by another process")):
            with pytest.raises(RuntimeError) as excinfo:
                VectorStore(storage_path=tmp_path, force_memory=False)
            assert "Refusing silent fallback" in str(excinfo.value)

