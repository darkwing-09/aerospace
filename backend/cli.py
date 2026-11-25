#!/usr/bin/env python3
"""
backend/cli.py
─────────────────────────────────────────────────────────────────
AeroMind 2.0 CLI Interface (Task 0.5 / PLAN §8.1).
Executes tasks through the minimal LangGraph execution DAG.
"""

import sys
from pathlib import Path

# Add backend and venv to path if invoked directly
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

venv_site = backend_dir / "venv/lib/python3.13/site-packages"
if venv_site.exists() and str(venv_site) not in sys.path:
    sys.path.insert(0, str(venv_site))

from orchestration.graph import run_task


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 cli.py \"<task description>\"")
        return 1

    task = sys.argv[1]
    print(f"\n========================================================")
    print(f" AeroMind 2.0 Task Runner: \"{task}\"")
    print(f"========================================================\n")

    try:
        final_state = run_task(task)
    except Exception as e:
        print(f"[ERROR] Graph execution failed: {e}")
        return 1

    task_type = final_state.get("task_type")
    status = final_state.get("execution_status")
    result = final_state.get("result")
    eval_rep = final_state.get("evaluation")
    needs_review = final_state.get("needs_human_review")
    review_reason = final_state.get("review_reason")
    tool_calls = final_state.get("tool_calls", [])

    print(f"Task ID:          {final_state.get('task_id')}")
    print(f"Declared Type:    {task_type}")
    print(f"Execution Status: {status}")
    print(f"Steps Executed:   {final_state.get('step_count')}")

    if tool_calls:
        print(f"\nTool Invocations ({len(tool_calls)}):")
        for tc in tool_calls:
            print(f"  - Tool: {tc['tool_name']} | Succeeded: {tc['succeeded']}")
            output_snippet = tc['output'].strip()[:140]
            print(f"    Output: {output_snippet}")

    if eval_rep:
        print(f"\nCritic Evaluation:")
        print(f"  Verdict:       {eval_rep.get('verdict')}")
        print(f"  Faithfulness:  {eval_rep.get('faithfulness')}")
        print(f"  Reason:        {eval_rep.get('reason')}")

    print(f"\nHuman Review Required: {needs_review}")
    if review_reason:
        print(f"Review Reason:         {review_reason}")

    print(f"\nFinal Result:\n{result}\n")
    print(f"========================================================\n")

    return 0 if status == "COMPLETED" and not needs_review else (0 if needs_review and status == "COMPLETED" else 1)


if __name__ == "__main__":
    sys.exit(main())

