import re
import uuid
from typing import List, Dict, Any, Optional, Set, Tuple
from ingestion.evidence_unit import EvidenceUnit
from knowledge.graph_store import GraphStore, GraphEdge, GraphNode

REFERENCE_PATTERNS = [
    r"refer to",
    r"see\s+",
    r"in accordance with",
    r"per\s+",
    r"according to",
    r"as defined in",
    r"as detailed in"
]

CONTRADICTION_PATTERNS = [
    r"contradicts",
    r"supersedes",
    r"disagrees",
    r"conflicts with",
    r"revokes",
    r"updated to"
]

def _find_entity_mentions(text: str, nodes: List[GraphNode]) -> List[GraphNode]:
    """Matches registered graph nodes against text case-insensitively."""
    matched = []
    text_lower = text.lower()
    for node in nodes:
        node_name_clean = node.name.lower()
        if len(node_name_clean) >= 3 and node_name_clean in text_lower:
            matched.append(node)
        elif node.node_id.lower() in text_lower:
            matched.append(node)
    return matched

def compute_and_persist_edges(
    units: List[EvidenceUnit],
    graph_store: GraphStore,
    workspace_id: str
) -> List[GraphEdge]:
    """
    Computes graph relationships across EvidenceUnits and persists them to GraphStore.
    Types: references, corroborates, contradicts, co-occurs-in, temporally-adjacent-to.
    """
    # Fetch all nodes in workspace to match against
    with graph_store._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT node_id, workspace_id, name, entity_type, properties, created_at FROM graph_nodes WHERE workspace_id = ?", (workspace_id,))
        rows = cursor.fetchall()
        known_nodes = [
            GraphNode(
                node_id=r["node_id"],
                workspace_id=r["workspace_id"],
                name=r["name"],
                entity_type=r["entity_type"]
            )
            for r in rows
        ]

    computed_edges: List[GraphEdge] = []
    unit_to_entities: Dict[str, List[GraphNode]] = {}

    for unit in units:
        text = unit.extracted_text or ""
        matched = _find_entity_mentions(text, known_nodes)
        unit_to_entities[unit.id] = matched

        # 1. Co-occurrence & References within single unit
        if len(matched) >= 2:
            for i in range(len(matched)):
                for j in range(i + 1, len(matched)):
                    n1, n2 = matched[i], matched[j]
                    
                    # Co-occurs edge
                    edge_co = GraphEdge(
                        edge_id=f"co_{uuid.uuid4().hex[:12]}",
                        workspace_id=workspace_id,
                        source_id=n1.node_id,
                        target_id=n2.node_id,
                        edge_type="co-occurs-in",
                        confidence=0.85,
                        evidence_ids=[unit.id],
                        properties={"source_ref": unit.source_ref}
                    )
                    computed_edges.append(edge_co)

                    # Reference check
                    text_lower = text.lower()
                    has_ref = any(re.search(pat, text_lower) for pat in REFERENCE_PATTERNS)
                    if has_ref:
                        edge_ref = GraphEdge(
                            edge_id=f"ref_{uuid.uuid4().hex[:12]}",
                            workspace_id=workspace_id,
                            source_id=n1.node_id,
                            target_id=n2.node_id,
                            edge_type="references",
                            confidence=0.95,
                            evidence_ids=[unit.id],
                            properties={"citation_context": text[:120]}
                        )
                        computed_edges.append(edge_ref)

    # 2. Cross-unit analysis: Temporal Adjacency, Corroboration, Contradiction
    # Sort units by location line/page or provenance if available
    def _sort_key(u: EvidenceUnit):
        line = u.location.line_number if u.location else None
        page = u.location.page_number if u.location else None
        return (page or 0, line or 0, u.ingested_at)

    sorted_units = sorted(units, key=_sort_key)
    
    # Temporal adjacency for successive steps / lines
    for idx in range(len(sorted_units) - 1):
        u1, u2 = sorted_units[idx], sorted_units[idx + 1]
        line1 = u1.location.line_number if u1.location else None
        line2 = u2.location.line_number if u2.location else None

        is_sequential = False
        if line1 is not None and line2 is not None and line2 == line1 + 1:
            is_sequential = True
        elif u1.ingested_at <= u2.ingested_at and (line1 != line2 or (u1.location and u1.location.page_number != (u2.location and u2.location.page_number))):
            is_sequential = True

        if is_sequential:
            ents1 = unit_to_entities.get(u1.id, [])
            ents2 = unit_to_entities.get(u2.id, [])
            for e1 in ents1:
                for e2 in ents2:
                    if e1.node_id != e2.node_id:
                        edge_temp = GraphEdge(
                            edge_id=f"temp_{uuid.uuid4().hex[:12]}",
                            workspace_id=workspace_id,
                            source_id=e1.node_id,
                            target_id=e2.node_id,
                            edge_type="temporally-adjacent-to",
                            confidence=0.90,
                            evidence_ids=[u1.id, u2.id],
                            properties={"line_transition": f"{line1}->{line2}"}
                        )
                        computed_edges.append(edge_temp)

    # Contradiction / Corroboration across units sharing entities
    for i in range(len(units)):
        for j in range(i + 1, len(units)):
            u1, u2 = units[i], units[j]
            ents1 = set(e.node_id for e in unit_to_entities.get(u1.id, []))
            ents2 = set(e.node_id for e in unit_to_entities.get(u2.id, []))
            common = ents1.intersection(ents2)
            
            for ent_id in common:
                t1 = (u1.extracted_text or "").lower()
                t2 = (u2.extracted_text or "").lower()
                
                # Check for explicit contradiction or conflicting numeric values
                is_contra = (
                    any(re.search(pat, t1) for pat in CONTRADICTION_PATTERNS) or
                    any(re.search(pat, t2) for pat in CONTRADICTION_PATTERNS)
                )
                
                # Number check in sentences
                nums1 = set(re.findall(r"\b\d+\b", t1))
                nums2 = set(re.findall(r"\b\d+\b", t2))
                if ("maximum" in t1 or "limit" in t1) and ("maximum" in t2 or "limit" in t2) and nums1 != nums2:
                    is_contra = True
                    
                if is_contra:
                    edge_contra = GraphEdge(
                        edge_id=f"contra_{uuid.uuid4().hex[:12]}",
                        workspace_id=workspace_id,
                        source_id=ent_id,
                        target_id=ent_id,
                        edge_type="contradicts",
                        confidence=0.92,
                        evidence_ids=[u1.id, u2.id],
                        properties={"conflict_description": f"Conflicting statements in {u1.id} and {u2.id}"}
                    )
                    computed_edges.append(edge_contra)
                elif nums1 and nums1 == nums2:
                    edge_corrob = GraphEdge(
                        edge_id=f"corrob_{uuid.uuid4().hex[:12]}",
                        workspace_id=workspace_id,
                        source_id=ent_id,
                        target_id=ent_id,
                        edge_type="corroborates",
                        confidence=0.88,
                        evidence_ids=[u1.id, u2.id],
                        properties={"corroborating_data": list(nums1)}
                    )
                    computed_edges.append(edge_corrob)

    # Persist all computed edges to GraphStore
    for edge in computed_edges:
        graph_store.upsert_edge(edge)

    return computed_edges
