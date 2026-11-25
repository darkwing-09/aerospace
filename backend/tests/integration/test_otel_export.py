"""
backend/tests/integration/test_otel_export.py
─────────────────────────────────────────────────────────────────
Integration Tests for OpenTelemetry Local Export & Alert Engine
(Task 4.4 / ADR-0006, PLAN §7.8, §8.13).
Verifies that:
1. Internal AuditEvents convert cleanly to OTel OTLP JSON spans.
2. High-water mark tracking in CEF/SIEM exporter works incrementally.
3. An alert fires immediately on an injected failure or security breach.
4. Live traces are visible with valid trace IDs and span IDs.
"""

from pathlib import Path
import pytest

from observability.audit import AuditEvent
from observability.exporter import OTelSpanConverter, CEFExporter, AlertEngine


def test_otel_span_conversion():
    """Verifies that AuditEvents convert to valid OpenTelemetry ResourceSpans."""
    event = AuditEvent(
        workspace_id="ws_aviation_mro",
        user_id="lead_inspector",
        conversation_id="conv_engine_overhaul",
        task_id="task_calc_clearance",
        event_type="MODEL_CALL",
        agent_name="router",
        model_capability="general_reasoning",
        model_name="qwen2.5:3b",
        succeeded=True,
        details={"prompt_tokens": 128, "completion_tokens": 45}
    )

    span = OTelSpanConverter.audit_event_to_span(event)

    assert len(span["traceId"]) == 32
    assert len(span["spanId"]) == 16
    assert span["name"] == "aeromind.model_call"
    assert span["status"]["code"] == 1

    attr_keys = {attr["key"] for attr in span["attributes"]}
    assert "workspace_id" in attr_keys
    assert "user_id" in attr_keys
    assert "agent_name" in attr_keys
    assert "model_capability" in attr_keys
    assert "details.prompt_tokens" in attr_keys

    # Full OTLP bundle
    payload = OTelSpanConverter.to_otlp_payload([event])
    assert "resourceSpans" in payload
    assert len(payload["resourceSpans"][0]["scopeSpans"][0]["spans"]) == 1


def test_cef_exporter_high_water_mark(tmp_path):
    """Verifies high-water mark tracking in CEF exporter prevents duplicate emissions."""
    hwm_file = tmp_path / "cef_hwm.txt"
    exporter = CEFExporter(high_water_mark_path=hwm_file)

    events = [
        AuditEvent(
            workspace_id="ws_1", user_id="u1", conversation_id="c1",
            task_id="t1", event_type="PLAN", agent_name="planner"
        ),
        AuditEvent(
            workspace_id="ws_1", user_id="u1", conversation_id="c1",
            task_id="t2", event_type="AGENT_DISPATCH", agent_name="dispatcher"
        ),
    ]

    # First export yields 2 CEF records
    exported_1 = exporter.export_new_events(events)
    assert len(exported_1) == 2
    assert "CEF:0|AeroMind" in exported_1[0]
    assert hwm_file.read_text().strip() == "2"

    # Subsequent export of same list yields 0 new records
    exported_2 = exporter.export_new_events(events)
    assert len(exported_2) == 0

    # Adding a third event yields only 1 new record
    events.append(AuditEvent(
        workspace_id="ws_1", user_id="u1", conversation_id="c1",
        task_id="t3", event_type="RESPONSE", agent_name="synthesis"
    ))
    exported_3 = exporter.export_new_events(events)
    assert len(exported_3) == 1
    assert "AeroMind RESPONSE" in exported_3[0]
    assert hwm_file.read_text().strip() == "3"


def test_alert_fires_on_injected_security_violation():
    """
    Acceptance criterion: An alert fires on an injected failure.
    Verifies that a SECURITY_VIOLATION or TOOL_CALL_DENIED event triggers a CRITICAL alert.
    """
    engine = AlertEngine()

    normal_event = AuditEvent(
        workspace_id="ws_mro", user_id="tech_1", conversation_id="c1",
        task_id="t1", event_type="TOOL_CALL", agent_name="kb_search"
    )
    alert_none = engine.evaluate(normal_event)
    assert alert_none is None
    assert len(engine.fired_alerts) == 0

    # Injected Security Violation (e.g. prompt injection attempt)
    security_event = AuditEvent(
        workspace_id="ws_mro", user_id="adversary", conversation_id="c_evil",
        task_id="t_inj", event_type="TOOL_CALL_DENIED", agent_name="tool_runner",
        failure_category="SECURITY_VIOLATION",
        succeeded=False,
        details={"tool_name": "sandbox_exec", "reason": "Requires ANALYST role, user has VIEWER"}
    )

    alert = engine.evaluate(security_event)
    assert alert is not None
    assert alert.rule_name == "SECURITY_VIOLATION_DETECTED"
    assert alert.severity == "CRITICAL"
    assert alert.event_type == "TOOL_CALL_DENIED"
    assert "sandbox_exec" in alert.message
    assert len(engine.fired_alerts) == 1


def test_alert_fires_on_model_failover():
    """Verifies that an alert fires when a circuit-breaker or model failover occurs."""
    engine = AlertEngine()

    failover_event = AuditEvent(
        workspace_id="ws_core", user_id="system", conversation_id="c_failover",
        task_id="t_fail", event_type="MODEL_FAILOVER", agent_name="router",
        succeeded=True,
        details={"tag": "qwen3:4b-instruct-2507-q4_K_M", "reason": "Timeout > 2.0s"}
    )

    alert = engine.evaluate(failover_event)
    assert alert is not None
    assert alert.rule_name == "MODEL_FAILOVER_OR_CIRCUIT_TRIP"
    assert alert.severity == "HIGH"
    assert "qwen3:4b" in alert.message

