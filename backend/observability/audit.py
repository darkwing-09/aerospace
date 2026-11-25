"""
backend/observability/audit.py
─────────────────────────────────────────────────────────────────
Audit and Observability for AeroMind 2.0 (PLAN §7.8, §8.17, ADR-0006).
Append-only JSONL event sink with recursive secret scrubbing.
Every model call, tool execution, and security event is attributable.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

SECRET_PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9_\-]{8,}", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?:token|password|secret|api_key|apikey|private_key)=([^\s&]+)", re.IGNORECASE), "token=[REDACTED]"),
]

SENSITIVE_KEY_NAMES = {"password", "secret", "token", "api_key", "apikey", "private_key", "authorization"}


def scrub_secrets(data: Any) -> Any:
    """
    Recursively scrubs known secret formats and credential values from dictionaries,
    lists, tuples, and strings.
    """
    if isinstance(data, str):
        cleaned = data
        for pattern, replacement in SECRET_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned

    elif isinstance(data, dict):
        scrubbed = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEY_NAMES):
                scrubbed[k] = "[REDACTED]"
            else:
                scrubbed[k] = scrub_secrets(v)
        return scrubbed

    elif isinstance(data, list):
        return [scrub_secrets(item) for item in data]

    elif isinstance(data, tuple):
        return tuple(scrub_secrets(item) for item in data)

    return data


class FailureCategory(str, Enum):
    USER_ERROR = "USER_ERROR"
    INPUT_ERROR = "INPUT_ERROR"
    PARSING_ERROR = "PARSING_ERROR"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MODEL_FAILURE = "MODEL_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    SECURITY_VIOLATION = "SECURITY_VIOLATION"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class AuditEvent:
    workspace_id: str
    user_id: str
    conversation_id: str
    task_id: str
    event_type: str
    agent_name: str
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_version: str = "1.0.0"
    model_capability: str = ""
    model_name: str = ""
    model_version: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    permission_check: Optional[bool] = None
    details: Dict[str, Any] = field(default_factory=dict)
    failure_category: Optional[str] = None
    succeeded: bool = True

    def to_dict(self) -> Dict[str, Any]:
        raw = asdict(self)
        raw["details"] = scrub_secrets(raw["details"])
        return raw

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Append-only local JSONL sink for audit and sovereignty records."""

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        if log_dir is None:
            from config import settings
            log_dir = Path(settings.TRACES_DIR)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"

    def emit(self, event: AuditEvent) -> None:
        """Appends a scrubbed JSON-serialized event to the audit stream."""
        line = event.to_json() + "\n"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)


# Global default audit logger
audit_logger = AuditLogger()

