import pytest
import time
from security.auth import (
    IdentityProvider,
    JWTIdentityProvider,
    UserClaims,
    AuthenticationError,
    PermissionError,
    authenticate_request,
    authorize_action
)

SECRET_KEY = "test-secret-key-for-aeromind-unit-tests-only"

@pytest.fixture
def auth_provider():
    return JWTIdentityProvider(secret_key=SECRET_KEY)

def test_unvalidated_header_injection_fails(auth_provider):
    """
    Pitfall §11.15:
    Identity from a trusted header (e.g. X-User-Id: admin) with no valid token
    must be rejected. Never trust client-supplied identity headers.
    """
    headers = {
        "X-User-Id": "superadmin",
        "X-User-Role": "ADMIN",
        "X-Workspace-Id": "all_workspaces"
    }
    
    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_request(headers=headers, idp=auth_provider)
    assert "token missing" in str(exc_info.value).lower() or "authorization required" in str(exc_info.value).lower()

def test_tampered_token_fails(auth_provider):
    """
    Cryptographic signature verification:
    A tampered token must fail signature verification.
    """
    valid_token = auth_provider.issue_token(
        user_id="user1",
        role="OPERATOR",
        allowed_workspaces=["ws-1"],
        clearance="INTERNAL"
    )
    
    # Tamper with signature
    tampered_token = valid_token[:-4] + "abcd"
    headers = {"Authorization": f"Bearer {tampered_token}"}
    
    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_request(headers=headers, idp=auth_provider)
    assert "signature" in str(exc_info.value).lower() or "invalid token" in str(exc_info.value).lower()

def test_expired_token_fails(auth_provider):
    """
    Tokens past their expiration window must be rejected.
    """
    expired_token = auth_provider.issue_token(
        user_id="user2",
        role="OPERATOR",
        allowed_workspaces=["ws-1"],
        clearance="INTERNAL",
        expires_in_seconds=-10  # Already expired
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    
    with pytest.raises(AuthenticationError) as exc_info:
        authenticate_request(headers=headers, idp=auth_provider)
    assert "expired" in str(exc_info.value).lower()

def test_privilege_escalation_role_mismatch(auth_provider):
    """
    User with OPERATOR role attempting an action requiring ADMIN clearance is denied.
    """
    token = auth_provider.issue_token(
        user_id="operator-1",
        role="OPERATOR",
        allowed_workspaces=["ws-alpha"],
        clearance="INTERNAL"
    )
    claims = authenticate_request(headers={"Authorization": f"Bearer {token}"}, idp=auth_provider)
    
    # Non-admin trying to perform admin action
    with pytest.raises(PermissionError) as exc_info:
        authorize_action(claims=claims, target_workspace="ws-alpha", required_role="ADMIN")
    assert "insufficient role" in str(exc_info.value).lower()

def test_cross_tenant_workspace_privilege_escalation(auth_provider):
    """
    User token cleared for tenant-alpha cannot access tenant-beta.
    """
    token = auth_provider.issue_token(
        user_id="engineer-alpha",
        role="OPERATOR",
        allowed_workspaces=["tenant-alpha"],
        clearance="SECRET"
    )
    claims = authenticate_request(headers={"Authorization": f"Bearer {token}"}, idp=auth_provider)
    
    # Access to own workspace succeeds
    assert authorize_action(claims=claims, target_workspace="tenant-alpha") is True
    
    # Attempting to access another tenant workspace raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        authorize_action(claims=claims, target_workspace="tenant-beta")
    assert "not authorized for workspace" in str(exc_info.value).lower()


def test_agent_chaining_privilege_escalation_denied_and_audited(monkeypatch):
    """
    Task 4.1c / PLAN §8.13:
    Verifies that when an unprivileged agent/user in an agent chain attempts
    to escalate privileges and invoke a restricted tool (e.g. sandbox execution),
    the attempt is:
    1. Denied strictly at the tool boundary.
    2. Denied event logged to audit with failure_category=SECURITY_VIOLATION.
    3. Returns an honest explanation without partial execution.
    """
    from tools.registry import get_tools_for, UserContext, BoundTool
    from observability.audit import audit_logger

    audit_events = []
    monkeypatch.setattr(audit_logger, "emit", lambda ev: audit_events.append(ev))

    # Viewer user context
    viewer_ctx = UserContext(
        user_id="viewer_bob",
        role="VIEWER",
        allowed_workspaces=["ws_mro"]
    )

    # 1. Statically granted tools for 'coding' are intersected with dynamic user role
    tools = get_tools_for("coding", viewer_ctx, workspace_id="ws_mro")
    tool_names = [t.spec.name for t in tools]
    # sandbox_exec requires ANALYST, so it is filtered out of VIEWER tool grant
    assert "sandbox_exec" not in tool_names

    # 2. If adversary or rogue subagent tries to bind and invoke sandbox_exec anyway:
    from tools.registry import get_tool
    sandbox_spec = get_tool("sandbox_exec")
    assert sandbox_spec is not None

    unauthorized_tool = BoundTool(spec=sandbox_spec, user_ctx=viewer_ctx, workspace_id="ws_mro")

    # Attempting invocation from unprivileged context
    with pytest.raises(PermissionError) as exc_info:
        unauthorized_tool(code="import os; os.system('id')")

    err_msg = str(exc_info.value)
    # Honest explanation stating required role and user role
    assert "Access denied" in err_msg
    assert "requires role 'ANALYST'" in err_msg
    assert "user has 'VIEWER'" in err_msg

    # Denial audited
    denied_events = [e for e in audit_events if e.event_type == "TOOL_CALL_DENIED"]
    assert len(denied_events) >= 1
    denied = denied_events[0]
    assert denied.permission_check is False
    assert denied.failure_category == "SECURITY_VIOLATION"
    assert denied.details["tool_name"] == "sandbox_exec"
    assert denied.details["required_role"] == "ANALYST"
    assert denied.details["user_role"] == "VIEWER"


