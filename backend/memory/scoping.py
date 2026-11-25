from typing import Dict, Any, List

CLEARANCE_LEVELS: Dict[str, int] = {
    "UNCLASSIFIED": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4
}

def can_access(user_clearance: str, resource_classification: str) -> bool:
    """
    Returns True if user_clearance level is greater than or equal to resource_classification.
    Defaults to strict least-privilege on unknown levels.
    """
    user_lvl = CLEARANCE_LEVELS.get(user_clearance.upper(), 0)
    res_lvl = CLEARANCE_LEVELS.get(resource_classification.upper(), 4)
    return user_lvl >= res_lvl

def filter_by_scope(
    entries: List[Any],
    workspace_id: str,
    user_clearance: str
) -> List[Any]:
    """
    Filters memory entries to enforce workspace partition and clearance restrictions.
    """
    allowed = []
    for entry in entries:
        if getattr(entry, "workspace_id", None) != workspace_id:
            continue
        classification = getattr(entry, "classification_level", "INTERNAL")
        if can_access(user_clearance, classification):
            allowed.append(entry)
    return allowed

