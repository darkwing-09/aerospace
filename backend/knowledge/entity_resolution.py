import re
from typing import Dict, Any, List, Tuple
from difflib import SequenceMatcher

# 20 hand-labelled pairs of equipment, subsystems, and parameters for entity resolution benchmark (Task 3.2)
LABELLED_BENCHMARK_PAIRS: List[Dict[str, Any]] = [
    # Positive pairs (True equivalence / synonyms / abbreviations)
    {"e1": "Pump 104", "e2": "P-104", "is_match": True, "rationale": "Equipment prefix abbreviation"},
    {"e1": "Fuel pump No.1", "e2": "Fuel Pump #1", "is_match": True, "rationale": "Numeric designator formatting variant"},
    {"e1": "MiG-21bis", "e2": "MiG 21 bis", "is_match": True, "rationale": "Hyphenation and spacing variant"},
    {"e1": "Airspeed Indicator", "e2": "ASI", "is_match": True, "rationale": "Standard avionics acronym"},
    {"e1": "Emergency Landing Gear Lever", "e2": "Emerg. LG lever", "is_match": True, "rationale": "Aviation component abbreviation"},
    {"e1": "Afterburner", "e2": "Reheat", "is_match": True, "rationale": "Standard jet propulsion synonym"},
    {"e1": "SPS-141 ECM Pod", "e2": "SPS 141 Electronic Countermeasures", "is_match": True, "rationale": "Acronym expansion"},
    {"e1": "Altimeter VD-20", "e2": "VD-20 Altimeter", "is_match": True, "rationale": "Word order permutation"},
    {"e1": "Bleed Air Valve", "e2": "Bleed-air valve", "is_match": True, "rationale": "Hyphenation and case variant"},
    {"e1": "Oxygen Mask KM-32", "e2": "KM-32 mask", "is_match": True, "rationale": "Identifier match with partial noun omission"},

    # Negative pairs (Hard negatives: distinct equipment, numbers, or functions)
    {"e1": "Fuel pump No.1", "e2": "Fuel pump No.2", "is_match": False, "rationale": "Distinct pump unit numbers"},
    {"e1": "Radar RP-22", "e2": "Radar RP-21", "is_match": False, "rationale": "Distinct radar model generations"},
    {"e1": "Altimeter VD-20", "e2": "Altimeter VD-10", "is_match": False, "rationale": "Distinct instrument range models"},
    {"e1": "Hydraulic System 1", "e2": "Hydraulic System 2", "is_match": False, "rationale": "Independent redundant hydraulic circuits"},
    {"e1": "Oxygen Mask KM-32", "e2": "Oxygen Mask KM-34", "is_match": False, "rationale": "Distinct mask model types"},
    {"e1": "Airspeed Indicator", "e2": "Attitude Indicator", "is_match": False, "rationale": "Completely distinct avionics flight instruments"},
    {"e1": "Emergency Landing Gear Lever", "e2": "Flap Control Lever", "is_match": False, "rationale": "Distinct cockpit control levers"},
    {"e1": "Engine AP-9", "e2": "Engine AP-11", "is_match": False, "rationale": "Distinct auxiliary power units"},
    {"e1": "Main Fuel Tank 1", "e2": "Main Fuel Tank 3", "is_match": False, "rationale": "Distinct fuselage fuel cell locations"},
    {"e1": "Afterburner", "e2": "Compressor", "is_match": False, "rationale": "Distinct thermodynamic stages of jet engine"}
]

# Aviation canonical abbreviations and synonym dictionary
AVIATION_SYNONYMS: Dict[str, str] = {
    "asi": "airspeed indicator",
    "lg": "landing gear",
    "emerg": "emergency",
    "reheat": "afterburner",
    "ecm": "electronic countermeasures",
    "alt": "altimeter",
    "p": "pump"
}

def _extract_numbers(text: str) -> List[str]:
    """Extract all individual numeric tokens or model designators."""
    return re.findall(r"\b\d+\b", text)

def _normalize_tokens(text: str) -> List[str]:
    """Tokenize and expand abbreviations."""
    # Replace symbols and hyphens
    t = text.lower().replace("#", " number ").replace("no.", " number ").replace("no ", " number ")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    raw_tokens = [tok for tok in t.split() if tok]
    
    expanded = []
    for tok in raw_tokens:
        if tok in AVIATION_SYNONYMS:
            expanded.extend(AVIATION_SYNONYMS[tok].split())
        else:
            expanded.append(tok)
    return expanded

def resolve_entity_pair_baseline(e1: str, e2: str) -> Dict[str, Any]:
    """Approach 1: Simple token overlap (Jaccard similarity)."""
    t1 = set(e1.lower().replace("-", " ").split())
    t2 = set(e2.lower().replace("-", " ").split())
    intersection = t1.intersection(t2)
    union = t1.union(t2)
    sim = len(intersection) / len(union) if union else 0.0
    is_match = sim >= 0.5
    return {
        "is_match": is_match,
        "confidence": round(sim, 3),
        "reason": f"Baseline Jaccard overlap: {sim:.2f}"
    }

def resolve_entity_pair_hybrid(e1: str, e2: str) -> Dict[str, Any]:
    """
    Approach 2: Hybrid Rule-Aviation Normalizer.
    - Rule 1: Strict numeric designator equality (different numbers -> guaranteed negative).
    - Rule 2: Aviation abbreviation/synonym expansion.
    - Rule 3: Exact normalized token set match or high sequence similarity.
    """
    nums1 = _extract_numbers(e1)
    nums2 = _extract_numbers(e2)
    
    # Critical Safety Rule: If both specify numbers and they differ, never resolve as the same entity
    if nums1 and nums2 and set(nums1) != set(nums2):
        return {
            "is_match": False,
            "confidence": 0.1,
            "reason": f"Designator number mismatch: {nums1} != {nums2}"
        }
        
    toks1 = _normalize_tokens(e1)
    toks2 = _normalize_tokens(e2)
    
    set1, set2 = set(toks1), set(toks2)
    if set1 == set2:
        return {
            "is_match": True,
            "confidence": 1.0,
            "reason": "Exact canonical token match"
        }
        
    # Check subset containment when numbers match
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    jaccard = len(intersection) / len(union) if union else 0.0
    
    # Token difference analysis
    diff1 = set1 - set2
    diff2 = set2 - set1
    
    # If both sides contain distinct unshared descriptors (neither is a subset)
    if diff1 and diff2:
        # Check if the unshared words are just morphological variants / typos
        has_similar_descriptor = False
        for w1 in diff1:
            for w2 in diff2:
                if SequenceMatcher(None, w1, w2).ratio() >= 0.75:
                    has_similar_descriptor = True
                    break
            if has_similar_descriptor:
                break
        if not has_similar_descriptor:
            # They describe distinct items (e.g. "airspeed indicator" vs "attitude indicator")
            return {
                "is_match": False,
                "confidence": 0.2,
                "reason": f"Distinct differentiating descriptors: {diff1} vs {diff2}"
            }

    # Sequence matching on normalized string
    str1 = " ".join(sorted(toks1))
    str2 = " ".join(sorted(toks2))
    seq_ratio = SequenceMatcher(None, str1, str2).ratio()
    
    # Combined score
    confidence = max(jaccard, seq_ratio)
    
    # Specific checks for high-confidence matches
    # If one is subset of another and length difference is minor, or acronym matched
    is_subset = set1.issubset(set2) or set2.issubset(set1)
    if is_subset and len(intersection) >= 2 and (not nums1 or set(nums1) == set(nums2)):
        confidence = max(confidence, 0.85)
        
    is_match = confidence >= 0.70
    return {
        "is_match": is_match,
        "confidence": round(confidence, 3),
        "reason": f"Hybrid canonical score: {confidence:.2f} (Jaccard={jaccard:.2f}, Seq={seq_ratio:.2f})"
    }

def resolve_entity_pair(e1: str, e2: str, approach: str = "hybrid_canonical") -> Dict[str, Any]:
    if approach == "baseline":
        return resolve_entity_pair_baseline(e1, e2)
    return resolve_entity_pair_hybrid(e1, e2)

def benchmark_entity_resolution(approach: str = "hybrid_canonical") -> Dict[str, float]:
    """Run benchmark against LABELLED_BENCHMARK_PAIRS and compute P/R/F1."""
    tp, fp, tn, fn = 0, 0, 0, 0
    
    for item in LABELLED_BENCHMARK_PAIRS:
        res = resolve_entity_pair(item["e1"], item["e2"], approach=approach)
        pred = res["is_match"]
        actual = item["is_match"]
        
        if pred and actual:
            tp += 1
        elif pred and not actual:
            fp += 1
        elif not pred and actual:
            fn += 1
        else:
            tn += 1
            
    total = len(LABELLED_BENCHMARK_PAIRS)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0
    
    return {
        "approach": approach,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4)
    }
