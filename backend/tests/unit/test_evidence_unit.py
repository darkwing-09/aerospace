"""
Unit tests for EvidenceUnit ingestion contract (Task 0.4 / PLAN §7.5).
"""

from datetime import datetime, timezone
from ingestion.evidence_unit import (
    ContentBlock,
    Document,
    Entity,
    EvidenceTag,
    EvidenceUnit,
    ExtractionError,
    PageSectionLocation,
    ProcessingStatus,
    Provenance,
    Relationship,
    Source,
)


def test_evidence_unit_roundtrip():
    loc = PageSectionLocation(
        page_number=42,
        bounding_box=(10.0, 20.0, 100.0, 150.0),
        section_path=["Systems", "Hydraulics"],
        row_index=3,
        col_index=2,
    )
    prov = Provenance(
        extractor_name="mig21_pdf_extractor",
        extractor_version="1.2.0",
        model_name=None,
        pipeline_stage="ingestion",
        execution_time_ms=45.2,
    )
    cb_table = ContentBlock(
        block_type="table",
        content="Table 4: Hydraulic Pressures",
        structured_data={
            "headers": ["Subsystem", "Nominal (kg/cm2)", "Min (kg/cm2)"],
            "rows": [["Main", "210", "180"], ["Booster", "210", "175"]],
        },
        location=loc,
    )
    unit = EvidenceUnit(
        id="unit_hyd_001",
        source_type="pdf",
        source_ref="manuals/mig21bis.pdf#page=42",
        extracted_text="Table 4: Hydraulic Pressures. Main system nominal 210 kg/cm2.",
        workspace_id="ws_defense_01",
        classification_level="SECRET",
        content_blocks=[cb_table],
        extracted_entities=[{"name": "Main System", "type": "EQUIPMENT", "confidence": 0.98}],
        extracted_relationships=[
            {"subject": "Main System", "predicate": "OPERATES_AT", "object": "210 kg/cm2"}
        ],
        evidence_tag=EvidenceTag.OBSERVED,
        location=loc,
        provenance=prov,
        confidence=0.99,
        ingested_at=datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc),
    )

    data = unit.to_dict()
    assert data["id"] == "unit_hyd_001"
    assert data["classification_level"] == "SECRET"
    assert data["content_blocks"][0]["structured_data"]["rows"][0][1] == "210"

    # Lossless reconstruction
    restored = EvidenceUnit.from_dict(data)
    assert restored.id == unit.id
    assert restored.workspace_id == "ws_defense_01"
    assert restored.evidence_tag == EvidenceTag.OBSERVED
    assert restored.location.page_number == 42
    assert restored.location.bounding_box == (10.0, 20.0, 100.0, 150.0)
    assert restored.content_blocks[0].block_type == "table"
    assert restored.content_blocks[0].structured_data["headers"] == ["Subsystem", "Nominal (kg/cm2)", "Min (kg/cm2)"]
    assert restored.provenance.extractor_name == "mig21_pdf_extractor"


def test_document_roundtrip_with_errors():
    source = Source(
        id="src_doc_01",
        uri="file:///data/mig21.pdf",
        source_type="pdf",
        file_name="mig21.pdf",
        file_size_bytes=1048576,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        classification_level="INTERNAL",
    )
    err = ExtractionError(
        error_code="UNSUPPORTED_FONT",
        message="Non-standard Cyrillic font encountered on page 14",
        component="pymupdf_extractor",
        recoverable=True,
    )
    doc = Document(
        id="doc_mig_01",
        source=source,
        title="MiG-21bis Operating Instructions",
        author="Mikoyan-Gurevich",
        total_pages=350,
        status=ProcessingStatus.PARTIAL,
        errors=[err],
    )

    doc_dict = doc.to_dict()
    assert doc_dict["status"] == "partial"
    assert doc_dict["errors"][0]["error_code"] == "UNSUPPORTED_FONT"

    restored_doc = Document.from_dict(doc_dict)
    assert restored_doc.id == "doc_mig_01"
    assert restored_doc.source.file_name == "mig21.pdf"
    assert restored_doc.status == ProcessingStatus.PARTIAL
    assert len(restored_doc.errors) == 1
    assert restored_doc.errors[0].error_code == "UNSUPPORTED_FONT"

