# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/load.py
==========================
Loading stage: the single point that calls the Module 7 write contract.

For each chunk that passes the quality gates, load.py:

1. Runs the write-path guardrail (anonymize_pii / anonymize_metadata from
   module7/memory/guardrails.py), so pipeline-sourced data is anonymized
   exactly like agent-authored memory (v5 Section 7.1).
2. Stamps the full v5 Appendix B lineage metadata plus the Confluent
   (topic, offset) and Databricks (Delta version, Unity Catalog lineage id)
   provenance anchors and the access-control fields.
3. Embeds via the Module 7 EmbeddingService (Titan v2, 1024-dim).
4. Upserts into MongoStore with memory_type="consolidated" and a corpus
   metadata field; the content-derived doc_id makes re-runs idempotent
   (v5 Section 3.3 incremental refresh).
5. Registers the chunk in the lineage registry for provenance queries.

Module 9 never edits Module 7: it reuses the existing memory contracts.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from module9.config.corpora import CorpusSpec, get_corpus
from module9.ingestion.chunk import Chunk, chunk_record
from module9.ingestion.delta_writer import DeltaWriteResult
from module9.ingestion.embed import embed_chunk
from module9.ingestion.lineage import get_registry
from module9.ingestion.quality import (
    VERDICT_PASS,
    DedupIndex,
    get_dedup_index,
    run_quality_gates,
)
from module9.ingestion.stream_consumer import ConsumedEvent

try:
    from module7.memory.guardrails import anonymize_metadata, anonymize_pii
    from module7.memory.mongo_store import MongoStore
except ImportError:  # standalone module9 checkout
    from module9.mock.module7_contract import (
        MongoStore,
        anonymize_metadata,
        anonymize_pii,
    )

# Decision from the design blueprint (Section F.1): reuse the existing
# "consolidated" memory type and distinguish pipeline-authored knowledge
# with the corpus metadata field, so VALID_MEMORY_TYPES in Module 7 is
# never edited.
MEMORY_TYPE = "consolidated"

EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"


@lru_cache(maxsize=1)
def get_mongo_store() -> MongoStore:
    """Shared MongoStore instance for the loading and retrieval paths.

    Caching matters in mock mode: each MongoStore() wraps its own
    in-memory MockMongo, so writers and readers must share one instance.
    Tests clear this via get_mongo_store.cache_clear().
    """
    return MongoStore()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stable_doc_id(content: str, corpus: str) -> str:
    """Content-derived doc id, mirroring module7 _stable_id semantics.

    The digest is computed over memory_type:content exactly like Module 7's
    _stable_id, with a kb- prefix and corpus tag so pipeline-authored
    documents are recognizable at a glance.
    """
    digest = hashlib.sha256(f"{MEMORY_TYPE}:{content}".encode()).hexdigest()[:32]
    return f"kb-{corpus[:3]}-{digest}"


def build_chunk_metadata(
    chunk: Chunk,
    spec: CorpusSpec,
    *,
    pipeline_run_id: str,
    chunk_hash: str,
    source_uri: str,
    source_type: str,
    source_modified: str,
    consumed: ConsumedEvent | None = None,
    delta: DeltaWriteResult | None = None,
    ingested_at: str | None = None,
) -> dict:
    """Assemble the full Appendix B lineage schema plus the partner
    provenance anchors and access-control fields (design Section F.4).

    ingested_at defaults to the current time; the seed loader overrides it
    to simulate ingest runs that happened in the past.
    """
    metadata = {
        # --- v5 Appendix B lineage schema ---
        "source_uri": source_uri,
        "source_type": source_type,
        "source_modified": source_modified,
        "ingested_at": ingested_at or _now(),
        "pipeline_run_id": pipeline_run_id,
        "content_hash": chunk_hash,
        "embedding_model": EMBEDDING_MODEL_ID,
        "chunking_strategy": chunk.chunking_strategy,
        "chunk_index": chunk.chunk_index,
        "chunk_count": chunk.chunk_count,
        "parent_chunk_id": chunk.parent_chunk_id,
        "domain": spec.name,
        "access_level": spec.access_level,
        "allowed_agent_roles": list(spec.allowed_agent_roles),
        "is_deprecated": False,
        "deprecated_at": None,
        # --- access-control extension (Module 8 seam) ---
        "agent_scope": spec.agent_scope,
        "owner_team": "platform-sre",
        # --- Databricks / Unity Catalog lineage anchors ---
        "delta_table": delta.silver_table if delta else None,
        "delta_version": delta.silver_version if delta else None,
        "unity_catalog_lineage_id": (
            delta.unity_catalog_lineage_id if delta else None
        ),
        "unity_catalog_lineage_status": (
            delta.unity_catalog_lineage_status if delta else None
        ),
        # --- Confluent anchor ---
        "kafka_topic": consumed.topic if consumed else None,
        "kafka_partition": consumed.partition if consumed else None,
        "kafka_offset": consumed.offset if consumed else None,
        # --- cross-module provenance (module7 mock convention) ---
        "corpus": spec.name,
        "source_module": "module9",
        "timestamp": source_modified or _now(),
    }
    return metadata


@dataclass
class LoadResult:
    """Outcome of loading one chunk."""

    action: str  # stored | rejected | skipped_duplicate
    doc_id: str | None
    quality_checks: list[dict]
    metadata: dict | None = None


def load_chunk(
    chunk: Chunk,
    spec: CorpusSpec,
    *,
    pipeline_run_id: str,
    source_uri: str,
    source_type: str,
    source_modified: str,
    consumed: ConsumedEvent | None = None,
    delta: DeltaWriteResult | None = None,
    dedup_index: DedupIndex | None = None,
    mongo: MongoStore | None = None,
    ingested_at: str | None = None,
) -> LoadResult:
    """Gate, anonymize, embed, and load one chunk into the knowledge base."""
    dedup_index = dedup_index if dedup_index is not None else get_dedup_index()

    # Write-path guardrail first, so the hash and the stored content agree
    # and raw PII never reaches any downstream stage (v5 Section 7.1).
    content = anonymize_pii(chunk.content)

    report = run_quality_gates(content, dedup_index)
    if report.verdict != VERDICT_PASS:
        action = (
            "skipped_duplicate"
            if report.verdict == "skip_duplicate"
            else "rejected"
        )
        return LoadResult(
            action=action,
            doc_id=dedup_index.doc_id_for(report.content_hash),
            quality_checks=report.checks,
        )

    metadata = build_chunk_metadata(
        chunk,
        spec,
        pipeline_run_id=pipeline_run_id,
        chunk_hash=report.content_hash,
        source_uri=source_uri,
        source_type=source_type,
        source_modified=source_modified,
        consumed=consumed,
        delta=delta,
        ingested_at=ingested_at,
    )
    metadata = anonymize_metadata(metadata)

    doc_id = stable_doc_id(content, spec.name)

    # The sink owns storage. Where it embeds internally (a Bedrock managed
    # knowledge base), the metadata records that rather than claiming a
    # Titan call this pipeline did not make.
    from module9.ingestion.kb_sink import resolve_sink

    sink = resolve_sink()
    sink_info = sink.info()
    metadata["embedding_model"] = sink_info.embedding_model
    metadata["knowledge_sink"] = sink_info.backend

    if mongo is not None:  # explicit store injection, used by tests
        embedding = embed_chunk(content)
        mongo.upsert(doc_id, embedding, MEMORY_TYPE, content, metadata)
    else:
        sink.upsert_chunk(doc_id, content, metadata)

    dedup_index.record(report.content_hash, doc_id)
    get_registry().register_chunk(doc_id, metadata)

    return LoadResult(
        action="stored",
        doc_id=doc_id,
        quality_checks=report.checks,
        metadata=metadata,
    )


def load_seed_corpora(pipeline_run_id: str = "run-seed") -> list[LoadResult]:
    """Load the bundled per-corpus seed documents (idempotent).

    Seeds flow through the same chunk, gate, anonymize, embed, and load
    stages as streamed events; they carry document source anchors instead
    of Kafka and Delta anchors. Each seed's ingested_at is back-dated to
    its source_modified time, simulating the earlier pipeline runs that
    would have loaded it, so freshness verdicts reflect the seed's age.
    """
    from module9.mock.seed_corpora_data import SEED_DOCS

    results: list[LoadResult] = []
    for doc in SEED_DOCS:
        spec = get_corpus(doc["corpus"])
        for chunk in chunk_record(doc["content"], spec.name):
            results.append(
                load_chunk(
                    chunk,
                    spec,
                    pipeline_run_id=pipeline_run_id,
                    source_uri=doc["source_uri"],
                    source_type=doc["source_type"],
                    source_modified=doc["source_modified"],
                    ingested_at=doc["source_modified"],
                )
            )
    return results
