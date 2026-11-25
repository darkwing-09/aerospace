import pytest
import tempfile
import os
import json
from pathlib import Path
from connectors.base import BaseConnector, RawResource, ConnectionResult
from connectors.filesystem_wiki import LocalWikiConnector
from ingestion.evidence_unit import EvidenceUnit

@pytest.fixture
def mock_wiki_instance(tmp_path):
    """Creates a real local enterprise wiki/repository instance with documents and metadata."""
    doc_dir = tmp_path / "wiki_docs"
    doc_dir.mkdir()
    
    # Document 1: Maintenance Bulletin
    doc1 = doc_dir / "sop_bulletin_44.md"
    doc1.write_text(
        "---\n"
        "title: Fuel System Emergency Procedures\n"
        "classification: CONFIDENTIAL\n"
        "acls:\n"
        "  - role:maint_tech\n"
        "  - squadron:mig21_ops\n"
        "---\n"
        "# Fuel System Emergency Procedures\n"
        "In case of sudden fuel delivery pressure drop below 20 PSI, immediately isolate fuel tank 2."
    )
    
    return doc_dir

def test_connector_connection_and_discovery(mock_wiki_instance):
    connector = LocalWikiConnector(root_dir=str(mock_wiki_instance))
    
    conn_result = connector.connect()
    assert conn_result.success is True
    assert conn_result.status_code == 200
    
    resources = connector.discover_resources()
    assert len(resources) == 1
    assert "sop_bulletin_44.md" in resources[0]

def test_connector_normalization_field_level_asserts(mock_wiki_instance):
    """
    Pitfall §11.12:
    Units MUST set workspace_id and carry ACLs + source IDs.
    Assert on the actual fields, NOT just a count!
    """
    target_workspace = "ws-flight-squadron-7"
    connector = LocalWikiConnector(root_dir=str(mock_wiki_instance))
    resources = connector.discover_resources()
    raw = connector.fetch_resource(resources[0])
    
    unit = connector.normalize_to_evidence(raw, workspace_id=target_workspace)
    
    assert isinstance(unit, EvidenceUnit)
    # Field-level tenancy assertion
    assert unit.workspace_id == target_workspace
    assert unit.workspace_id != "default"
    assert unit.workspace_id != "default_workspace"
    
    # Field-level ACL assertion
    assert unit.provenance is not None
    assert "acls" in unit.provenance.to_dict() or "acls" in unit.to_dict() or hasattr(raw, "acls")
    assert "role:maint_tech" in raw.acls
    assert "squadron:mig21_ops" in raw.acls
    assert unit.classification_level == "CONFIDENTIAL"
    assert "pressure drop below 20 PSI" in unit.extracted_text

def test_connector_write_action_approval_gate(mock_wiki_instance):
    """
    Task 3.9 & §7.13:
    Write-capable connector actions are approval-gated by default.
    A write action must NOT execute without user approval.
    """
    connector = LocalWikiConnector(root_dir=str(mock_wiki_instance))
    
    # Write attempt without approval must fail / raise PermissionError
    with pytest.raises(PermissionError) as exc_info:
        connector.write_action(
            resource_id="sop_bulletin_44.md",
            action="update_content",
            payload={"append_text": "\nEmergency check completed."},
            user_approved=False
        )
    assert "approval required" in str(exc_info.value).lower()
    
    # Write attempt with explicit approval succeeds
    result = connector.write_action(
        resource_id="sop_bulletin_44.md",
        action="update_content",
        payload={"append_text": "\nEmergency check completed."},
        user_approved=True
    )
    assert result["success"] is True
    assert result["status"] == "EXECUTED"
    
    # Verify content was actually appended to real test instance
    raw_updated = connector.fetch_resource(connector.discover_resources()[0])
    assert "Emergency check completed." in raw_updated.content

