"""
Adversarial vector isolation and tenant security tests (Task 1.5 / PLAN §7.6, §8.4, §11.3).
Verifies:
1. Workspace A units are NEVER returned in Workspace B searches under any query.
2. Missing or empty workspace_id fails closed immediately with ValueError.
3. User authorization and clearance boundaries are strictly enforced.
4. Ground-truth query returns the correct chunk in top-3.
"""

from pathlib import Path
import pytest

from ingestion.pipeline import IngestionPipeline
from knowledge.vector_store import VectorStore
from tools.kb_search import search_knowledge_base
from tools.registry import UserContext

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MAINTENANCE_PDF = FIXTURES_DIR / "maintenance_sop.pdf"


@pytest.fixture
def isolated_pipeline():
    vstore = VectorStore(force_memory=True)
    return IngestionPipeline(vector_store=vstore)


def test_cross_workspace_leakage_prevented(isolated_pipeline, tmp_path):
    """
    Adversarial test: Document A contains classified MiG-21 radar specs in ws_alpha.
    Document B contains general Cessna manuals in ws_beta.
    A query in ws_beta searching for MiG-21 radar specs must NEVER return ws_alpha chunks.
    """
    doc_a = tmp_path / "mig21_radar_classified.txt"
    with open(doc_a, "w", encoding="utf-8") as f:
        f.write("MiG-21 RP-21 Sapfir radar operating frequency 9.3 GHz, pulse power 100 kW, target detection range 20 km.")

    # We use custom chunks directly into vector store for precise text control
    vstore = isolated_pipeline.vector_store
    vec_a = isolated_pipeline.embed_text("MiG-21 RP-21 Sapfir radar 9.3 GHz 100 kW")

    vstore.upsert_chunks(
        chunks=[
            {
                "unit_id": "unit_alpha_classified",
                "chunk_idx": 0,
                "workspace_id": "ws_alpha",
                "classification_level": "SECRET",
                "source_type": "text",
                "source_ref": "mig21_radar_classified.txt#p1",
                "extracted_text": "MiG-21 RP-21 Sapfir radar operating frequency 9.3 GHz, pulse power 100 kW, target detection range 20 km.",
                "evidence_tag": "observed",
                "confidence": 1.0,
            }
        ],
        vectors=[vec_a],
    )

    vec_b = isolated_pipeline.embed_text("Cessna 172 electrical system 28V DC battery")
    vstore.upsert_chunks(
        chunks=[
            {
                "unit_id": "unit_beta_civil",
                "chunk_idx": 0,
                "workspace_id": "ws_beta",
                "classification_level": "UNCLASSIFIED",
                "source_type": "text",
                "source_ref": "cessna_172.txt#p1",
                "extracted_text": "Cessna 172 electrical system utilizes a 28-volt direct-current electrical system powered by a belt-driven alternator.",
                "evidence_tag": "observed",
                "confidence": 1.0,
            }
        ],
        vectors=[vec_b],
    )

    # Adversary searches in ws_beta using exact keywords from ws_alpha
    results = search_knowledge_base(
        query="MiG-21 RP-21 Sapfir radar operating frequency",
        workspace_id="ws_beta",
        top_k=5,
        vector_store=vstore,
    )

    # MUST NOT return ws_alpha unit!
    assert len(results) == 0 or all(r["workspace_id"] == "ws_beta" for r in results)
    for r in results:
        assert r["unit_id"] != "unit_alpha_classified"
        assert "MiG-21" not in r["extracted_text"]


def test_missing_workspace_id_fails_closed():
    """Omitting or passing blank workspace_id must fail closed with ValueError."""
    with pytest.raises(ValueError, match="workspace_id is REQUIRED"):
        search_knowledge_base(query="hydraulic pressure", workspace_id="")

    with pytest.raises(ValueError, match="workspace_id is REQUIRED"):
        search_knowledge_base(query="hydraulic pressure", workspace_id="   ")


def test_user_context_workspace_permission_enforced(isolated_pipeline):
    """User without access to the requested workspace is blocked with PermissionError."""
    user = UserContext(
        user_id="user_john",
        role="ANALYST",
        allowed_workspaces=["ws_commercial"],
        clearance_level="SECRET",
    )

    with pytest.raises(PermissionError, match="does not have access to workspace"):
        search_knowledge_base(
            query="hydraulic pressure",
            workspace_id="ws_military",
            user_ctx=user,
            vector_store=isolated_pipeline.vector_store,
        )


def test_clearance_filtering(isolated_pipeline):
    """User with INTERNAL clearance cannot view SECRET chunks in the same workspace."""
    vstore = isolated_pipeline.vector_store
    vec = isolated_pipeline.embed_text("classified telemetry data frequency 433 MHz")

    vstore.upsert_chunks(
        chunks=[
            {
                "unit_id": "unit_secret",
                "chunk_idx": 0,
                "workspace_id": "ws_dept",
                "classification_level": "SECRET",
                "source_type": "text",
                "source_ref": "telemetry.txt#p1",
                "extracted_text": "Classified telemetry transmission on 433 MHz with encrypted key K-99.",
                "evidence_tag": "observed",
            },
            {
                "unit_id": "unit_internal",
                "chunk_idx": 0,
                "workspace_id": "ws_dept",
                "classification_level": "INTERNAL",
                "source_type": "text",
                "source_ref": "public_note.txt#p1",
                "extracted_text": "General maintenance shift schedule for telemetry room.",
                "evidence_tag": "observed",
            },
        ],
        vectors=[vec, vec],
    )

    low_user = UserContext(
        user_id="low_user",
        role="VIEWER",
        allowed_workspaces=["ws_dept"],
        clearance_level="INTERNAL",
    )
    high_user = UserContext(
        user_id="high_user",
        role="ANALYST",
        allowed_workspaces=["ws_dept"],
        clearance_level="SECRET",
    )

    # Low clearance search
    low_hits = search_knowledge_base(
        query="telemetry",
        workspace_id="ws_dept",
        user_ctx=low_user,
        vector_store=vstore,
    )
    assert len(low_hits) == 1
    assert low_hits[0]["unit_id"] == "unit_internal"

    # High clearance search
    high_hits = search_knowledge_base(
        query="telemetry",
        workspace_id="ws_dept",
        user_ctx=high_user,
        vector_store=vstore,
    )
    assert len(high_hits) == 2
    assert any(h["unit_id"] == "unit_secret" for h in high_hits)


def test_known_query_returns_correct_chunk_in_top_3(isolated_pipeline):
    """Fixture SOP query returns the hydraulic pressure chunk in top-3."""
    doc, count = isolated_pipeline.ingest_file(
        file_path=MAINTENANCE_PDF,
        workspace_id="ws_mro",
        classification_level="INTERNAL",
    )
    assert count > 0

    hits = search_knowledge_base(
        query="What is the normal operating pressure of the hydraulic system 210 kg/cm2?",
        workspace_id="ws_mro",
        top_k=3,
        vector_store=isolated_pipeline.vector_store,
    )

    assert len(hits) > 0
    top_texts = [h["extracted_text"] for h in hits[:3]]
    assert any("210 kg/cm2" in t or "hydraulic" in t.lower() for t in top_texts)

