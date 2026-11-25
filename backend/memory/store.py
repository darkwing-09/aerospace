import sqlite3
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from memory.scoping import can_access

@dataclass
class MemoryEntry:
    id: str
    workspace_id: str
    key: str
    value: Any
    user_id: Optional[str] = None
    memory_type: str = "fact"
    classification_level: str = "INTERNAL"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None

class MemoryStore:
    """
    Long-term workspace-scoped persistent Memory Store (ADR-0003, PLAN §6.2).
    Enforces hard tenant isolation via workspace_id and clearance hierarchy.
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.getenv("DATA_DIR")
            if data_dir:
                base_dir = data_dir
            else:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data_repository"))
            os.makedirs(base_dir, exist_ok=True)
            db_path = os.getenv("MEMORY_DB_PATH", os.path.join(base_dir, "memory.sqlite3"))
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
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    user_id TEXT,
                    memory_type TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    classification_level TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_ws ON memory_entries(workspace_id, key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_class ON memory_entries(workspace_id, classification_level)")
            conn.commit()

    def upsert(self, entry: MemoryEntry):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_entries (id, workspace_id, user_id, memory_type, key, value, classification_level, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    memory_type = excluded.memory_type,
                    key = excluded.key,
                    value = excluded.value,
                    classification_level = excluded.classification_level,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
            """, (
                entry.id,
                entry.workspace_id,
                entry.user_id,
                entry.memory_type,
                entry.key,
                json.dumps(entry.value),
                entry.classification_level,
                entry.created_at,
                entry.expires_at
            ))
            conn.commit()

    def get(self, key: str, workspace_id: str, user_clearance: str = "INTERNAL") -> Optional[MemoryEntry]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, workspace_id, user_id, memory_type, key, value, classification_level, created_at, expires_at
                FROM memory_entries
                WHERE key = ? AND workspace_id = ?
            """, (key, workspace_id))
            row = cursor.fetchone()
            if not row:
                return None
            
            classification = row["classification_level"]
            if not can_access(user_clearance, classification):
                return None
                
            return MemoryEntry(
                id=row["id"],
                workspace_id=row["workspace_id"],
                user_id=row["user_id"],
                memory_type=row["memory_type"],
                key=row["key"],
                value=json.loads(row["value"]),
                classification_level=row["classification_level"],
                created_at=row["created_at"],
                expires_at=row["expires_at"]
            )

    def search(
        self,
        workspace_id: str,
        user_clearance: str = "INTERNAL",
        query: Optional[str] = None,
        memory_type: Optional[str] = None
    ) -> List[MemoryEntry]:
        sql = "SELECT id, workspace_id, user_id, memory_type, key, value, classification_level, created_at, expires_at FROM memory_entries WHERE workspace_id = ?"
        params: List[Any] = [workspace_id]
        
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
            
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                if not can_access(user_clearance, r["classification_level"]):
                    continue
                val_str = r["value"]
                if query:
                    # Case-insensitive substring match on key or serialized value
                    if query.lower() not in r["key"].lower() and query.lower() not in val_str.lower():
                        continue
                results.append(MemoryEntry(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    user_id=r["user_id"],
                    memory_type=r["memory_type"],
                    key=r["key"],
                    value=json.loads(val_str),
                    classification_level=r["classification_level"],
                    created_at=r["created_at"],
                    expires_at=r["expires_at"]
                ))
            return results

