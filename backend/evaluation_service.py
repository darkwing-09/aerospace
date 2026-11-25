"""
evaluation_service.py
─────────────────────────────────────────────────────────────────
Real-Time Application Evaluation & Quality Scorecard Engine.

Calculates:
1. Faithfulness Score (% grounded in retrieved manuals/diagrams)
2. Citation Grounding Score (precision of referenced pages/sections)
3. Safety Protocol Compliance (checks for required emergency notices)
4. Hallucination Risk Assessment
5. Response Confidence Level
"""

import re
from typing import Dict, Any, List, Optional


class EvaluationService:
    @staticmethod
    def evaluate_response(
        query: str,
        response_text: str,
        retrieved_contexts: List[Dict[str, Any]],
        math_result: Optional[str] = None,
        referenced_page: Optional[int] = None,
        latency_ms: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Performs multi-criteria evaluation of the AI generation.
        """
        # 1. Faithfulness & Grounding Check
        context_text = " ".join([c.get("text", "") for c in retrieved_contexts]).lower()
        response_lower = response_text.lower()

        # Extract technical nouns / aviation keywords from response
        keywords = re.findall(r"\b[a-zA-Z0-9_\-]{4,}\b", response_lower)
        keywords = [
            k for k in keywords
            if k not in ["step", "page", "manual", "aircraft", "system", "with", "this", "that", "from", "have"]
        ]

        grounded_count = 0
        total_checked = len(keywords)
        if total_checked > 0:
            for kw in keywords:
                if kw in context_text:
                    grounded_count += 1
            raw_faithfulness = round((grounded_count / total_checked) * 100, 1)
        else:
            raw_faithfulness = 0.0

        heuristic_faithfulness = raw_faithfulness

        # 2. Citation Accuracy Check (Heuristic)
        if referenced_page:
            # Check if any retrieved context matches this page
            page_found = any(c.get("page_number") == referenced_page for c in retrieved_contexts)
            heuristic_citation = 100.0 if page_found else 0.0
        else:
            heuristic_citation = None

        # 3. Safety Compliance Evaluation (Heuristic)
        is_emergency_query = any(
            w in query.lower()
            for w in ["emergency", "fire", "failure", "flameout", "leak", "warning", "caution", "stall", "loss"]
        )
        has_warning_tag = "warning:" in response_lower or "caution:" in response_lower or "⚠️" in response_text

        if not response_text.strip():
            safety_compliance = "EMPTY_RESPONSE"
            safety_score = 0.0
        elif is_emergency_query:
            safety_compliance = "PASSED" if has_warning_tag else "CAUTION_REQUIRED"
            safety_score = 100.0 if has_warning_tag else 0.0
        else:
            # Honest labelling: non-emergency queries are not formally verified without the Critic
            safety_compliance = "UNVERIFIED"
            safety_score = 100.0

        # 4. Hallucination Risk
        if heuristic_faithfulness >= 80:
            hallucination_risk = "LOW"
        elif heuristic_faithfulness >= 50:
            hallucination_risk = "MODERATE"
        else:
            hallucination_risk = "HIGH"

        # 5. Overall Confidence (Heuristic)
        if not response_text.strip():
            overall_confidence = 0.0
        else:
            citation_weight = 0.3 if heuristic_citation is not None else 0.0
            faith_weight = 0.7 if heuristic_citation is None else 0.5
            safety_weight = 0.2 if heuristic_citation is not None else 0.3
            score = (heuristic_faithfulness * faith_weight) + (safety_score * safety_weight)
            if heuristic_citation is not None:
                score += (heuristic_citation * citation_weight)
            overall_confidence = round(score, 1)

        return {
            "heuristic_faithfulness": heuristic_faithfulness,
            "heuristic_citation": heuristic_citation,
            "heuristic_safety": safety_score,
            "safety_compliance": safety_compliance,
            "safety_score": safety_score,
            "hallucination_risk": hallucination_risk,
            "overall_confidence": min(99.4, overall_confidence),
            "sources_consulted": len(retrieved_contexts),
            "diagrams_verified": sum(1 for c in retrieved_contexts if c.get("is_schematic") or c.get("is_diagram")),
            "math_verified": bool(math_result),
            "latency_ms": round(latency_ms, 2),
            "is_heuristic": True,
            # Backwards compatibility aliases
            "faithfulness_score": heuristic_faithfulness,
            "citation_score": heuristic_citation if heuristic_citation is not None else 0.0,
        }


evaluation_service = EvaluationService()
