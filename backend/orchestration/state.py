"""
backend/orchestration/state.py
─────────────────────────────────────────────────────────────────
Typed Orchestration State for AeroMind 2.0 (PLAN §7.3, §7.4).
Enforces reducer semantics, structural evidence references, and
JSON-serializable checkpointer state.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

from langgraph.graph.message import add_messages

EvidenceTag = Literal["observed", "retrieved", "inferred", "uncertain"]

ExecutionStatus = Literal[
    "RUNNING",
    "WAITING_FOR_USER",
    "APPROVAL_REQUIRED",
    "PAUSED",
    "RESUMED",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]

TaskType = Literal[
    "code_gen",
    "retrieval",
    "multimodal",
    "correlation",
    "drafting",
    "data_analysis",
    "clarify",
]


class EvidenceRef(TypedDict):
    source_id: str  # References EvidenceUnit.id
    tag: EvidenceTag
    confidence: float


class ToolCallRecord(TypedDict):
    tool_name: str
    inputs: Dict[str, Any]
    output: str
    succeeded: bool


class AgentMessage(TypedDict):
    from_agent: str
    to_agent: str
    task_id: str
    payload: Dict[str, Any]
    evidence_refs: List[EvidenceRef]  # REQUIRED if payload makes factual claims
    inference: bool  # True if claim is model-inferred with no direct evidence
    confidence: float
    requires_human_approval: bool
    agent_version: str


class WorkbenchState(TypedDict):
    # Identity & tenant scope (set by gateway; never by the model)
    task: str
    task_id: str  # unique per task — NOT derived from conversation_id
    user_id: str
    workspace_id: str
    conversation_id: str
    parent_task_id: Optional[str]
    attachments: List[str]

    # Working memory (reducers enforce immutable state accumulation)
    messages: Annotated[List[Any], add_messages]
    tool_calls: Annotated[List[ToolCallRecord], operator.add]
    evidence: Annotated[List[EvidenceRef], operator.add]
    agent_messages: Annotated[List[AgentMessage], operator.add]

    # Planning & evaluation
    task_type: Optional[TaskType]  # MUST be declared (pitfall §11.1)
    plan: Optional[Dict[str, Any]]
    evaluation: Optional[Dict[str, Any]]
    execution_status: ExecutionStatus
    user_approval_granted: Optional[bool]
    retry_count: int

    # V1: memory, correlation, continuation
    correlation_results: Optional[List[Dict[str, Any]]]
    continuation_proposal: Optional[str]

    # Control flow
    step_count: int
    max_steps: int
    done: bool

    # Result
    result: Optional[str]
    artifacts: List[Dict[str, Any]]
    needs_human_review: bool
    review_reason: Optional[str]

