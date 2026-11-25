"""
Unit tests for Audit and Observability (Task 0.4 / PLAN §7.8, ADR-0006).
"""

import json
from pathlib import Path
from observability.audit import (
    AuditEvent,
    AuditLogger,
    FailureCategory,
    scrub_secrets,
)


def test_scrub_secrets_redaction():
    payload = {
        "api_key": "sk-1234567890abcdef1234567890",
        "nested": {
            "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz",
            "aws_cred": "AKIAIOSFODNN7EXAMPLE",
            "conn_string": "https://api.local/v1?token=supersecret123&user=admin",
            "safe_text": "Normal avionics diagnostic message",
            "password": "ClearTextPassword!",
        },
        "list_items": [
            "sk-anothersecretkey987654321",
            "Safe value",
        ],
    }

    scrubbed = scrub_secrets(payload)

    # API key redacted
    assert "sk-" not in str(scrubbed)
    assert "[REDACTED" in scrubbed["api_key"]

    # Bearer token redacted
    assert "eyJhbGci" not in scrubbed["nested"]["auth_header"]
    assert "[REDACTED_TOKEN]" in scrubbed["nested"]["auth_header"]

    # AWS key redacted
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed["nested"]["aws_cred"]
    assert "[REDACTED_AWS_KEY]" in scrubbed["nested"]["aws_cred"]

    # Token parameter redacted
    assert "supersecret123" not in scrubbed["nested"]["conn_string"]

    # Sensitive key password redacted
    assert scrubbed["nested"]["password"] == "[REDACTED]"

    # Safe text preserved
    assert scrubbed["nested"]["safe_text"] == "Normal avionics diagnostic message"

    # List items scrubbed
    assert scrubbed["list_items"][0] == "[REDACTED_API_KEY]"
    assert scrubbed["list_items"][1] == "Safe value"


def test_audit_event_auto_scrub_and_sink(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    event = AuditEvent(
        workspace_id="ws_defense",
        user_id="user_pilot",
        conversation_id="conv_100",
        task_id="task_200",
        event_type="MODEL_CALL",
        agent_name="planning_agent",
        model_capability="planning",
        model_name="qwen3:4b",
        details={
            "prompt_tokens": 120,
            "auth_header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "openai_key": "sk-secret12345678",
            "api_key": "some_secret_key_value",
            "raw_text": "Analyzing flap position",
        },
        succeeded=True,
    )

    logger.emit(event)

    audit_file = tmp_path / "audit.jsonl"
    assert audit_file.exists()

    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    logged_data = json.loads(lines[0])
    assert logged_data["event_type"] == "MODEL_CALL"
    assert logged_data["workspace_id"] == "ws_defense"
    assert "sk-" not in lines[0]
    assert "[REDACTED_TOKEN]" in logged_data["details"]["auth_header"]
    assert logged_data["details"]["api_key"] == "[REDACTED]"


def test_failure_categories():
    assert FailureCategory.SECURITY_VIOLATION.value == "SECURITY_VIOLATION"
    assert FailureCategory.MODEL_FAILURE.value == "MODEL_FAILURE"
    assert FailureCategory.HUMAN_REVIEW_REQUIRED.value == "HUMAN_REVIEW_REQUIRED"
