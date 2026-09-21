#!/usr/bin/env python3
"""
B4 — Router Accuracy (AS_IS)
──────────────────────────────
Runs gold.jsonl questions through the regex heuristic router
(OrchestratorPlanner.plan_dag) and checks whether the intent
classification matches the expected task_type.

Maps gold task_type → expected router intents:
  factual      → FACTUAL or GENERAL
  table_drawing → VISUAL_QUERY or VISUAL_AND_PHYSICS
  numeric      → PHYSICS_CALCULATION or VISUAL_AND_PHYSICS
  code         → GENERAL (no code specialist exists)
  out_of_scope → GENERAL or FACTUAL (no OOS detection)
  injection    → GENERAL (no guard exists)
"""

import json, sys, re
from pathlib import Path

# Add backend to path so we can import the planner
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Expected mapping: what the router SHOULD ideally route to
IDEAL_ROUTES = {
    "factual": {"FACTUAL", "GENERAL"},
    "table_drawing": {"VISUAL_QUERY", "VISUAL_AND_PHYSICS"},
    "numeric": {"PHYSICS_CALCULATION", "VISUAL_AND_PHYSICS"},
    "code": {"GENERAL"},  # no code specialist
    "out_of_scope": {"GENERAL", "FACTUAL"},  # no OOS detection
    "injection": {"GENERAL", "FACTUAL"},  # no guard
}


def load_gold():
    with open(Path(__file__).parent / "gold.jsonl") as f:
        data = json.load(f)
    return data["questions"]


def classify_query(query: str) -> str:
    """
    Reproduce the regex router from orchestrator_planner.py _classify_intent().
    This avoids needing to instantiate the full backend.
    """
    q_lower = query.lower()

    # Physics patterns (from orchestrator_planner.py L143-162)
    physics_patterns = [
        r'\b(calculate|compute|convert|how (?:much|many|long|far|fast))\b',
        r'\b(speed|velocity|altitude|fuel|range|endurance|mach|knots?|km/?h|mph)\b',
        r'\b(temperature|pressure|thrust|weight|mass|force|drag|lift)\b',
        r'\b(rate|ratio|percentage|formula|equation)\b',
        r'\d+\s*(?:kg|km|m|ft|lbs?|gallons?|litres?|minutes?|hours?|seconds?)',
    ]

    # Visual patterns (from orchestrator_planner.py L164-175)
    visual_patterns = [
        r'\b(show|display|where|locate|find|identify|point)\b.*\b(diagram|schematic|panel|cockpit|layout|gauge|switch|indicator|instrument)\b',
        r'\b(diagram|schematic|cockpit|panel|layout)\b',
        r'\b(page|figure|image|photo|picture|drawing)\b',
        r'\b(look|see|visual|identify)\b.*\b(in|on|at)\b.*\b(manual|document|pdf)\b',
    ]

    has_physics = any(re.search(p, q_lower) for p in physics_patterns)
    has_visual = any(re.search(p, q_lower) for p in visual_patterns)

    if has_physics and has_visual:
        return "VISUAL_AND_PHYSICS"
    elif has_visual:
        return "VISUAL_QUERY"
    elif has_physics:
        return "PHYSICS_CALCULATION"
    else:
        return "FACTUAL"


def main():
    questions = load_gold()
    results = []
    correct = 0
    total = 0

    # Confusion matrix
    categories = sorted(set(q["task_type"] for q in questions))
    confusion = {cat: {} for cat in categories}

    for q in questions:
        predicted = classify_query(q["question"])
        expected_set = IDEAL_ROUTES.get(q["task_type"], {"GENERAL"})
        is_correct = predicted in expected_set

        if is_correct:
            correct += 1
        total += 1

        # Track confusion
        confusion.setdefault(q["task_type"], {})
        confusion[q["task_type"]][predicted] = confusion[q["task_type"]].get(predicted, 0) + 1

        results.append({
            "id": q["id"],
            "question": q["question"][:80],
            "task_type": q["task_type"],
            "predicted_intent": predicted,
            "acceptable_intents": list(expected_set),
            "correct": is_correct,
        })

    accuracy = round(correct / total * 100, 1) if total > 0 else 0

    # Per-category accuracy
    cat_acc = {}
    for cat in categories:
        cat_qs = [r for r in results if r["task_type"] == cat]
        cat_correct = sum(1 for r in cat_qs if r["correct"])
        cat_acc[cat] = {
            "total": len(cat_qs),
            "correct": cat_correct,
            "accuracy_pct": round(cat_correct / len(cat_qs) * 100, 1) if cat_qs else 0,
        }

    output = {
        "benchmark": "B4_router_accuracy_AS_IS",
        "router_type": "regex_heuristic",
        "router_file": "backend/orchestrator_planner.py",
        "router_function": "_classify_intent (lines 137-212)",
        "total_questions": total,
        "correct": correct,
        "accuracy_pct": accuracy,
        "per_category": cat_acc,
        "confusion_matrix": confusion,
        "details": results,
    }

    out_file = RESULTS_DIR / "b4_router_accuracy_AS_IS.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"[B4] Router accuracy: {accuracy}% ({correct}/{total})")
    for cat, info in cat_acc.items():
        print(f"  {cat:15s}: {info['accuracy_pct']:5.1f}% ({info['correct']}/{info['total']})")
    print(f"\n[B4] Confusion matrix:")
    for cat, preds in confusion.items():
        print(f"  {cat}: {preds}")
    print(f"\n[B4] Results saved to {out_file}")


if __name__ == "__main__":
    main()
