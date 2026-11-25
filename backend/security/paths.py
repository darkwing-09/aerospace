"""Allowlist-based path handling for anything derived from client input.

Why an allowlist: a blocklist of `..`, `/etc/` and similar is bypassable
(plan pitfall §11.16). Instead we (1) accept only plain file names and
identifiers with a conservative character set, and (2) resolve the final path
and require it to sit inside the intended root directory.
"""
from __future__ import annotations

import re
from pathlib import Path


class UnsafePathError(ValueError):
    """Raised when a client-supplied name or path would escape its root."""


# Identifiers used to build directory/file names (doc ids, session ids, aircraft ids).
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
# Characters/sequences never allowed in an uploaded file name.
_FORBIDDEN_IN_NAME = ("/", "\\", "\x00", "%2f", "%2F", "%5c", "%5C", "%00")


def safe_filename(name: str | None) -> str:
    """Return the name unchanged if it is a plain, safe file name; else raise."""
    if not name or not name.strip():
        raise UnsafePathError("File name is empty.")
    if len(name) > 255:
        raise UnsafePathError("File name is too long.")
    if any(tok in name for tok in _FORBIDDEN_IN_NAME):
        raise UnsafePathError(f"File name {name!r} contains a path separator or encoded separator.")
    if ".." in name or name.startswith(".") or name.startswith("~"):
        raise UnsafePathError(f"File name {name!r} is not allowed.")
    if any(ord(c) < 32 for c in name):
        raise UnsafePathError("File name contains control characters.")
    return name


def safe_identifier(value: str | None, field: str = "identifier") -> str:
    """Validate an id that will be embedded in file-system paths."""
    if value is None or not _ID_RE.match(value) or ".." in value:
        raise UnsafePathError(f"Invalid {field}: only letters, digits, '_', '-', '.' are allowed (max 128).")
    return value


def safe_join(root: Path | str, *parts: str) -> Path:
    """Join parts onto root and guarantee the resolved result stays inside root."""
    root_resolved = Path(root).resolve()
    candidate = root_resolved.joinpath(*parts).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError("Resolved path escapes the allowed directory.")
    return candidate
