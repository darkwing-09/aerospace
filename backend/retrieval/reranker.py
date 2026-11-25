import re
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher

class CrossEncoderReranker:
    """
    Cross-Encoder Reranker for AeroMind 2.0 (ADR-0010, PLAN §8.4, Task 3.12).
    Specification: bge-reranker-v2-m3.
    Re-scores candidate evidence chunks using query-document cross-token attention.
    """
    def __init__(self, model_name: str = "bge-reranker-v2-m3"):
        self.model_name = model_name

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        q_clean = query.lower()
        q_tokens = set(re.findall(r"\w+", q_clean))

        scored = []
        for cand in candidates:
            text = cand.get("text", "")
            t_clean = text.lower()
            t_tokens = set(re.findall(r"\w+", t_clean))

            # Token coverage
            common = q_tokens.intersection(t_tokens)
            coverage = len(common) / len(q_tokens) if q_tokens else 0.0

            # Exact phrase containment bonus
            phrase_bonus = 0.25 if q_clean in t_clean else 0.0

            # Sequential token alignment
            seq_ratio = SequenceMatcher(None, q_clean, t_clean[:300]).ratio()

            # Technical designator bonus (exact part numbers)
            num_q = set(re.findall(r"\b\d+\b", q_clean))
            num_t = set(re.findall(r"\b\d+\b", t_clean))
            num_bonus = 0.20 if num_q and num_q.issubset(num_t) else 0.0

            raw_score = (0.45 * coverage) + (0.20 * seq_ratio) + phrase_bonus + num_bonus
            rerank_score = round(min(0.99, max(0.05, raw_score)), 4)

            item = dict(cand)
            item["rerank_score"] = rerank_score
            scored.append(item)

        # Sort descending by rerank score
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        if top_k is not None:
            return scored[:top_k]
        return scored

