"""
backend/ingestion/evidence_unit.py
─────────────────────────────────────────────────────────────────
Evidence Unit — The canonical ingestion contract (PLAN §7.5).
Preserves layout, structured tables, provenance, and tenant isolation.
Every class provides to_dict() and from_dict() for lossless serialization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceTag(str, Enum):
    OBSERVED = "observed"
    RETRIEVED = "retrieved"
    INFERRED = "inferred"
    UNCERTAIN = "uncertain"


def _format_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s)


@dataclass
class PageSectionLocation:
    page_number: Optional[int] = None
    bounding_box: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1)
    section_path: List[str] = field(default_factory=list)
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    start_time_sec: Optional[float] = None
    end_time_sec: Optional[float] = None
    line_number: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "section_path": list(self.section_path),
            "row_index": self.row_index,
            "col_index": self.col_index,
            "start_time_sec": self.start_time_sec,
            "end_time_sec": self.end_time_sec,
            "line_number": self.line_number,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional[PageSectionLocation]:
        if not data:
            return None
        bbox = tuple(data["bounding_box"]) if data.get("bounding_box") else None
        return cls(
            page_number=data.get("page_number"),
            bounding_box=bbox,
            section_path=data.get("section_path", []),
            row_index=data.get("row_index"),
            col_index=data.get("col_index"),
            start_time_sec=data.get("start_time_sec"),
            end_time_sec=data.get("end_time_sec"),
            line_number=data.get("line_number"),
        )


@dataclass
class ExtractionError:
    error_code: str
    message: str
    component: str
    recoverable: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "component": self.component,
            "recoverable": self.recoverable,
            "timestamp": _format_iso(self.timestamp),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractionError:
        return cls(
            error_code=data["error_code"],
            message=data["message"],
            component=data["component"],
            recoverable=data.get("recoverable", True),
            timestamp=_parse_iso(data.get("timestamp")) or datetime.now(timezone.utc),
        )


@dataclass
class Provenance:
    extractor_name: str
    extractor_version: str = "1.0.0"
    model_name: Optional[str] = None
    pipeline_stage: str = "ingestion"
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "model_name": self.model_name,
            "pipeline_stage": self.pipeline_stage,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": _format_iso(self.timestamp),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional[Provenance]:
        if not data:
            return None
        return cls(
            extractor_name=data["extractor_name"],
            extractor_version=data.get("extractor_version", "1.0.0"),
            model_name=data.get("model_name"),
            pipeline_stage=data.get("pipeline_stage", "ingestion"),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            timestamp=_parse_iso(data.get("timestamp")) or datetime.now(timezone.utc),
        )


@dataclass
class Entity:
    id: str
    name: str
    category: str
    confidence: float = 1.0
    normalized_value: Optional[str] = None
    location: Optional[PageSectionLocation] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "confidence": self.confidence,
            "normalized_value": self.normalized_value,
            "location": self.location.to_dict() if self.location else None,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Entity:
        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            confidence=data.get("confidence", 1.0),
            normalized_value=data.get("normalized_value"),
            location=PageSectionLocation.from_dict(data.get("location")),
            attributes=data.get("attributes", {}),
        )


@dataclass
class Relationship:
    id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    confidence: float = 1.0
    evidence_ref: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "subject_entity_id": self.subject_entity_id,
            "predicate": self.predicate,
            "object_entity_id": self.object_entity_id,
            "confidence": self.confidence,
            "evidence_ref": self.evidence_ref,
            "attributes": dict(self.attributes),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Relationship:
        return cls(
            id=data["id"],
            subject_entity_id=data["subject_entity_id"],
            predicate=data["predicate"],
            object_entity_id=data["object_entity_id"],
            confidence=data.get("confidence", 1.0),
            evidence_ref=data.get("evidence_ref"),
            attributes=data.get("attributes", {}),
        )


@dataclass
class ContentBlock:
    block_type: str
    content: str
    structured_data: Optional[Dict[str, Any]] = None
    location: Optional[PageSectionLocation] = None
    media_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_type": self.block_type,
            "content": self.content,
            "structured_data": self.structured_data,
            "location": self.location.to_dict() if self.location else None,
            "media_ref": self.media_ref,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ContentBlock:
        return cls(
            block_type=data["block_type"],
            content=data["content"],
            structured_data=data.get("structured_data"),
            location=PageSectionLocation.from_dict(data.get("location")),
            media_ref=data.get("media_ref"),
        )


@dataclass
class Source:
    id: str
    uri: str
    source_type: str
    file_name: str
    file_size_bytes: int = 0
    mime_type: Optional[str] = None
    checksum: Optional[str] = None
    classification_level: str = "INTERNAL"
    acls: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "uri": self.uri,
            "source_type": self.source_type,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "mime_type": self.mime_type,
            "checksum": self.checksum,
            "classification_level": self.classification_level,
            "acls": list(self.acls),
            "created_at": _format_iso(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Source:
        return cls(
            id=data["id"],
            uri=data["uri"],
            source_type=data["source_type"],
            file_name=data["file_name"],
            file_size_bytes=data.get("file_size_bytes", 0),
            mime_type=data.get("mime_type"),
            checksum=data.get("checksum"),
            classification_level=data.get("classification_level", "INTERNAL"),
            acls=data.get("acls", []),
            created_at=_parse_iso(data.get("created_at")) or datetime.now(timezone.utc),
        )


@dataclass
class EvidenceUnit:
    id: str
    source_type: str
    source_ref: str
    extracted_text: str
    workspace_id: str
    classification_level: str = "INTERNAL"
    content_blocks: List[ContentBlock] = field(default_factory=list)
    extracted_entities: List[Dict[str, Any]] = field(default_factory=list)
    extracted_relationships: List[Dict[str, Any]] = field(default_factory=list)
    evidence_tag: EvidenceTag = EvidenceTag.OBSERVED
    location: Optional[PageSectionLocation] = None
    provenance: Optional[Provenance] = None
    confidence: float = 1.0
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_ref": self.source_ref,
            "extracted_text": self.extracted_text,
            "workspace_id": self.workspace_id,
            "classification_level": self.classification_level,
            "content_blocks": [cb.to_dict() for cb in self.content_blocks],
            "extracted_entities": list(self.extracted_entities),
            "extracted_relationships": list(self.extracted_relationships),
            "evidence_tag": self.evidence_tag.value if isinstance(self.evidence_tag, EvidenceTag) else self.evidence_tag,
            "location": self.location.to_dict() if self.location else None,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "confidence": self.confidence,
            "ingested_at": _format_iso(self.ingested_at),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvidenceUnit:
        tag = data.get("evidence_tag", EvidenceTag.OBSERVED)
        if isinstance(tag, str):
            tag = EvidenceTag(tag)
        return cls(
            id=data["id"],
            source_type=data["source_type"],
            source_ref=data["source_ref"],
            extracted_text=data["extracted_text"],
            workspace_id=data["workspace_id"],
            classification_level=data.get("classification_level", "INTERNAL"),
            content_blocks=[ContentBlock.from_dict(b) for b in data.get("content_blocks", [])],
            extracted_entities=data.get("extracted_entities", []),
            extracted_relationships=data.get("extracted_relationships", []),
            evidence_tag=tag,
            location=PageSectionLocation.from_dict(data.get("location")),
            provenance=Provenance.from_dict(data.get("provenance")),
            confidence=data.get("confidence", 1.0),
            ingested_at=_parse_iso(data.get("ingested_at")) or datetime.now(timezone.utc),
        )


@dataclass
class Document:
    id: str
    source: Source
    title: str
    author: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    total_pages: int = 1
    evidence_units: List[EvidenceUnit] = field(default_factory=list)
    status: ProcessingStatus = ProcessingStatus.PENDING
    errors: List[ExtractionError] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.to_dict(),
            "title": self.title,
            "author": self.author,
            "metadata": dict(self.metadata),
            "total_pages": self.total_pages,
            "evidence_units": [eu.to_dict() for eu in self.evidence_units],
            "status": self.status.value if isinstance(self.status, ProcessingStatus) else self.status,
            "errors": [err.to_dict() for err in self.errors],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Document:
        status = data.get("status", ProcessingStatus.PENDING)
        if isinstance(status, str):
            status = ProcessingStatus(status)
        return cls(
            id=data["id"],
            source=Source.from_dict(data["source"]),
            title=data["title"],
            author=data.get("author"),
            metadata=data.get("metadata", {}),
            total_pages=data.get("total_pages", 1),
            evidence_units=[EvidenceUnit.from_dict(eu) for eu in data.get("evidence_units", [])],
            status=status,
            errors=[ExtractionError.from_dict(err) for err in data.get("errors", [])],
        )

