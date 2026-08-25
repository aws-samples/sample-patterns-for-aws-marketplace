# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/mock/module7_contract.py
=================================
Vendored fallback for the Module 7 seam contracts.

Module 9 normally imports MongoStore, Neo4jStore, EmbeddingService, and the
write-path guardrails from module7. If a newcomer checked out module9/ on
its own, those imports fail; this file bundles a minimal in-memory copy of
the exact upsert/vector_search/create_relationship/embed contracts so the
demo degrades to mock behavior instead of hard-failing.

Inside the monorepo this module is never used: ingestion code always
prefers the real Module 7 imports.
"""
from __future__ import annotations

import re

EMBEDDING_DIM = 1024

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_AWS_ACCESS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s])\d{3}[-.\s]\d{4}\b")


def anonymize_pii(text: str) -> str:
    """Minimal copy of module7.memory.guardrails.anonymize_pii."""
    if not isinstance(text, str) or not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _AWS_ACCESS_KEY_RE.sub("[REDACTED_AWS_ACCESS_KEY]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def anonymize_metadata(metadata: dict | None) -> dict:
    """Minimal copy of module7.memory.guardrails.anonymize_metadata."""
    if not metadata:
        return metadata or {}
    return {
        k: anonymize_pii(v) if isinstance(v, str) else v
        for k, v in metadata.items()
    }


class EmbeddingService:
    """Deterministic pseudo-embedding with the Module 7 embed() contract."""

    def embed(self, text: str) -> list[float]:
        if not text:
            raise ValueError("text must be 1-8192 characters, got 0")
        seed = sum(text.encode("utf-8")) % 1000 / 1000.0
        return [seed] * EMBEDDING_DIM


_MONGO_DOCS: dict[str, dict] = {}
_NEO4J_RELS: list[dict] = []


class MongoStore:
    """In-memory copy of the MongoStore upsert/vector_search contract."""

    def upsert(
        self,
        doc_id: str,
        embedding: list[float],
        memory_type: str,
        content: str,
        metadata: dict,
    ) -> str:
        _MONGO_DOCS[doc_id] = {
            "_id": doc_id,
            "memory_type": memory_type,
            "content": content,
            "metadata": dict(metadata),
        }
        return f"Stored memory {doc_id} (type={memory_type})"

    def vector_search(
        self,
        embedding: list[float],
        memory_type: str | None = None,
        filter_dict: dict | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        results = []
        for doc in _MONGO_DOCS.values():
            if memory_type and doc["memory_type"] != memory_type:
                continue
            meta = doc["metadata"]
            if filter_dict and not all(
                meta.get(k) == v for k, v in filter_dict.items()
            ):
                continue
            results.append(
                {
                    "id": doc["_id"],
                    "score": 0.95,
                    "content": doc["content"],
                    "memory_type": doc["memory_type"],
                    "metadata": dict(meta),
                }
            )
        return results[:top_k]


class Neo4jStore:
    """In-memory copy of the Neo4jStore create_relationship contract."""

    def create_relationship(
        self,
        source_name: str,
        source_type: str,
        relationship: str,
        target_name: str,
        target_type: str,
        properties: dict | None = None,
    ) -> str:
        _NEO4J_RELS.append(
            {
                "source": source_name,
                "source_type": source_type,
                "relationship": relationship,
                "target": target_name,
                "target_type": target_type,
                "properties": properties or {},
            }
        )
        return f"Created {source_name} -[{relationship}]-> {target_name}"
