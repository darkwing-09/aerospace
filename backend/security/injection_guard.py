import re
from typing import Tuple, List
from observability.audit import audit_logger, AuditEvent

# Comprehensive injection patterns for Task 4.1b
INJECTION_PATTERNS = [
    # 1. Instruction overrides
    (re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"disregard\s+(all\s+)?(earlier|previous)\s+instructions", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"you\s+are\s+now\s+(an\s+unrestricted|in\s+god\s+mode|dan)", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"(new\s+)?system\s*prompt\s*:", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"hidden\s+instruction\s*:", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),

    # 2. Model template token delimiters
    (re.compile(r"<\s*\|\s*im_start\s*\|\s*>", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"<\s*\|\s*im_end\s*\|\s*>", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"\[\s*INST\s*\]", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"\[\s*/\s*INST\s*\]", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"<<\s*SYS\s*>>", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"<<\s*/\s*SYS\s*>>", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),

    # 3. SSE In-Band Control-Tag Spoofing (PLAN §11.17, Task 4.1b)
    (re.compile(r"\[DONE\]", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"\[ERROR:\s*[^\]]*\]", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"data:\s*\[DONE\]", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),

    # 4. Markdown remote image exfiltration (PLAN §11.17, QW10)
    (re.compile(r"!\[[^\]]*\]\(\s*https?://[^\)]+\)", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]"),

    # 5. Dangerous CSV / DDE formula injection (=cmd|..., +shell|...)
    (re.compile(r"[=+\-@][a-zA-Z0-9_]+\|"), "[UNTRUSTED_INJECTION_FLAGGED]"),

    # 6. HTML/Script tag injection
    (re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL), "[UNTRUSTED_INJECTION_FLAGGED]"),
    (re.compile(r"<\s*iframe[^>]*>", re.IGNORECASE), "[UNTRUSTED_INJECTION_FLAGGED]")
]

def check_and_neutralize_injections(text: str, workspace_id: str = "default") -> Tuple[str, bool]:
    """
    Detects and neutralizes prompt injection signatures, model delimiters,
    SSE spoof tags, and markdown image exfiltration from untrusted inputs.
    Audits SANITIZED_BOUNDARY event on detection.
    """
    cleaned = text
    found_injections = []

    for pattern, replacement in INJECTION_PATTERNS:
        if pattern.search(cleaned):
            found_injections.append(pattern.pattern)
            cleaned = pattern.sub(replacement, cleaned)

    has_injection = len(found_injections) > 0

    if has_injection:
        audit_logger.emit(
            AuditEvent(
                workspace_id=workspace_id,
                user_id="system",
                conversation_id="injection_guard",
                task_id="sanitize",
                event_type="SANITIZED_BOUNDARY",
                agent_name="injection_guard",
                details={
                    "detected_patterns_count": len(found_injections),
                    "neutralized": True,
                    "input_snippet": text[:100]
                },
                succeeded=True
            )
        )

    return cleaned, has_injection
