# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/quality.py
=============================
Data quality gates that run before embedding (v5 Sections 6.1 and 6.2,
Appendix C):

- non-empty content
- minimum token threshold (50 tokens)
- structural validation (real prose, not stray markup or braces)
- deduplication by SHA-256 content hash, which also powers incremental
  hash-based refresh (v5 Section 3.3): an unchanged record is skipped,
  not re-embedded
- embedding dimension check (Titan v2 vectors must be exactly 1024)

The same Python assertions run in mock and live mode. On the live path
Databricks Delta Live Tables expectations enforce schema and null checks
at the lakehouse layer as well; these gates are the pipeline's own final
line of defense before the knowledge base.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

MIN_TOKENS = 50
EXPECTED_EMBEDDING_DIM = 1024

VERDICT_PASS = "pass"
VERDICT_REJECT = "reject"
VERDICT_SKIP_DUPLICATE = "skip_duplicate"


def content_hash(text: str) -> str:
    """SHA-256 hash of the chunk text, in the Appendix B sha256: format."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Cheap token estimate: the larger of word count and chars over 4."""
    if not text:
        return 0
    return max(len(text.split()), len(text) // 4)


class DedupIndex:
    """In-memory content-hash store for deduplication and incremental
    refresh (v5 Section 6.1). The live analogue is a DynamoDB hash table
    keyed by content hash; the interface is identical."""

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}  # content_hash -> doc_id

    def seen(self, chunk_hash: str) -> bool:
        return chunk_hash in self._hashes

    def record(self, chunk_hash: str, doc_id: str) -> None:
        self._hashes[chunk_hash] = doc_id

    def doc_id_for(self, chunk_hash: str) -> str | None:
        return self._hashes.get(chunk_hash)

    def __len__(self) -> int:
        return len(self._hashes)

    def clear(self) -> None:
        self._hashes.clear()


# Shared index so repeated pipeline runs in one process dedup against each
# other. Tests reset it via reset_dedup_index().
_DEDUP_INDEX = DedupIndex()


def get_dedup_index() -> DedupIndex:
    return _DEDUP_INDEX


def reset_dedup_index() -> None:
    _DEDUP_INDEX.clear()


@dataclass
class QualityReport:
    """Outcome of the quality gates for one chunk."""

    verdict: str  # pass | reject | skip_duplicate
    content_hash: str
    checks: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == VERDICT_PASS


def run_quality_gates(
    text: str,
    dedup_index: DedupIndex | None = None,
) -> QualityReport:
    """Run the pre-embedding gates on one chunk of text.

    Returns a QualityReport whose verdict is pass, reject (bad content,
    never embed), or skip_duplicate (identical content already loaded, the
    incremental-refresh skip).
    """
    dedup_index = dedup_index if dedup_index is not None else _DEDUP_INDEX
    chunk_hash = content_hash(text or "")
    checks: list[dict] = []

    non_empty = bool(text and text.strip())
    checks.append(
        {
            "check": "non_empty",
            "passed": non_empty,
            "detail": "content present" if non_empty else "content is empty or null",
        }
    )

    tokens = estimate_tokens(text or "")
    min_tokens_ok = tokens >= MIN_TOKENS
    checks.append(
        {
            "check": "min_tokens",
            "passed": min_tokens_ok,
            "detail": f"estimated {tokens} tokens (minimum {MIN_TOKENS})",
        }
    )

    letters = sum(ch.isalpha() for ch in (text or ""))
    structural_ok = non_empty and letters >= len(text or "") * 0.4
    checks.append(
        {
            "check": "structural",
            "passed": structural_ok,
            "detail": (
                "content is prose-like"
                if structural_ok
                else "content looks like markup or noise, not prose"
            ),
        }
    )

    if not (non_empty and min_tokens_ok and structural_ok):
        return QualityReport(VERDICT_REJECT, chunk_hash, checks)

    duplicate = dedup_index.seen(chunk_hash)
    checks.append(
        {
            "check": "dedup",
            "passed": not duplicate,
            "detail": (
                f"duplicate of {dedup_index.doc_id_for(chunk_hash)}"
                if duplicate
                else "content hash not previously loaded"
            ),
        }
    )
    if duplicate:
        return QualityReport(VERDICT_SKIP_DUPLICATE, chunk_hash, checks)

    return QualityReport(VERDICT_PASS, chunk_hash, checks)


def validate_embedding(embedding: list[float]) -> None:
    """Reject embeddings that are not exactly 1024 dimensions."""
    if not isinstance(embedding, list) or len(embedding) != EXPECTED_EMBEDDING_DIM:
        actual = len(embedding) if isinstance(embedding, list) else type(embedding)
        raise ValueError(
            f"Embedding must be {EXPECTED_EMBEDDING_DIM} dimensions, got {actual}"
        )
