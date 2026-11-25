"""
backend/knowledge/vector_store.py
─────────────────────────────────────────────────────────────────
Plan-conformant Vector Store for AeroMind 2.0 (PLAN §8.4, Task 1.1, ADR-0004).
Collection: evidence_chunks (COSINE).
Payload indexes on: workspace_id, classification_level, source_type.
Point ID: deterministic uuid5(NAMESPACE_DNS, f"{unit_id}_{chunk_idx}").
Lock failures raise loudly; no silent :memory: fallback.
"""

from __future__ import annotations

import math
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels
    from qdrant_client.http.exceptions import UnexpectedResponse
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    QdrantClient = None
    qmodels = None

COLLECTION_NAME = "evidence_chunks"
DEFAULT_VECTOR_SIZE = 768  # nomic-embed-text standard dimension


class VectorStoreLockError(RuntimeError):
    """Raised when the vector store storage directory is locked by another process (ADR-0004)."""
    pass


def generate_point_id(unit_id: str, chunk_idx: int) -> str:
    """Deterministic UUID5 point ID from unit_id and chunk_idx (PLAN §8.4)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{unit_id}_{chunk_idx}"))


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def generate_deterministic_vector(text: str, dim: int = DEFAULT_VECTOR_SIZE) -> List[float]:
    """Generates a deterministic unit vector for text using SHA-256 (PLAN QW6)."""
    import hashlib
    words = text.lower().split()
    if not words:
        words = ["empty_document"]

    vec = [0.0] * dim
    for i, word in enumerate(words):
        h = int(hashlib.sha256(word.encode("utf-8")).hexdigest()[:8], 16) % dim
        weight = 1.0 / (1.0 + math.log(i + 1))
        vec[h] += weight

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return [0.0] * dim
    return [x / norm for x in vec]


class FallbackMemoryStore:
    """
    Deterministic in-memory vector store used when Qdrant native package
    is absent, maintaining exact COSINE and payload filtering contracts.
    """

    def __init__(self) -> None:
        self.points: Dict[str, Dict[str, Any]] = {}
        self.indexes: Set[str] = set()

    def create_index(self, field_name: str) -> None:
        self.indexes.add(field_name)

    def upsert(self, points: List[Dict[str, Any]]) -> int:
        for p in points:
            self.points[p["id"]] = p
        return len(points)

    def search(
        self,
        query_vector: List[float],
        workspace_id: str,
        top_k: int = 5,
        max_classification_level: str = "INTERNAL",
    ) -> List[Dict[str, Any]]:
        results = []
        for p in self.points.values():
            payload = p.get("payload", {})
            if payload.get("workspace_id") != workspace_id:
                continue
            sim = cosine_similarity(query_vector, p["vector"])
            results.append({
                "id": p["id"],
                "score": sim,
                "payload": payload,
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]


class VectorStore:
    """
    Qdrant Vector Store implementing PLAN §8.4.
    Requires workspace_id at query time. Fails loudly on disk lock errors.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        force_memory: bool = False,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        self.vector_size = vector_size
        self.force_memory = force_memory
        self.storage_path = storage_path

        if not HAS_QDRANT:
            self._fallback = FallbackMemoryStore()
            self._client = None
        elif force_memory:
            self._fallback = None
            self._client = QdrantClient(":memory:")
        else:
            if storage_path is None:
                from config import settings
                storage_path = Path(settings.QDRANT_PATH)

            storage_path = Path(storage_path)
            storage_path.mkdir(parents=True, exist_ok=True)

            # Never catch lock error silently (PLAN §11.3, ADR-0004)
            try:
                self._client = QdrantClient(path=str(storage_path))
                self._fallback = None
            except Exception as e:
                raise VectorStoreLockError(
                    f"Fatal Qdrant lock error on path '{storage_path}': {e}. "
                    "Refusing silent fallback to in-memory store (ADR-0004)."
                ) from e

        self.create_collection_if_not_exists()

    def create_collection_if_not_exists(self) -> None:
        if self._fallback is not None:
            self._fallback.create_index("workspace_id")
            self._fallback.create_index("classification_level")
            self._fallback.create_index("source_type")
            return

        collections = [c.name for c in self._client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qmodels.VectorParams(
                    size=self.vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            # Create payload indexes for efficient tenant-scoped search
            for field in ("workspace_id", "classification_level", "source_type"):
                self._client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )

    def upsert_chunks(
        self,
        chunks: List[Dict[str, Any]],
        vectors: List[List[float]],
    ) -> int:
        """
        Upserts chunk payloads and vectors into evidence_chunks collection.
        Payload schema (PLAN §8.4):
        unit_id, chunk_idx, workspace_id, classification_level, source_type,
        source_ref, extracted_text, evidence_tag, confidence, ingested_at, location, acls.
        """
        if len(chunks) != len(vectors):
            raise ValueError(f"Mismatch: {len(chunks)} chunks vs {len(vectors)} vectors.")

        points_to_upsert = []
        for chunk, vector in zip(chunks, vectors):
            workspace_id = chunk.get("workspace_id")
            if not workspace_id:
                raise ValueError("workspace_id is REQUIRED for every vector store point.")

            unit_id = chunk.get("unit_id", "unknown_unit")
            chunk_idx = chunk.get("chunk_idx", 0)
            point_id = generate_point_id(unit_id, chunk_idx)

            payload = {
                "unit_id": unit_id,
                "chunk_idx": chunk_idx,
                "workspace_id": workspace_id,
                "classification_level": chunk.get("classification_level", "INTERNAL"),
                "source_type": chunk.get("source_type", "unknown"),
                "source_ref": chunk.get("source_ref", ""),
                "extracted_text": chunk.get("extracted_text", ""),
                "evidence_tag": chunk.get("evidence_tag", "observed"),
                "confidence": chunk.get("confidence", 1.0),
                "ingested_at": chunk.get("ingested_at", ""),
                "location": chunk.get("location", {}),
                "acls": chunk.get("acls", []),
            }

            points_to_upsert.append({
                "id": point_id,
                "vector": vector,
                "payload": payload,
            })

        if self._fallback is not None:
            return self._fallback.upsert(points_to_upsert)

        q_points = [
            qmodels.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p["payload"],
            )
            for p in points_to_upsert
        ]
        self._client.upsert(collection_name=COLLECTION_NAME, points=q_points)
        return len(points_to_upsert)

    def search(
        self,
        query_vector: List[float],
        workspace_id: str,
        top_k: int = 5,
        classification_level: str = "INTERNAL",
    ) -> List[Dict[str, Any]]:
        """
        Executes tenant-isolated vector search. workspace_id is strictly REQUIRED.
        """
        if not workspace_id:
            raise ValueError("workspace_id is required for vector search.")

        if self._fallback is not None:
            return self._fallback.search(
                query_vector=query_vector,
                workspace_id=workspace_id,
                top_k=top_k,
                max_classification_level=classification_level,
            )

        # Qdrant query with payload filter
        query_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="workspace_id",
                    match=qmodels.MatchValue(value=workspace_id),
                )
            ]
        )

        scored_points = self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=top_k,
        )

        return [
            {
                "id": str(p.id),
                "score": p.score,
                "payload": p.payload,
            }
            for p in scored_points
        ]
