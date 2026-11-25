"""
backend/tests/integration/test_router_failover.py
─────────────────────────────────────────────────────────────────
Integration tests for model health checks, circuit breaker, and ranked
failover (Task 2.6 / PLAN §11.5, §11.6).
"""

from __future__ import annotations

import pytest

from router.router import ModelRouter, ModelFailureError
from router.health import health_checker, CircuitBreakerState
from observability.audit import AuditEvent, audit_logger


@pytest.fixture(autouse=True)
def reset_circuit_breaker():
    """Ensure circuit breaker state is clean before each test."""
    health_checker.reset()
    yield
    health_checker.reset()


def test_primary_model_served_when_healthy(monkeypatch):
    """When primary model is healthy, router.get() returns rank 1 model."""
    monkeypatch.setattr(health_checker, "_probe_endpoint", lambda endpoint: True)
    router = ModelRouter(hardware_tier="cpu_lite")
    entry = router.get("planning")
    assert entry["name"] == "qwen3-4b-instruct-2507-q4"
    assert entry.get("rank") == 1


def test_ranked_failover_when_primary_unresponsive(monkeypatch):
    """
    When primary model fails health check, router.get() serves next-ranked
    candidate on the same capability tag and emits MODEL_FAILOVER.
    """
    events = []
    monkeypatch.setattr(audit_logger, "emit", lambda ev: events.append(ev))

    def mock_probe(endpoint: str) -> bool:
        # Fail the primary Ollama endpoint
        if "11434" in endpoint:
            return False
        return True

    # Primary model endpoint fails, but secondary model (transformers local) succeeds
    monkeypatch.setattr(health_checker, "_probe_endpoint", lambda ep: False)
    # Allow mistral (local transformers provider)
    monkeypatch.setattr(
        health_checker,
        "is_available",
        lambda ep, tag: False if "qwen" in tag else True,
    )

    router = ModelRouter(hardware_tier="cpu_lite")
    entry = router.get("planning")

    # Should serve mistral-7b-finetuned (rank 2 on planning)
    assert entry["name"] == "mistral-7b-finetuned"
    assert entry.get("rank") == 2

    # Verify MODEL_FAILOVER audit event was emitted
    failover_events = [e for e in events if e.event_type == "MODEL_FAILOVER"]
    assert len(failover_events) == 1
    assert failover_events[0].details["capability"] == "planning"
    assert failover_events[0].details["primary_model"] == "qwen3-4b-instruct-2507-q4"
    assert failover_events[0].details["failover_model"] == "mistral-7b-finetuned"


def test_model_failure_when_all_candidates_down(monkeypatch):
    """
    When all candidates for a capability are down, router.get() fails loudly
    with ModelFailureError and emits MODEL_FAILURE, without silent fallback to an unrelated model.
    """
    events = []
    monkeypatch.setattr(audit_logger, "emit", lambda ev: events.append(ev))

    # All endpoints down
    monkeypatch.setattr(health_checker, "is_available", lambda ep, tag: False)

    router = ModelRouter(hardware_tier="cpu_lite")
    with pytest.raises(ModelFailureError) as exc:
        router.get("planning")

    assert "MODEL_FAILURE" in str(exc.value)

    # Verify MODEL_FAILURE audit event was emitted
    failure_events = [e for e in events if e.event_type == "MODEL_FAILURE"]
    assert len(failure_events) == 1
    assert failure_events[0].event_type == "MODEL_FAILURE"
    assert failure_events[0].succeeded is False


def test_circuit_breaker_trips_after_threshold():
    """Verify circuit breaker trips to OPEN after 3 consecutive failures."""
    endpoint = "http://127.0.0.1:19999"
    model_tag = "test_model"

    assert health_checker.is_available(endpoint, model_tag) is False
    assert health_checker._get_entry(endpoint, model_tag)["consecutive_failures"] == 1
    assert health_checker._get_entry(endpoint, model_tag)["state"] == CircuitBreakerState.CLOSED

    assert health_checker.is_available(endpoint, model_tag) is False
    assert health_checker._get_entry(endpoint, model_tag)["consecutive_failures"] == 2

    # 3rd failure trips the breaker to OPEN
    assert health_checker.is_available(endpoint, model_tag) is False
    assert health_checker._get_entry(endpoint, model_tag)["state"] == CircuitBreakerState.OPEN

    # While OPEN, is_available immediately returns False without probing
    assert health_checker.is_available(endpoint, model_tag) is False

