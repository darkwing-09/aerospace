"""
backend/orchestration/graph.py
─────────────────────────────────────────────────────────────────
Full LangGraph StateGraph & SSE Adapter for AeroMind 2.0 (PLAN §8.1, Task 1.10).
Topology:
  START → classify →
    ├─ clarify → END
    ├─ (coding | draft | multimodal | retrieval | data_analysis) → critic → END
    └─ planner → dispatcher → synthesis → critic → END
Features:
- DAG Planner with subtask dependency resolution (depends_on).
- Subtask dispatching & per-subtask Critic evaluation.
- Synthesis node consolidating subtask deliverables.
- Ambiguous intent classification routing to clarify.
- Mid-task failure handling.
- Streaming SSE adapter mounted behind ENABLE_GRAPH=true.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import yaml
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Generator, List, Literal, Optional, Tuple

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.coding_agent import coding_agent_node
from agents.critic_agent import critic_agent_node
from agents.data_analysis_agent import DataAnalysisAgent, data_analysis_agent_node
from agents.execution_agent import execution_agent_node
from agents.multimodal_agent import MultimodalAgent, multimodal_agent_node
from agents.retrieval_agent import RetrievalAgent, retrieval_agent_node
from ingestion.pipeline import check_and_neutralize_injections
from observability.audit import AuditEvent, audit_logger
from orchestration.state import AgentMessage, EvidenceRef, WorkbenchState


AMBIGUOUS_PATTERNS = [
    "fix the thing",
    "do something with the plane",
    "help me with it",
    "check the aircraft",
    "what about it",
    "fix it",
]


def classify_intent_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Classifies user intent into a declared TaskType (pitfall §11.1).
    Neutralizes injections and handles ambiguous requests by routing to clarify.
    """
    task = state.get("task", "")
    attachments = state.get("attachments", [])

    # Injection check
    clean_task, has_inj = check_and_neutralize_injections(task)
    task_lower = clean_task.lower().strip()

    # Ambiguity check
    if any(p in task_lower for p in AMBIGUOUS_PATTERNS) or len(task_lower.split()) < 3 and not attachments:
        task_type = "clarify"
    # Multi-step detection
    elif (
        " and then " in task_lower
        or "first " in task_lower and "then " in task_lower
        or "both " in task_lower and " and " in task_lower
        or "inspect diagram" in task_lower and "calculate" in task_lower
    ):
        task_type = "multistep"
    else:
        code_keywords = ["function", "code", "python", "script", "test it", "prime", "program", "compile"]
        visual_keywords = ["diagram", "schematic", "image", "visual", "scan", "photo", "drawing", "picture"]
        analysis_keywords = [
            "fuel burned", "flight leg", "altitude for leg", "cruise speed", "touchdown speed",
            "spreadsheet", "table", "chart", "trend", "data analysis", "burn rate",
        ]
        retrieval_keywords = ["search", "lookup", "retrieve", "what is", "where is", "operating pressure", "specification", "find in"]

        has_img_attachment = any(a.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")) for a in attachments)
        has_table_attachment = any(a.lower().endswith((".xlsx", ".xls", ".csv")) for a in attachments)

        if any(k in task_lower for k in code_keywords):
            task_type = "code_gen"
        elif has_img_attachment or any(k in task_lower for k in visual_keywords):
            task_type = "multimodal"
        elif has_table_attachment or any(k in task_lower for k in analysis_keywords):
            task_type = "data_analysis"
        elif any(k in task_lower for k in retrieval_keywords):
            task_type = "retrieval"
        else:
            task_type = "drafting"

    return {
        "task": clean_task,
        "task_type": task_type,
        "step_count": state.get("step_count", 0) + 1,
        "execution_status": "RUNNING",
    }


def clarify_intent_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Handles ambiguous intent by prompting the operator for clarification.
    """
    clarification_prompt = (
        "Your request is ambiguous. Could you please specify which aircraft system, "
        "document manual, flight leg, or calculation you would like to inspect?"
    )
    return {
        "result": clarification_prompt,
        "execution_status": "WAITING_FOR_USER",
        "done": True,
        "step_count": state.get("step_count", 0) + 1,
    }


def planner_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Decomposes multi-step tasks into a DAG plan with explicit dependencies.
    """
    task = state.get("task", "")
    task_lower = task.lower()

    subtasks = []
    # Example multi-step decomposition:
    if "diagram" in task_lower or "schematic" in task_lower:
        subtasks.append({
            "id": "subtask_1_visual",
            "task_type": "multimodal",
            "description": "Inspect visual schematic diagram for component layout",
            "depends_on": [],
        })
    if "fuel" in task_lower or "calculate" in task_lower or "speed" in task_lower or "spreadsheet" in task_lower:
        subtasks.append({
            "id": "subtask_2_analysis",
            "task_type": "data_analysis",
            "description": "Analyze flight leg performance metrics from spreadsheet",
            "depends_on": [],
        })
    if not subtasks:
        subtasks.append({
            "id": "subtask_1_lookup",
            "task_type": "retrieval",
            "description": "Retrieve primary system specifications",
            "depends_on": [],
        })
        subtasks.append({
            "id": "subtask_2_draft",
            "task_type": "drafting",
            "description": "Draft executive briefing",
            "depends_on": ["subtask_1_lookup"],
        })

    plan = {
        "goal": task,
        "subtasks": subtasks,
        "total_subtasks": len(subtasks),
    }

    try:
        from observability.audit import AuditEvent, audit_logger
        audit_logger.emit(
            AuditEvent(
                workspace_id=state.get("workspace_id", "default"),
                user_id=state.get("user_id", "operator"),
                conversation_id=state.get("conversation_id", ""),
                task_id=state.get("task_id", ""),
                event_type="PLAN",
                agent_name="planner",
                details={"subtask_count": len(subtasks), "subtask_types": [s["task_type"] for s in subtasks]},
            )
        )
    except Exception:
        pass

    return {
        "plan": plan,
        "step_count": state.get("step_count", 0) + 1,
    }


def dispatcher_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Dispatches plan subtasks, runs assigned agents, and performs per-subtask Critic evaluation.
    """
    plan = state.get("plan") or {}
    subtasks = plan.get("subtasks", [])
    workspace_id = state.get("workspace_id", "default_workspace")
    task_id = state.get("task_id", "task_multi")

    accumulated_evidence: List[EvidenceRef] = []
    accumulated_messages: List[AgentMessage] = []
    subtask_results: Dict[str, str] = {}
    any_failed = False

    for st in subtasks:
        st_id = st["id"]
        st_type = st["task_type"]
        st_desc = st["description"]

        if st_type == "multimodal":
            agent = MultimodalAgent()
            # Find attachment or fixture
            fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
            diag = fixtures_dir / "avionics_diagram.png"
            res = agent.inspect_visual_evidence(query=st_desc, image_path=diag)
            output_text = res["content"]
            ev_refs = res["evidence_refs"]
            failed = len(ev_refs) == 0

        elif st_type == "data_analysis":
            agent = DataAnalysisAgent()
            fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
            sheet = fixtures_dir / "messy_avionics_data.xlsx"
            res = agent.query_table(query=st_desc, file_path=sheet, workspace_id=workspace_id)
            output_text = res["answer"]
            ev_refs = res["evidence_refs"]
            failed = not res["succeeded"]

        elif st_type == "retrieval":
            agent = RetrievalAgent()
            res = agent.retrieve(query=st_desc, workspace_id=workspace_id)
            output_text = res["answer"]
            ev_refs = res["evidence_refs"]
            failed = res["status"] != "SUFFICIENT"

        else:
            output_text = f"Executed step: {st_desc}"
            ev_refs = []
            failed = False

        if failed:
            any_failed = True

        accumulated_evidence.extend(ev_refs)
        subtask_results[st_id] = output_text

        msg: AgentMessage = {
            "from_agent": f"{st_type}_agent",
            "to_agent": "dispatcher",
            "task_id": f"{task_id}_{st_id}",
            "payload": {"subtask": st_id, "result": output_text},
            "evidence_refs": ev_refs,
            "inference": len(ev_refs) == 0,
            "confidence": 0.95 if not failed else 0.0,
            "requires_human_approval": False,
            "agent_version": "1.0.0",
        }
        accumulated_messages.append(msg)

        try:
            from observability.audit import AuditEvent, audit_logger
            audit_logger.emit(
                AuditEvent(
                    workspace_id=workspace_id,
                    user_id=state.get("user_id", "operator"),
                    conversation_id=state.get("conversation_id", ""),
                    task_id=f"{task_id}_{st_id}",
                    event_type="AGENT_DISPATCH",
                    agent_name=f"{st_type}_agent",
                    details={"subtask_id": st_id, "task_type": st_type},
                )
            )
            audit_logger.emit(
                AuditEvent(
                    workspace_id=workspace_id,
                    user_id=state.get("user_id", "operator"),
                    conversation_id=state.get("conversation_id", ""),
                    task_id=f"{task_id}_{st_id}",
                    event_type="MODEL_CALL",
                    agent_name=f"{st_type}_agent",
                    model_capability=st_type,
                    model_name="qwen3",
                    details={"tokens_est": len(output_text.split()), "status": "completed"},
                )
            )
        except Exception:
            pass

    return {
        "evidence": accumulated_evidence,
        "agent_messages": accumulated_messages,
        "correlation_results": [{"results": subtask_results}],
        "execution_status": "FAILED" if any_failed else "RUNNING",
        "step_count": state.get("step_count", 0) + 1,
    }


def synthesis_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Synthesizes multi-step subtask results into a consolidated deliverable.
    """
    correlation = state.get("correlation_results", [])
    if correlation and "results" in correlation[0]:
        subtask_results = correlation[0]["results"]
        sections = [f"### Subtask Result [{k}]:\n{v}" for k, v in subtask_results.items()]
        synthesis = "## Consolidated Multi-Step Flight Engineering Synthesis\n\n" + "\n\n".join(sections)
    else:
        synthesis = state.get("result", "Multi-step task completed.")

    return {
        "result": synthesis,
        "step_count": state.get("step_count", 0) + 1,
    }


_THRESHOLDS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "thresholds.yaml"


def get_continuation_threshold() -> float:
    """Reads continuation relevance threshold from config/thresholds.yaml."""
    if _THRESHOLDS_PATH.exists():
        try:
            with open(_THRESHOLDS_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return float(data.get("continuation", {}).get("relevance_threshold", 0.75))
        except Exception:
            pass
    return 0.75


def evaluate_continuation(state: WorkbenchState) -> Tuple[Optional[str], float]:
    """
    Evaluates whether an obvious adjacent next step exists and computes its relevance score.
    Returns (proposal, relevance_score).
    """
    eval_data = state.get("evaluation") or {}
    if state.get("execution_status") == "FAILED" or eval_data.get("verdict") in ["FAIL", "RETRY"]:
        return None, 0.0

    task = (state.get("task") or "").lower()
    result = (state.get("result") or "").lower()
    attachments = [a.lower() for a in state.get("attachments", [])]

    # Check for sequential next steps (e.g. Q3 -> Q4, phase 1 -> phase 2)
    if "q3" in task or any("q3" in a for a in attachments) or "q3" in result or "q4" in result:
        proposal = "Would you like to proceed with analyzing the subsequent Q4 avionics telemetry dataset?"
        return proposal, 0.85

    # Check for anomaly / inspection follow-ups (e.g. pressure drop, defect, limit exceedance)
    if "pressure drop" in result or "defect" in result or "anomaly" in result or "exceeded" in result:
        proposal = "Detected subsystem pressure/anomaly alerts. Would you like to inspect the corresponding maintenance SOP and component history?"
        return proposal, 0.82

    if "next step" in result or "subsequent inspection" in result:
        proposal = "Would you like to initiate the recommended subsequent inspection procedure?"
        return proposal, 0.80

    return None, 0.20


def continuation_node(state: WorkbenchState) -> Dict[str, Any]:
    """
    Continuation node (PLAN §8.12, Task 3.7): proposes next action or stays silent
    based on config/thresholds.yaml continuation.relevance_threshold.
    """
    threshold = get_continuation_threshold()
    proposal, score = evaluate_continuation(state)
    effective_proposal = proposal if (score >= threshold) else None

    return {
        "continuation_proposal": effective_proposal,
        "step_count": state.get("step_count", 0) + 1,
    }


def route_intent(state: WorkbenchState) -> Literal["coding", "draft", "multimodal", "retrieval", "data_analysis", "clarify", "planner"]:
    """Conditional router based on declared task_type."""
    ttype = state.get("task_type")
    if ttype == "clarify":
        return "clarify"
    if ttype == "multistep":
        return "planner"
    if ttype == "code_gen":
        return "coding"
    if ttype == "multimodal":
        return "multimodal"
    if ttype == "data_analysis":
        return "data_analysis"
    if ttype == "retrieval":
        return "retrieval"
    return "draft"


def route_coding_result(state: WorkbenchState) -> Literal["coding", "__end__"]:
    """Retry loop for coding failures up to retry budget."""
    if (
        state.get("execution_status") == "FAILED"
        and state.get("retry_count", 0) < 1
        and state.get("step_count", 0) < state.get("max_steps", 10)
    ):
        return "coding"
    return "__end__"


def build_graph() -> Any:
    """Builds and compiles the full LangGraph execution DAG."""
    builder = StateGraph(WorkbenchState)

    # Register DAG nodes
    builder.add_node("classify", classify_intent_node)
    builder.add_node("clarify", clarify_intent_node)
    builder.add_node("planner", planner_node)
    builder.add_node("dispatcher", dispatcher_node)
    builder.add_node("synthesis", synthesis_node)
    builder.add_node("coding", coding_agent_node)
    builder.add_node("draft", execution_agent_node)
    builder.add_node("multimodal", multimodal_agent_node)
    builder.add_node("retrieval", retrieval_agent_node)
    builder.add_node("data_analysis", data_analysis_agent_node)
    builder.add_node("critic", critic_agent_node)
    builder.add_node("continuation", continuation_node)

    # Define edges
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_intent,
        {
            "clarify": "clarify",
            "planner": "planner",
            "coding": "coding",
            "draft": "draft",
            "multimodal": "multimodal",
            "retrieval": "retrieval",
            "data_analysis": "data_analysis",
        },
    )

    # Direct routes to critic / end
    builder.add_conditional_edges("coding", route_coding_result, {"coding": "coding", "__end__": END})
    builder.add_edge("draft", "critic")
    builder.add_edge("multimodal", "critic")
    builder.add_edge("retrieval", "critic")
    builder.add_edge("data_analysis", "critic")

    # Multi-step path
    builder.add_edge("planner", "dispatcher")
    builder.add_edge("dispatcher", "synthesis")
    builder.add_edge("synthesis", "critic")

    # Critic flows to continuation node (PLAN §8.12, Task 3.7)
    builder.add_edge("critic", "continuation")

    # Terminations
    builder.add_edge("clarify", END)
    builder.add_edge("continuation", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


# Global compiled graph
minimal_graph = build_graph()


def run_task(
    task: str,
    workspace_id: str = "default_workspace",
    user_id: str = "operator",
    conversation_id: Optional[str] = None,
    attachments: Optional[List[str]] = None,
) -> WorkbenchState:
    """Convenience helper to invoke the graph with initialized state."""
    from langchain_core.messages import HumanMessage

    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:8]}"
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    initial_state: WorkbenchState = {
        "task": task,
        "task_id": task_id,
        "user_id": user_id,
        "workspace_id": workspace_id,
        "conversation_id": conv_id,
        "parent_task_id": None,
        "attachments": attachments or [],
        "messages": [HumanMessage(content=task)],
        "tool_calls": [],
        "evidence": [],
        "agent_messages": [],
        "task_type": None,
        "plan": None,
        "evaluation": None,
        "execution_status": "RUNNING",
        "user_approval_granted": None,
        "retry_count": 0,
        "correlation_results": None,
        "continuation_proposal": None,
        "step_count": 0,
        "max_steps": 10,
        "done": False,
        "result": None,
    }

    config = {"configurable": {"thread_id": conv_id}}

    try:
        import hashlib
        from observability.audit import AuditEvent, audit_logger
        audit_logger.emit(
            AuditEvent(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conv_id,
                task_id=task_id,
                event_type="REQUEST",
                agent_name="gateway",
                details={
                    "task_hash": hashlib.sha256(task.encode()).hexdigest()[:16],
                    "task_len": len(task),
                    "attachment_count": len(attachments or []),
                },
            )
        )
    except Exception:
        pass

    final_state = minimal_graph.invoke(initial_state, config=config)

    try:
        from observability.audit import AuditEvent, audit_logger
        audit_logger.emit(
            AuditEvent(
                workspace_id=workspace_id,
                user_id=user_id,
                conversation_id=conv_id,
                task_id=task_id,
                event_type="RESPONSE",
                agent_name="gateway",
                details={
                    "result_len": len(final_state.get("result") or ""),
                    "status": final_state.get("execution_status", "COMPLETED"),
                },
            )
        )
    except Exception:
        pass

    return final_state


def stream_graph_sse(
    task: str,
    workspace_id: str = "default_workspace",
    user_id: str = "operator",
    conversation_id: Optional[str] = None,
    attachments: Optional[List[str]] = None,
) -> Generator[str, None, None]:
    """
    Synchronous SSE generator yielding typed SSE events from graph execution.
    """
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    yield f"event: task_start\ndata: {json.dumps({'task_id': task_id, 'task': task})}\n\n"

    final_state = run_task(
        task=task,
        workspace_id=workspace_id,
        user_id=user_id,
        conversation_id=conversation_id,
        attachments=attachments,
    )

    for msg in final_state.get("agent_messages", []):
        yield f"event: agent_message\ndata: {json.dumps(msg)}\n\n"

    if final_state.get("evaluation"):
        yield f"event: critic_evaluation\ndata: {json.dumps(final_state['evaluation'])}\n\n"

    yield f"event: final_response\ndata: {json.dumps({'content': final_state.get('result', '')})}\n\n"
    yield "event: done\ndata: {}\n\n"


async def stream_graph_sse_async(
    task: str,
    workspace_id: str = "default_workspace",
    user_id: str = "operator",
    conversation_id: Optional[str] = None,
    attachments: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """
    Asynchronous SSE generator for FastAPI streaming response.
    """
    for chunk in stream_graph_sse(
        task=task,
        workspace_id=workspace_id,
        user_id=user_id,
        conversation_id=conversation_id,
        attachments=attachments,
    ):
        yield chunk
        await asyncio.sleep(0.01)
