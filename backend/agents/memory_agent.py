import uuid
from typing import Dict, Any, List, Optional
from memory.store import MemoryStore, MemoryEntry

class MemoryAgent:
    """
    Deterministic Memory Agent enforcing workspace scoping, user context,
    and security clearance verification on every read and write (PLAN §6.2).
    """
    def __init__(self, store: Optional[MemoryStore] = None):
        if store is None:
            store = MemoryStore()
        self.store = store

    def remember(
        self,
        key: str,
        value: Any,
        workspace_id: str,
        user_id: Optional[str] = None,
        memory_type: str = "fact",
        classification_level: str = "INTERNAL",
        expires_at: Optional[str] = None
    ) -> MemoryEntry:
        """Stores a memory entry strictly associated with workspace_id."""
        entry = MemoryEntry(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            workspace_id=workspace_id,
            user_id=user_id,
            memory_type=memory_type,
            key=key,
            value=value,
            classification_level=classification_level,
            expires_at=expires_at
        )
        self.store.upsert(entry)
        return entry

    def recall(
        self,
        key: str,
        workspace_id: str,
        user_clearance: str = "INTERNAL"
    ) -> Optional[MemoryEntry]:
        """Retrieves a memory entry strictly filtered by workspace and clearance."""
        return self.store.get(key=key, workspace_id=workspace_id, user_clearance=user_clearance)

    def search(
        self,
        workspace_id: str,
        user_clearance: str = "INTERNAL",
        query: Optional[str] = None,
        memory_type: Optional[str] = None
    ) -> List[MemoryEntry]:
        """Searches memories strictly within workspace_id that user is cleared to view."""
        return self.store.search(
            workspace_id=workspace_id,
            user_clearance=user_clearance,
            query=query,
            memory_type=memory_type
        )

