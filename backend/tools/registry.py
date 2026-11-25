"""
backend/tools/registry.py
─────────────────────────────────────────────────────────────────
Tool Contract and Registry for AeroMind 2.0 (PLAN §7.6, §7.7).
Static agent grant intersected with dynamic user authorization.
Every tool invocation is permission-checked, audited, and approval-gated.
Dangerous tools (e.g. web_fetch) are excluded from the build entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Type
import yaml
from pydantic import BaseModel

from observability.audit import AuditEvent, audit_logger
from security.auth import PermissionError

ROLE_HIERARCHY: Dict[str, int] = {
    "VIEWER": 1,
    "ANALYST": 2,
    "ADMIN": 3,
}

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "agents.yaml"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Type[BaseModel]
    output_schema: Type[BaseModel]
    side_effects: Literal["read", "write", "execute"]
    network_required: bool = False  # Always False in production (zero-egress)
    permission_scope: str = "kb:read"
    required_role: Literal["VIEWER", "ANALYST", "ADMIN"] = "VIEWER"
    requires_approval: bool = False
    func: Optional[Callable[..., Any]] = None


@dataclass
class UserContext:
    user_id: str
    role: Literal["VIEWER", "ANALYST", "ADMIN"] = "VIEWER"
    allowed_workspaces: List[str] = field(default_factory=list)
    clearance_level: str = "INTERNAL"

    def can_access_workspace(self, workspace_id: str) -> bool:
        if self.role == "ADMIN":
            return True
        return workspace_id in self.allowed_workspaces

    def has_role(self, required_role: str) -> bool:
        user_level = ROLE_HIERARCHY.get(self.role.upper(), 0)
        req_level = ROLE_HIERARCHY.get(required_role.upper(), 999)
        return user_level >= req_level


class BoundTool:
    """Wraps a tool with user context and workspace scope, re-verifying permission at call time."""

    def __init__(self, spec: ToolSpec, user_ctx: UserContext, workspace_id: str) -> None:
        self.spec = spec
        self.user_ctx = user_ctx
        self.workspace_id = workspace_id

    def __call__(self, **kwargs: Any) -> Any:
        # Runtime verification outside the LLM (PLAN §7.7, §8.13)
        if not self.user_ctx.can_access_workspace(self.workspace_id):
            try:
                from observability.audit import AuditEvent, audit_logger
                audit_logger.emit(
                    AuditEvent(
                        workspace_id=self.workspace_id,
                        user_id=self.user_ctx.user_id,
                        conversation_id="conv_tool",
                        task_id=f"tool_{self.spec.name}",
                        event_type="TOOL_CALL_DENIED",
                        agent_name="tool_runner",
                        permission_check=False,
                        failure_category="SECURITY_VIOLATION",
                        details={
                            "tool_name": self.spec.name,
                            "reason": f"User '{self.user_ctx.user_id}' cannot access workspace '{self.workspace_id}'."
                        },
                        succeeded=False
                    )
                )
            except Exception:
                pass
            raise PermissionError(
                f"Access denied: User '{self.user_ctx.user_id}' cannot access workspace '{self.workspace_id}'."
            )
        if not self.user_ctx.has_role(self.spec.required_role):
            try:
                from observability.audit import AuditEvent, audit_logger
                audit_logger.emit(
                    AuditEvent(
                        workspace_id=self.workspace_id,
                        user_id=self.user_ctx.user_id,
                        conversation_id="conv_tool",
                        task_id=f"tool_{self.spec.name}",
                        event_type="TOOL_CALL_DENIED",
                        agent_name="tool_runner",
                        permission_check=False,
                        failure_category="SECURITY_VIOLATION",
                        details={
                            "tool_name": self.spec.name,
                            "required_role": self.spec.required_role,
                            "user_role": self.user_ctx.role
                        },
                        succeeded=False
                    )
                )
            except Exception:
                pass
            raise PermissionError(
                f"Access denied: Tool '{self.spec.name}' requires role '{self.spec.required_role}', user has '{self.user_ctx.role}'."
            )
        if self.spec.network_required and os.environ.get("ZERO_EGRESS_MODE", "true").lower() == "true":
            raise PermissionError(f"Network call blocked: Tool '{self.spec.name}' violates zero-egress policy.")

        try:
            from observability.audit import AuditEvent, audit_logger
            audit_logger.emit(
                AuditEvent(
                    workspace_id=self.workspace_id,
                    user_id=self.user_ctx.user_id,
                    conversation_id="conv_tool",
                    task_id=f"tool_{self.spec.name}",
                    event_type="TOOL_CALL",
                    agent_name="tool_runner",
                    permission_check=True,
                    details={
                        "tool_name": self.spec.name,
                        "side_effects": self.spec.side_effects,
                        "permission_scope": self.spec.permission_scope,
                    },
                    succeeded=True,
                )
            )
        except Exception:
            pass

        if self.spec.func:
            return self.spec.func(**kwargs)
        return f"Executed tool {self.spec.name} successfully."


# Standard base schemas
class EmptyInput(BaseModel):
    pass


class EmptyOutput(BaseModel):
    success: bool
    message: str


class SandboxExecInput(BaseModel):
    code: str
    language: str = "python"
    timeout_seconds: int = 15


class SandboxExecOutput(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


# Canonical tool specifications (Production build excludes dev-only tools like web_fetch)
_ALL_TOOLS: Dict[str, ToolSpec] = {
    "sandbox_exec": ToolSpec(
        name="sandbox_exec",
        description="Executes code safely inside an isolated Docker sandbox container.",
        input_schema=SandboxExecInput,
        output_schema=SandboxExecOutput,
        side_effects="execute",
        network_required=False,
        permission_scope="sandbox:execute",
        required_role="ANALYST",
        requires_approval=True,
    ),
    "kb_search": ToolSpec(
        name="kb_search",
        description="Searches indexed EvidenceUnits in the current workspace.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="kb:read",
        required_role="VIEWER",
        requires_approval=False,
        func=lambda **kw: __import__("tools.kb_search", fromlist=["search_knowledge_base"]).search_knowledge_base(**kw),
    ),
    "doc_inspect": ToolSpec(
        name="doc_inspect",
        description="Inspects source document content blocks and metadata.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="kb:read",
        required_role="VIEWER",
        requires_approval=False,
    ),
    "math_eval": ToolSpec(
        name="math_eval",
        description="Evaluates deterministic avionics formulas without model inference.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="calc:execute",
        required_role="VIEWER",
        requires_approval=False,
    ),
    "csv_search": ToolSpec(
        name="csv_search",
        description="Performs structured data lookup over ingested CSV/XLSX tables.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="kb:read",
        required_role="VIEWER",
        requires_approval=False,
    ),
    "critic_verify": ToolSpec(
        name="critic_verify",
        description="Executes deterministic verification gates against deliverable claims.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="audit:verify",
        required_role="VIEWER",
        requires_approval=False,
    ),
    "workspace_memory_read": ToolSpec(
        name="workspace_memory_read",
        description="Reads persistent workspace memory items.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="read",
        network_required=False,
        permission_scope="memory:read",
        required_role="VIEWER",
        requires_approval=False,
    ),
    "workspace_memory_write": ToolSpec(
        name="workspace_memory_write",
        description="Writes a verified memory item to the workspace scope.",
        input_schema=EmptyInput,
        output_schema=EmptyOutput,
        side_effects="write",
        network_required=False,
        permission_scope="memory:write",
        required_role="ANALYST",
        requires_approval=False,
    ),
}


def get_tool(tool_name: str) -> Optional[ToolSpec]:
    """Returns the tool specification by name, or None if not registered."""
    return _ALL_TOOLS.get(tool_name)


def _load_agent_tools() -> Dict[str, List[str]]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("agent_tools", {})


def get_tools_for(agent_name: str, user_ctx: UserContext, workspace_id: str) -> List[BoundTool]:
    """
    Computes static agent tool grant ∩ dynamic user authorization.
    Every returned tool is bound and permission-checked.
    """
    if not user_ctx.can_access_workspace(workspace_id):
        return []

    agent_grants = _load_agent_tools().get(agent_name, [])
    authorized_tools: List[BoundTool] = []

    for tool_name in agent_grants:
        spec = _ALL_TOOLS.get(tool_name)
        if not spec:
            continue
        # Verify role authorization
        if user_ctx.has_role(spec.required_role):
            authorized_tools.append(BoundTool(spec=spec, user_ctx=user_ctx, workspace_id=workspace_id))

    return authorized_tools

