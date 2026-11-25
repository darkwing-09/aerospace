"""
langsmith_service.py
─────────────────────────────────────────────────────────────────
LangSmith Tracing, Observability & Prompt Logging for AeroMind.

Traces multi-agent execution graphs, worker agent sub-prompts, tool calls,
and outputs both to the LangSmith cloud and local inspection cache.
"""

import os
import time
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import settings

def _is_egress_blocked() -> bool:
    """Enforce zero-egress rule: cloud tracing only allowed if ZERO_EGRESS_MODE=false AND AEROMIND_ENV=dev."""
    zero_egress = os.getenv("ZERO_EGRESS_MODE", str(getattr(settings, "ZERO_EGRESS_MODE", True))).lower() in ("true", "1", "yes")
    env = os.getenv("AEROMIND_ENV", getattr(settings, "AEROMIND_ENV", "local")).lower()
    return zero_egress or env != "dev"

# Configure environment for official LangSmith / LangChain SDK only when cloud egress is explicitly allowed in dev
if not _is_egress_blocked() and (settings.LANGCHAIN_API_KEY or os.getenv("LANGCHAIN_API_KEY")):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY or os.getenv("LANGCHAIN_API_KEY", "")
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT


class LangSmithService:
    def __init__(self):
        self.traces_dir = Path(settings.TRACES_DIR)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.client = None
        self._init_client()

    def _init_client(self):
        if _is_egress_blocked():
            self.client = None
            return
        api_key = settings.LANGCHAIN_API_KEY or os.getenv("LANGCHAIN_API_KEY")
        if api_key:
            try:
                from langsmith import Client
                self.client = Client(
                    api_url=settings.LANGCHAIN_ENDPOINT,
                    api_key=api_key,
                )
                print(f"[LangSmith] Connected to project: {settings.LANGCHAIN_PROJECT}")
            except Exception as e:
                print(f"[LangSmith] Cloud initialization skipped: {e}")
                self.client = None

    def is_cloud_enabled(self) -> bool:
        if _is_egress_blocked():
            return False
        return self.client is not None or bool(os.getenv("LANGCHAIN_API_KEY"))

    def create_run_trace(
        self,
        query: str,
        aircraft_id: str,
        plan: Dict[str, Any],
        agent_results: Dict[str, Any],
        final_response: str,
        evaluation: Dict[str, Any],
        latency_ms: float,
    ) -> str:
        """
        Creates a complete multi-agent execution trace record.
        Saves locally for immediate prompt inspection and forwards to LangSmith Cloud if configured.
        """
        run_id = str(uuid.uuid4())
        trace_record = {
            "run_id": run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "project": settings.LANGCHAIN_PROJECT,
            "aircraft_id": aircraft_id,
            "query": query,
            "plan": plan,
            "agent_steps": agent_results,
            "response": final_response,
            "evaluation": evaluation,
            "latency_ms": latency_ms,
            "cloud_synced": self.is_cloud_enabled(),
        }

        # Save local JSON trace
        trace_file = self.traces_dir / f"trace_{run_id}.json"
        try:
            with open(trace_file, "w", encoding="utf-8") as f:
                json.dump(trace_record, f, indent=2)
        except Exception as e:
            print(f"[LangSmith] Local trace save error: {e}")

        # Send to LangSmith Cloud if available
        if self.client:
            try:
                self.client.create_run(
                    name="aeromind_multiagent_pipeline",
                    run_type="chain",
                    inputs={"query": query, "aircraft": aircraft_id},
                    outputs={"response": final_response[:500], "evaluation": evaluation},
                    extra={"plan": plan, "latency_ms": latency_ms},
                    project_name=settings.LANGCHAIN_PROJECT,
                )
            except Exception as e:
                print(f"[LangSmith] Cloud sync error: {e}")

        return run_id

    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent traces for the Prompt & Trace Inspector UI."""
        traces = []
        files = sorted(self.traces_dir.glob("trace_*.json"), key=os.path.getmtime, reverse=True)
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as tf:
                    traces.append(json.load(tf))
            except Exception:
                pass
        return traces


langsmith_service = LangSmithService()
