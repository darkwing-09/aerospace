"""
orchestrator_planner.py
─────────────────────────────────────────────────────────────────
Dynamic Multi-Agent DAG Planner & Task Decomposition Engine.

Uses AGENT_MODEL_MAP["orchestrator"] (e.g. qwen2.5:7b-instruct / qwen2.5:3b)
to analyze technical & tactical queries across any document, determine
required capabilities, and emit an executable Directed Acyclic Graph (DAG).
"""

import json
import re
from typing import Dict, List, Any, Optional

from config import settings


DEFAULT_DAG_TEMPLATES = {
    "visual_math": {
        "intent": "VISUAL_AND_PHYSICS",
        "rationale": "Query involves layout diagrams, schematics, or tables along with numerical calculations.",
        "nodes": [
            {
                "id": "visual_schematic",
                "title": "ColPali Visual Schematics",
                "capability": "vision_table",
                "model": settings.AGENT_MODEL_MAP.get("vision_table", "qwen2.5-vl:7b"),
                "depends_on": [],
            },
            {
                "id": "avionics_physics",
                "title": "Avionics Physics Engine",
                "capability": "math",
                "model": settings.AGENT_MODEL_MAP.get("math", "qwen2.5-math:7b"),
                "depends_on": [],
            },
            {
                "id": "command_synthesis",
                "title": "Command Synthesis Briefing",
                "capability": "synthesis",
                "model": settings.AGENT_MODEL_MAP.get("synthesis", "qwen2.5:3b"),
                "depends_on": ["visual_schematic", "avionics_physics"],
            },
            {
                "id": "safety_verification",
                "title": "Flight Safety & SOP Audit",
                "capability": "verification",
                "model": settings.AGENT_MODEL_MAP.get("verification", "qwen2.5:3b-instruct"),
                "depends_on": ["command_synthesis"],
            },
        ],
    },
    "visual_only": {
        "intent": "SCHEMATIC_OR_PROCEDURE",
        "rationale": "Query focuses on diagrams, switch locations, wiring, text content, or document steps.",
        "nodes": [
            {
                "id": "visual_schematic",
                "title": "ColPali Visual Schematics",
                "capability": "vision_table",
                "model": settings.AGENT_MODEL_MAP.get("vision_table", "qwen2.5-vl:7b"),
                "depends_on": [],
            },
            {
                "id": "command_synthesis",
                "title": "Command Synthesis Briefing",
                "capability": "synthesis",
                "model": settings.AGENT_MODEL_MAP.get("synthesis", "qwen2.5:3b"),
                "depends_on": ["visual_schematic"],
            },
            {
                "id": "safety_verification",
                "title": "Flight Safety & SOP Audit",
                "capability": "verification",
                "model": settings.AGENT_MODEL_MAP.get("verification", "qwen2.5:3b-instruct"),
                "depends_on": ["command_synthesis"],
            },
        ],
    },
    "math_only": {
        "intent": "AERONAUTICAL_CALCULATION",
        "rationale": "Query strictly involves speed, Mach, fuel, formulas, or physics computations.",
        "nodes": [
            {
                "id": "avionics_physics",
                "title": "Avionics Physics Engine",
                "capability": "math",
                "model": settings.AGENT_MODEL_MAP.get("math", "qwen2.5-math:7b"),
                "depends_on": [],
            },
            {
                "id": "command_synthesis",
                "title": "Command Synthesis Briefing",
                "capability": "synthesis",
                "model": settings.AGENT_MODEL_MAP.get("synthesis", "qwen2.5:3b"),
                "depends_on": ["avionics_physics"],
            },
            {
                "id": "safety_verification",
                "title": "Flight Safety & SOP Audit",
                "capability": "verification",
                "model": settings.AGENT_MODEL_MAP.get("verification", "qwen2.5:3b-instruct"),
                "depends_on": ["command_synthesis"],
            },
        ],
    },
    "logistics": {
        "intent": "LOGISTICS_AND_PARTS",
        "rationale": "Query requires querying tabular inventory manifests, stock status, or records.",
        "nodes": [
            {
                "id": "logistics_inventory",
                "title": "Defense Inventory Manifests",
                "capability": "reasoning",
                "model": settings.AGENT_MODEL_MAP.get("reasoning", "deepseek-r1-distill-qwen:7b"),
                "depends_on": [],
            },
            {
                "id": "command_synthesis",
                "title": "Command Synthesis Briefing",
                "capability": "synthesis",
                "model": settings.AGENT_MODEL_MAP.get("synthesis", "qwen2.5:3b"),
                "depends_on": ["logistics_inventory"],
            },
            {
                "id": "safety_verification",
                "title": "Flight Safety & SOP Audit",
                "capability": "verification",
                "model": settings.AGENT_MODEL_MAP.get("verification", "qwen2.5:3b-instruct"),
                "depends_on": ["command_synthesis"],
            },
        ],
    },
}


def _heuristic_dag_fallback(query: str) -> Dict[str, Any]:
    """Fast deterministic task graph generator using strict word boundaries."""
    q_lower = query.lower()
    
    # Exact word boundary matching for math/aero terms
    math_words = [
        r"\bcalculate\b",
        r"\bmach\s*\d",
        r"\bfuel\s*(?:burn|flow|consumption|endurance)\b",
        r"\bburn\s*rate\b",
        r"\bconvert\b",
        r"\btas\b",
        r"\bknots\b",
        r"\bkg/min\b",
        r"\bdescent\s*rate\b",
        r"\btrue\s*airspeed\b",
    ]
    has_math = any(re.search(pattern, q_lower) for pattern in math_words)

    visual_words = [
        r"\bwhere\b",
        r"\bswitch\b",
        r"\bpanel\b",
        r"\bcockpit\b",
        r"\bgauge\b",
        r"\bschematic\b",
        r"\bdiagram\b",
        r"\blook\b",
        r"\blayout\b",
        r"\bprocedure\b",
        r"\bstart\b",
        r"\bemergency\b",
        r"\bshow\b",
        r"\bvalve\b",
        r"\bindicator\b",
        r"\bmanual\b",
        r"\bpage\b",
        r"\bfigure\b",
        r"\btable\b",
        r"\bfile\b",
        r"\bdocument\b",
        r"\bsyllabus\b",
        r"\btopic\b",
        r"\bwhat\b",
        r"\bexplain\b",
        r"\bsummarize\b",
        r"\bsection\b",
        r"\bchapter\b",
        r"\boutline\b",
        r"\blearning\b",
        r"\bcontent\b",
    ]
    has_visual = any(re.search(pattern, q_lower) for pattern in visual_words)

    logistics_words = [
        r"\binventory\b",
        r"\bpart\b",
        r"\bserial\b",
        r"\bstock\b",
        r"\bammunition\b",
        r"\breadiness\b",
        r"\bdepot\b",
        r"\bmanifest\b",
        r"\bcsv\b",
        r"\bxlsx\b",
        r"\bsheet\b",
    ]
    has_logistics = any(re.search(pattern, q_lower) for pattern in logistics_words)

    if has_logistics:
        return DEFAULT_DAG_TEMPLATES["logistics"]
    if has_math and has_visual:
        return DEFAULT_DAG_TEMPLATES["visual_math"]
    if has_math:
        return DEFAULT_DAG_TEMPLATES["math_only"]
    return DEFAULT_DAG_TEMPLATES["visual_only"]


class OrchestratorPlanner:
    """Dynamic DAG Task Decomposition Planner with Multi-Document Awareness."""

    @staticmethod
    async def plan_workflow(
        query: str,
        aircraft_id: Optional[str],
        model_service_instance,
    ) -> Dict[str, Any]:
        """
        Plans a dynamic DAG workflow for the given user query.
        Uses AGENT_MODEL_MAP['orchestrator'] to produce a structured JSON DAG.
        Handles both airframe-specific queries and multi-document / session file queries.
        """
        # Return structured template instantly for sub-millisecond planning latency
        return _heuristic_dag_fallback(query)


orchestrator_planner = OrchestratorPlanner()
