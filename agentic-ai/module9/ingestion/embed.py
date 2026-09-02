# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/embed.py
===========================
Embedding stage: wraps the Module 7 EmbeddingService (Amazon Titan Text
Embeddings v2, 1024-dim, via Bedrock). No new embedding code; the pipeline
produces exactly the vectors the Module 7 knowledge base already stores
(v5 Section 2.4).

Under AGENT_MOCK_MEMORY=true the Module 7 service returns a deterministic
pseudo-vector without calling Bedrock, so the pipeline runs offline.
"""
from __future__ import annotations

from functools import lru_cache

from module9.ingestion.quality import validate_embedding

try:
    from module7.memory.embeddings import EmbeddingService
except ImportError:  # standalone module9 checkout
    from module9.mock.module7_contract import EmbeddingService


@lru_cache(maxsize=1)
def _get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


def embed_chunk(text: str) -> list[float]:
    """Embed one chunk to a validated 1024-dim Titan v2 vector."""
    embedding = _get_embedding_service().embed(text)
    validate_embedding(embedding)
    return embedding
