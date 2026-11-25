import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class GraphNode:
    node_id: str
    workspace_id: str
    name: str
    entity_type: str = "equipment"
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class GraphEdge:
    edge_id: str
    workspace_id: str
    source_id: str
    target_id: str
    edge_type: str = "references"
    confidence: float = 1.0
    evidence_ids: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GraphStore:
    """
    In-process, SQLite-backed Knowledge Graph Store providing strict workspace isolation,
    typed edges, confidence scores, evidence linking, and multi-hop recursive queries.
    Conforms to ADR-0008.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.getenv("DATA_DIR")
            if data_dir:
                base_dir = data_dir
            else:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_repository"))
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.getenv("GRAPH_DB_PATH", os.path.join(base_dir, "graph.sqlite3"))
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    properties TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (node_id, workspace_id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    properties TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_nodes_ws ON graph_nodes(workspace_id, entity_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges(workspace_id, source_id, edge_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(workspace_id, target_id, edge_type)")
            conn.commit()

    def upsert_node(self, node: GraphNode):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO graph_nodes (node_id, workspace_id, name, entity_type, properties, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id, workspace_id) DO UPDATE SET
                    name = excluded.name,
                    entity_type = excluded.entity_type,
                    properties = excluded.properties,
                    created_at = excluded.created_at
            """, (
                node.node_id,
                node.workspace_id,
                node.name,
                node.entity_type,
                json.dumps(node.properties),
                node.created_at
            ))
            conn.commit()

    def get_node(self, node_id: str, workspace_id: str) -> Optional[GraphNode]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, workspace_id, name, entity_type, properties, created_at
                FROM graph_nodes
                WHERE node_id = ? AND workspace_id = ?
            """, (node_id, workspace_id))
            row = cursor.fetchone()
            if not row:
                return None
            return GraphNode(
                node_id=row["node_id"],
                workspace_id=row["workspace_id"],
                name=row["name"],
                entity_type=row["entity_type"],
                properties=json.loads(row["properties"]),
                created_at=row["created_at"]
            )

    def upsert_edge(self, edge: GraphEdge):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO graph_edges (edge_id, workspace_id, source_id, target_id, edge_type, confidence, evidence_ids, properties, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(edge_id) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    source_id = excluded.source_id,
                    target_id = excluded.target_id,
                    edge_type = excluded.edge_type,
                    confidence = excluded.confidence,
                    evidence_ids = excluded.evidence_ids,
                    properties = excluded.properties,
                    created_at = excluded.created_at
            """, (
                edge.edge_id,
                edge.workspace_id,
                edge.source_id,
                edge.target_id,
                edge.edge_type,
                float(edge.confidence),
                json.dumps(edge.evidence_ids),
                json.dumps(edge.properties),
                edge.created_at
            ))
            conn.commit()

    def get_edges(
        self,
        workspace_id: str,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        edge_type: Optional[str] = None,
        min_confidence: float = 0.0
    ) -> List[GraphEdge]:
        query = "SELECT edge_id, workspace_id, source_id, target_id, edge_type, confidence, evidence_ids, properties, created_at FROM graph_edges WHERE workspace_id = ? AND confidence >= ?"
        params: List[Any] = [workspace_id, min_confidence]
        if source_id:
            query += " AND source_id = ?"
            params.append(source_id)
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)
        if edge_type:
            query += " AND edge_type = ?"
            params.append(edge_type)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [
                GraphEdge(
                    edge_id=r["edge_id"],
                    workspace_id=r["workspace_id"],
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    edge_type=r["edge_type"],
                    confidence=float(r["confidence"]),
                    evidence_ids=json.loads(r["evidence_ids"]),
                    properties=json.loads(r["properties"]),
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    def get_neighbors(
        self,
        node_id: str,
        workspace_id: str,
        max_depth: int = 1,
        edge_type: Optional[str] = None
    ) -> List[str]:
        """
        Traverses outgoing and incoming relationships up to max_depth hops using SQLite Recursive CTE.
        """
        if max_depth < 1:
            return []
            
        edge_clause = "AND edge_type = ?" if edge_type else ""
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if edge_type:
                sql = f"""
                    WITH RECURSIVE traverse(curr_node, depth) AS (
                        SELECT target_id, 1 FROM graph_edges WHERE workspace_id = ? AND source_id = ? {edge_clause}
                        UNION
                        SELECT e.target_id, t.depth + 1
                        FROM graph_edges e
                        JOIN traverse t ON e.source_id = t.curr_node
                        WHERE e.workspace_id = ? AND t.depth < ? {edge_clause}
                    )
                    SELECT DISTINCT curr_node FROM traverse WHERE curr_node != ?
                """
                params = [workspace_id, node_id, edge_type, workspace_id, max_depth, edge_type, node_id]
            else:
                sql = f"""
                    WITH RECURSIVE traverse(curr_node, depth) AS (
                        SELECT target_id, 1 FROM graph_edges WHERE workspace_id = ? AND source_id = ?
                        UNION
                        SELECT e.target_id, t.depth + 1
                        FROM graph_edges e
                        JOIN traverse t ON e.source_id = t.curr_node
                        WHERE e.workspace_id = ? AND t.depth < ?
                    )
                    SELECT DISTINCT curr_node FROM traverse WHERE curr_node != ?
                """
                params = [workspace_id, node_id, workspace_id, max_depth, node_id]
                
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [r["curr_node"] for r in rows]

    def find_paths(
        self,
        source_id: str,
        target_id: str,
        workspace_id: str,
        max_depth: int = 4
    ) -> List[List[str]]:
        """
        Finds directed paths between source_id and target_id within workspace_id up to max_depth.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            sql = """
                WITH RECURSIVE search_paths(curr_node, path_str, depth) AS (
                    SELECT target_id, source_id || '->' || target_id, 1
                    FROM graph_edges
                    WHERE workspace_id = ? AND source_id = ?
                    UNION ALL
                    SELECT e.target_id, sp.path_str || '->' || e.target_id, sp.depth + 1
                    FROM graph_edges e
                    JOIN search_paths sp ON e.source_id = sp.curr_node
                    WHERE e.workspace_id = ? AND sp.depth < ? AND instr(sp.path_str, e.target_id) = 0
                )
                SELECT path_str FROM search_paths WHERE curr_node = ?
            """
            cursor.execute(sql, (workspace_id, source_id, workspace_id, max_depth, target_id))
            rows = cursor.fetchall()
            paths = []
            for r in rows:
                p = r["path_str"].split("->")
                paths.append(p)
            return paths

    def export_subgraph(
        self,
        workspace_id: str,
        seed_node_ids: List[str],
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """
        Extracts sub-graph surrounding seed_node_ids within max_depth hops.
        """
        collected_nodes = set(seed_node_ids)
        for seed in seed_node_ids:
            neighbors = self.get_neighbors(seed, workspace_id, max_depth=max_depth)
            collected_nodes.update(neighbors)

        nodes = []
        for nid in collected_nodes:
            n = self.get_node(nid, workspace_id)
            if n:
                nodes.append({
                    "node_id": n.node_id,
                    "name": n.name,
                    "entity_type": n.entity_type,
                    "properties": n.properties
                })

        edges = []
        for nid in collected_nodes:
            out_edges = self.get_edges(workspace_id=workspace_id, source_id=nid)
            for e in out_edges:
                if e.target_id in collected_nodes:
                    edges.append({
                        "edge_id": e.edge_id,
                        "source_id": e.source_id,
                        "target_id": e.target_id,
                        "edge_type": e.edge_type,
                        "confidence": e.confidence,
                        "evidence_ids": e.evidence_ids,
                        "properties": e.properties
                    })

        return {
            "workspace_id": workspace_id,
            "nodes": nodes,
            "edges": edges
        }
