"""
backend/observability/exporter.py
─────────────────────────────────────────────────────────────────
Telemetry Exporter and Alert Engine for AeroMind 2.0 (Task 4.4 / ADR-0006, PLAN §7.8).
Converts internal AuditEvents into:
1. OpenTelemetry (OTel) OTLP-compliant spans for local collector export.
2. Common Event Format (CEF) strings for SIEM ingestion with high-water marks.
3. Real-time alert evaluations triggering on security, circuit breaker, and critic faults.
Zero egress: all endpoints and outputs target local collectors only.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from observability.audit import AuditEvent, scrub_secrets


@dataclass
class AlertRecord:
    alert_id: str
    rule_name: str
    severity: str  # "INFO", "WARNING", "HIGH", "CRITICAL"
    event_id: str
    event_type: str
    workspace_id: str
    user_id: str
    message: str
    timestamp: float = field(default_factory=time.time)


class OTelSpanConverter:
    """Converts AuditEvents into OpenTelemetry OTLP ResourceSpans JSON structure."""

    @staticmethod
    def _to_trace_id(conversation_id: str) -> str:
        """Generates a 32-character hex trace ID from conversation_id or task."""
        seed = conversation_id if conversation_id else "aeromind_default_trace"
        return hashlib.md5(seed.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_span_id(event_id: str) -> str:
        """Generates a 16-character hex span ID from event_id."""
        return hashlib.md5(event_id.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def audit_event_to_span(cls, event: AuditEvent) -> Dict[str, Any]:
        trace_id = cls._to_trace_id(event.conversation_id)
        span_id = cls._to_span_id(event.event_id)

        clean_details = scrub_secrets(event.details or {})
        attributes = [
            {"key": "workspace_id", "value": {"stringValue": str(event.workspace_id)}},
            {"key": "user_id", "value": {"stringValue": str(event.user_id)}},
            {"key": "agent_name", "value": {"stringValue": str(event.agent_name)}},
            {"key": "agent_version", "value": {"stringValue": str(event.agent_version)}},
            {"key": "model_capability", "value": {"stringValue": str(event.model_capability)}},
            {"key": "succeeded", "value": {"boolValue": bool(event.succeeded)}},
        ]

        if event.failure_category:
            attributes.append({"key": "failure_category", "value": {"stringValue": str(event.failure_category)}})

        for k, v in clean_details.items():
            if isinstance(v, (str, int, float, bool)):
                attributes.append({"key": f"details.{k}", "value": {"stringValue": str(v)}})

        return {
            "traceId": trace_id,
            "spanId": span_id,
            "name": f"aeromind.{event.event_type.lower()}",
            "kind": 1,  # SPAN_KIND_INTERNAL
            "attributes": attributes,
            "status": {
                "code": 1 if event.succeeded else 2,  # 1 = OK, 2 = ERROR
                "message": event.failure_category or ("OK" if event.succeeded else "FAILED"),
            },
        }

    @classmethod
    def to_otlp_payload(cls, events: List[AuditEvent]) -> Dict[str, Any]:
        spans = [cls.audit_event_to_span(ev) for ev in events]
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "aeromind-backend"}},
                            {"key": "service.version", "value": {"stringValue": "2.0.0"}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "aeromind.observability", "version": "2.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
        }


class CEFExporter:
    """Formats AuditEvents into ArcSight Common Event Format (CEF) with high-water marks."""

    def __init__(self, high_water_mark_path: Optional[Path] = None):
        self.hwm_path = high_water_mark_path
        self._last_exported_idx = 0
        if self.hwm_path and self.hwm_path.exists():
            try:
                self._last_exported_idx = int(self.hwm_path.read_text().strip())
            except ValueError:
                self._last_exported_idx = 0

    def format_cef(self, event: AuditEvent) -> str:
        severity = 7 if not event.succeeded else 3
        if event.failure_category == "SECURITY_VIOLATION":
            severity = 10

        name = f"AeroMind {event.event_type}"
        cef_header = f"CEF:0|AeroMind|AeroMind-Core|2.0.0|{event.event_type}|{name}|{severity}|"

        ext_fields = [
            f"src={event.user_id}",
            f"suser={event.user_id}",
            f"cs1={event.workspace_id}",
            f"cs1Label=WorkspaceId",
            f"cs2={event.agent_name}",
            f"cs2Label=AgentName",
            f"outcome={'SUCCESS' if event.succeeded else 'FAILURE'}",
        ]
        if event.failure_category:
            ext_fields.append(f"reason={event.failure_category}")

        return cef_header + " ".join(ext_fields)

    def export_new_events(self, events: List[AuditEvent]) -> List[str]:
        new_events = events[self._last_exported_idx:]
        formatted = [self.format_cef(ev) for ev in new_events]
        self._last_exported_idx = len(events)
        if self.hwm_path:
            self.hwm_path.parent.mkdir(parents=True, exist_ok=True)
            self.hwm_path.write_text(str(self._last_exported_idx))
        return formatted


class AlertEngine:
    """Evaluates audit stream events against security, resilience, and quality alert rules."""

    def __init__(self):
        self.fired_alerts: List[AlertRecord] = []

    def evaluate(self, event: AuditEvent) -> Optional[AlertRecord]:
        alert: Optional[AlertRecord] = None

        # Rule 1: Security violations (Prompt injection / Privilege Escalation)
        if event.failure_category == "SECURITY_VIOLATION" or event.event_type in ("TOOL_CALL_DENIED", "SANITIZED_BOUNDARY"):
            severity = "CRITICAL" if event.event_type == "TOOL_CALL_DENIED" else "HIGH"
            alert = AlertRecord(
                alert_id=f"alert_{len(self.fired_alerts)+1}",
                rule_name="SECURITY_VIOLATION_DETECTED",
                severity=severity,
                event_id=event.event_id,
                event_type=event.event_type,
                workspace_id=event.workspace_id,
                user_id=event.user_id,
                message=f"Security alert triggered by {event.agent_name}: {event.details.get('tool_name') or event.details.get('input_snippet', '')}",
            )

        # Rule 2: Circuit breaker / Model Failover
        elif event.event_type in ("MODEL_FAILOVER", "CIRCUIT_BREAKER_TRIP"):
            alert = AlertRecord(
                alert_id=f"alert_{len(self.fired_alerts)+1}",
                rule_name="MODEL_FAILOVER_OR_CIRCUIT_TRIP",
                severity="HIGH",
                event_id=event.event_id,
                event_type=event.event_type,
                workspace_id=event.workspace_id,
                user_id=event.user_id,
                message=f"Model failover event triggered on tag {event.details.get('tag', '')}",
            )

        # Rule 3: Critic rejection on deliverable
        elif event.event_type == "EVALUATION" and not event.succeeded:
            alert = AlertRecord(
                alert_id=f"alert_{len(self.fired_alerts)+1}",
                rule_name="CRITIC_DELIVERABLE_REJECTED",
                severity="WARNING",
                event_id=event.event_id,
                event_type=event.event_type,
                workspace_id=event.workspace_id,
                user_id=event.user_id,
                message="Critic rejected deliverable due to ungrounded or failed claims",
            )

        if alert:
            self.fired_alerts.append(alert)
        return alert

    def clear(self):
        self.fired_alerts.clear()

