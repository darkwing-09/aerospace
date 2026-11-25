"""
backend/router/health.py
─────────────────────────────────────────────────────────────────
Health Checks and Circuit Breaker for Model Endpoints (Task 2.6 / PLAN §11.5, §11.6).
Implements HEAD then GET probes with 2s timeout and N=3 / 60s circuit breaker
loaded from config/thresholds.yaml.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import urllib.request
import urllib.error
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "thresholds.yaml"

DEFAULT_FAILURE_THRESHOLD = 3
DEFAULT_COOLDOWN_SECONDS = 60.0
DEFAULT_TIMEOUT_SECONDS = 2.0


def _load_thresholds() -> Tuple[int, float, float]:
    """Loads failure threshold, cooldown, and timeout from thresholds.yaml."""
    if not CONFIG_PATH.exists():
        return DEFAULT_FAILURE_THRESHOLD, DEFAULT_COOLDOWN_SECONDS, DEFAULT_TIMEOUT_SECONDS

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cb = data.get("circuit_breaker", {})
        thresh = int(cb.get("failure_threshold", DEFAULT_FAILURE_THRESHOLD))
        cool = float(cb.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS))
        timeout = float(cb.get("health_check_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        return thresh, cool, timeout
    except Exception:
        return DEFAULT_FAILURE_THRESHOLD, DEFAULT_COOLDOWN_SECONDS, DEFAULT_TIMEOUT_SECONDS


class CircuitBreakerState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class EndpointCircuitBreaker:
    """
    Per-endpoint circuit breaker.
    Trips to OPEN after N consecutive failures. Cooldown for T seconds.
    """

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds

        # State mapping: (endpoint, model_tag) -> dict
        self._states: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def _get_entry(self, endpoint: str, model_tag: str) -> Dict[str, Any]:
        key = (endpoint, model_tag)
        if key not in self._states:
            self._states[key] = {
                "state": CircuitBreakerState.CLOSED,
                "consecutive_failures": 0,
                "last_failure_time": 0.0,
                "last_success_time": 0.0,
            }
        return self._states[key]

    def record_success(self, endpoint: str, model_tag: str) -> None:
        entry = self._get_entry(endpoint, model_tag)
        entry["state"] = CircuitBreakerState.CLOSED
        entry["consecutive_failures"] = 0
        entry["last_success_time"] = time.monotonic()

    def record_failure(self, endpoint: str, model_tag: str) -> None:
        entry = self._get_entry(endpoint, model_tag)
        entry["consecutive_failures"] += 1
        entry["last_failure_time"] = time.monotonic()
        if entry["consecutive_failures"] >= self.failure_threshold:
            entry["state"] = CircuitBreakerState.OPEN

    def is_available(self, endpoint: str, model_tag: str) -> bool:
        """
        Returns True if endpoint is healthy and available to serve requests.
        Probes endpoint via HEAD then GET if state is CLOSED or cooldown expired.
        """
        entry = self._get_entry(endpoint, model_tag)
        now = time.monotonic()

        if entry["state"] == CircuitBreakerState.OPEN:
            if now - entry["last_failure_time"] > self.cooldown_seconds:
                entry["state"] = CircuitBreakerState.HALF_OPEN
            else:
                return False

        # If provider is not HTTP (e.g. transformers/local files), verify local existence
        if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
            return True

        # Probe endpoint: HEAD then GET with 2s timeout
        try:
            is_alive = self._probe_endpoint(endpoint)
        except Exception:
            is_alive = False

        if is_alive:
            self.record_success(endpoint, model_tag)
            return True
        else:
            self.record_failure(endpoint, model_tag)
            return False

    def _probe_endpoint(self, endpoint: str) -> bool:
        url = f"{endpoint.rstrip('/')}/api/tags" if "11434" in endpoint else endpoint.rstrip("/")
        
        # 1. Try HEAD request first
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "AeroMind-HealthProbe"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                if resp.status in (200, 204):
                    return True
        except Exception:
            pass

        # 2. Fall back to GET request
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "AeroMind-HealthProbe"})
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return resp.status in (200, 204)
        except Exception:
            return False

    def reset(self) -> None:
        """Resets all circuit breaker states."""
        self._states.clear()


thresh, cool, timeout = _load_thresholds()
health_checker = EndpointCircuitBreaker(
    failure_threshold=thresh,
    cooldown_seconds=cool,
    timeout_seconds=timeout,
)
