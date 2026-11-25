"""
backend/tests/adversarial/test_hardening_audit.py
─────────────────────────────────────────────────────────────────
Audit Hardening & Secret Scrubbing Tests (PLAN §7.8, §8.13, §8.17).
Verifies that:
1. Secret scrubbing recursively sanitizes sensitive API keys, tokens,
   passwords, and credentials in nested dicts, lists, and strings.
2. AuditEvent serialization guarantees no cleartext credentials hit the audit log.
3. Common secret patterns (OpenAI, AWS, JWT Bearer, URL params) are redacted.
"""

import json
from observability.audit import scrub_secrets, AuditEvent, audit_logger


def test_secret_scrubbing_string_patterns():
    """Verifies regex patterns for API keys, bearer tokens, AWS keys, and password assignments."""
    test_cases = [
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz.123", "Bearer [REDACTED_TOKEN]"),
        ("Using key sk-12345678abcdefghij for inference", "Using key [REDACTED_API_KEY] for inference"),
        ("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE", "AWS_ACCESS_KEY_ID=[REDACTED_AWS_KEY]"),
        ("https://internal.wiki/sync?token=super_secret_token_value&user=1", "https://internal.wiki/sync?token=[REDACTED]&user=1"),
        ("Database connection string password=mypassword123 host=localhost", "Database connection string token=[REDACTED] host=localhost"),
    ]

    for raw, expected in test_cases:
        scrubbed = scrub_secrets(raw)
        assert "[REDACTED" in scrubbed
        assert "super_secret_token_value" not in scrubbed
        assert "mypassword123" not in scrubbed
        assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed


def test_secret_scrubbing_nested_structures():
    """Verifies recursive sanitization of dictionaries, lists, and tuples."""
    dirty_data = {
        "user_id": "auditor_1",
        "api_key": "sk-unredacted_private_key_9999",
        "nested": {
            "token": "secret_jwt_xyz",
            "password": "ClearTextPassword!",
            "public_info": "MiG-21 Fuel SOP",
            "items": [
                "Bearer secret_token_in_list",
                {"authorization": "Bearer deep_secret"}
            ]
        }
    }

    cleaned = scrub_secrets(dirty_data)

    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["password"] == "[REDACTED]"
    assert cleaned["nested"]["public_info"] == "MiG-21 Fuel SOP"
    assert "[REDACTED_TOKEN]" in cleaned["nested"]["items"][0]
    assert cleaned["nested"]["items"][1]["authorization"] == "[REDACTED]"


def test_audit_event_serialization_redacts_details():
    """Verifies AuditEvent.to_dict() and to_json() scrub all nested secrets automatically."""
    event = AuditEvent(
        workspace_id="ws_scrub",
        user_id="user_admin",
        conversation_id="conv_1",
        task_id="task_1",
        event_type="MODEL_CALL",
        agent_name="router",
        details={
            "prompt": "Here is the key sk-9988776655443322 for verification",
            "auth_header": "Bearer token_secret_123",
            "api_key": "sk-secret12345678",
            "metric": 42
        }
    )

    serialized = event.to_json()
    parsed = json.loads(serialized)

    assert "sk-9988776655443322" not in serialized
    assert "token_secret_123" not in serialized
    assert "sk-secret12345678" not in serialized
    assert parsed["details"]["api_key"] == "[REDACTED]"
    assert parsed["details"]["metric"] == 42

