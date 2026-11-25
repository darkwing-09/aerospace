from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from memory.scoping import can_access


import builtins

class AuthenticationError(Exception):
    """Raised when authentication credentials are missing, invalid, or expired."""
    pass


class PermissionError(builtins.PermissionError):
    """Raised when an authenticated user lacks authorization for an action or workspace."""
    pass


@dataclass
class UserClaims:
    user_id: str
    role: str  # "ADMIN", "OPERATOR", "ANALYST", "AUDITOR"
    allowed_workspaces: List[str]
    clearance: str = "INTERNAL"
    issued_at: int = field(default_factory=lambda: int(time.time()))
    expires_at: int = field(default_factory=lambda: int(time.time()) + 3600)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub": self.user_id,
            "role": self.role,
            "workspaces": list(self.allowed_workspaces),
            "clearance": self.clearance,
            "iat": self.issued_at,
            "exp": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UserClaims:
        return cls(
            user_id=data.get("sub", "anonymous"),
            role=data.get("role", "OPERATOR"),
            allowed_workspaces=data.get("workspaces", []),
            clearance=data.get("clearance", "INTERNAL"),
            issued_at=data.get("iat", int(time.time())),
            expires_at=data.get("exp", int(time.time()) + 3600),
        )


class IdentityProvider(ABC):
    """
    Abstract Identity Provider interface for AeroMind 2.0 (PLAN §7.7, Pitfall §11.15).
    Binds to enterprise IdPs (Keycloak, LDAP, Entra ID) or local cryptographic tokens.
    """
    @abstractmethod
    def validate_token(self, token: str) -> UserClaims:
        """Cryptographically validates token signature, expiration, and returns UserClaims."""
        pass

    @abstractmethod
    def issue_token(
        self,
        user_id: str,
        role: str,
        allowed_workspaces: List[str],
        clearance: str = "INTERNAL",
        expires_in_seconds: int = 3600,
    ) -> str:
        """Issues a signed token for testing and local authentication."""
        pass


class JWTIdentityProvider(IdentityProvider):
    """
    Cryptographically signed HMAC-SHA256 JWT Identity Provider.
    Runs locally with zero external network dependencies and strict signature verification.
    """
    def __init__(self, secret_key: str):
        if not secret_key:
            raise ValueError("Secret key must not be empty")
        self.secret_key = secret_key.encode("utf-8")

    def _b64encode(self, data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    def _b64decode(self, s: str) -> bytes:
        rem = len(s) % 4
        if rem > 0:
            s += "=" * (4 - rem)
        return base64.urlsafe_b64decode(s.encode("utf-8"))

    def issue_token(
        self,
        user_id: str,
        role: str,
        allowed_workspaces: List[str],
        clearance: str = "INTERNAL",
        expires_in_seconds: int = 3600,
    ) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        now = int(time.time())
        claims = UserClaims(
            user_id=user_id,
            role=role.upper(),
            allowed_workspaces=allowed_workspaces,
            clearance=clearance.upper(),
            issued_at=now,
            expires_at=now + expires_in_seconds,
        )

        h_bytes = self._b64encode(json.dumps(header).encode("utf-8"))
        p_bytes = self._b64encode(json.dumps(claims.to_dict()).encode("utf-8"))
        signing_input = f"{h_bytes}.{p_bytes}".encode("utf-8")
        sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        sig_bytes = self._b64encode(sig)

        return f"{h_bytes}.{p_bytes}.{sig_bytes}"

    def validate_token(self, token: str) -> UserClaims:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationError("Malformed token structure: must contain header, payload, and signature.")

        h_str, p_str, sig_str = parts[0], parts[1], parts[2]
        signing_input = f"{h_str}.{p_str}".encode("utf-8")
        expected_sig = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        actual_sig = self._b64decode(sig_str)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AuthenticationError("Invalid token signature: cryptographic verification failed.")

        try:
            payload = json.loads(self._b64decode(p_str).decode("utf-8"))
        except Exception as e:
            raise AuthenticationError(f"Failed to decode token payload: {e}") from e

        now = int(time.time())
        if payload.get("exp", 0) < now:
            raise AuthenticationError("Token has expired.")

        return UserClaims.from_dict(payload)


def authenticate_request(headers: Dict[str, str], idp: IdentityProvider) -> UserClaims:
    """
    Authenticates an incoming request from HTTP headers.
    Enforces Pitfall §11.15: Never trust client-supplied identity headers (X-User-Id, etc.)
    without a validated cryptographic Bearer token.
    """
    # Normalize header keys to lowercase
    norm_headers = {k.lower(): v for k, v in headers.items()}
    auth_header = norm_headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise AuthenticationError("Authorization required: missing or malformed Bearer token.")

    token = auth_header[7:].strip()
    return idp.validate_token(token)


def authorize_action(
    claims: UserClaims,
    target_workspace: Optional[str] = None,
    required_role: Optional[str] = None,
    required_clearance: Optional[str] = None,
) -> bool:
    """
    Enforces RBAC and workspace tenant authorization on authenticated UserClaims.
    """
    # 1. Role validation
    if required_role:
        if required_role.upper() == "ADMIN" and claims.role != "ADMIN":
            raise PermissionError(f"Insufficient role: requires '{required_role}', user has '{claims.role}'.")

    # 2. Workspace tenant isolation
    if target_workspace:
        if "*" not in claims.allowed_workspaces and target_workspace not in claims.allowed_workspaces:
            raise PermissionError(
                f"User '{claims.user_id}' is not authorized for workspace '{target_workspace}'. "
                f"Allowed workspaces: {claims.allowed_workspaces}"
            )

    # 3. Clearance validation
    if required_clearance:
        if not can_access(claims.clearance, required_clearance):
            raise PermissionError(
                f"Insufficient security clearance: requires '{required_clearance}', user has '{claims.clearance}'."
            )

    return True

