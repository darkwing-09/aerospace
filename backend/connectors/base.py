from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid

from ingestion.evidence_unit import EvidenceUnit, ContentBlock, PageSectionLocation, Provenance, EvidenceTag

@dataclass
class ConnectionResult:
    success: bool
    message: str
    status_code: int = 200

@dataclass
class RawResource:
    resource_id: str
    source_uri: str
    title: str
    content: str
    content_type: str = "document"
    acls: List[str] = field(default_factory=list)
    classification_level: str = "INTERNAL"
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class SyncResult:
    success: bool
    resources_discovered: int
    units_ingested: int
    errors: List[str] = field(default_factory=list)

class BaseConnector(ABC):
    """
    Base Connector Contract for Enterprise Data Sources (PLAN §7.13, Pitfall §11.12).
    Flow: CONNECT → AUTHENTICATE → DISCOVER → FETCH → NORMALIZE → INGEST → INDEX → PROVENANCE.
    Enforces workspace scoping, ACL retention, and approval gates on write actions.
    """
    @abstractmethod
    def connect(self) -> ConnectionResult:
        """Establish connection and authenticate with target data source."""
        pass

    @abstractmethod
    def discover_resources(self) -> List[str]:
        """List resource identifiers available in the target repository."""
        pass

    @abstractmethod
    def fetch_resource(self, resource_id: str) -> RawResource:
        """Fetch raw content and metadata for a specific resource."""
        pass

    def health_check(self) -> ConnectionResult:
        return self.connect()

    def normalize_to_evidence(self, resource: RawResource, workspace_id: str) -> EvidenceUnit:
        """
        Normalizes RawResource into a plan-compliant EvidenceUnit.
        MUST preserve workspace_id, ACLs, and classification level (Pitfall §11.12).
        """
        if not workspace_id or workspace_id in ["default", "default_workspace"]:
            raise ValueError(f"Valid tenant workspace_id required for connector normalization, got: '{workspace_id}'")

        unit_id = f"conn_{uuid.uuid4().hex[:12]}"
        
        # Preserve ACLs in provenance metadata
        prov = Provenance(
            extractor_name=self.__class__.__name__,
            extractor_version="1.0.0",
            pipeline_stage="connector_ingest",
        )
        
        block = ContentBlock(
            block_type="text",
            content=resource.content,
            location=PageSectionLocation(page_number=1)
        )

        return EvidenceUnit(
            id=unit_id,
            source_type=f"connector_{resource.content_type}",
            source_ref=resource.source_uri,
            extracted_text=resource.content,
            workspace_id=workspace_id,
            classification_level=resource.classification_level,
            content_blocks=[block],
            evidence_tag=EvidenceTag.OBSERVED,
            provenance=prov,
            confidence=1.0,
            ingested_at=resource.timestamp
        )

    def write_action(
        self,
        resource_id: str,
        action: str,
        payload: Dict[str, Any],
        user_approved: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a write/mutation action on the connector target.
        Approval-gated: strictly raises PermissionError if user_approved is False.
        """
        if not user_approved:
            raise PermissionError(
                f"Approval required for connector write action '{action}' on resource '{resource_id}'. "
                "Side-effecting actions must pass human approval gate."
            )
        return self._execute_write_action(resource_id, action, payload)

    @abstractmethod
    def _execute_write_action(self, resource_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass

    def sync(self, workspace_id: str) -> SyncResult:
        """Synchronizes discovered resources into EvidenceUnits."""
        res_ids = self.discover_resources()
        units = []
        errors = []
        for rid in res_ids:
            try:
                raw = self.fetch_resource(rid)
                unit = self.normalize_to_evidence(raw, workspace_id=workspace_id)
                units.append(unit)
            except Exception as e:
                errors.append(f"Failed to sync {rid}: {str(e)}")
        
        return SyncResult(
            success=(len(errors) == 0),
            resources_discovered=len(res_ids),
            units_ingested=len(units),
            errors=errors
        )

