# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/lineage.py
=============================
Lineage capture and provenance queries (v5 Section 5).

Two complementary lineage layers:

1. **Graph layer (Neo4j, Module 7 Seam C).** The pipeline writes the
   Source -> Dataset -> Corpus -> Agent path into the Module 7 Neo4jStore
   with FEEDS / POPULATES / SERVES relationships, so chunk-level lineage
   lives in the same graph as the Module 7 relationship memory.
2. **Chunk registry.** Every loaded chunk's full Appendix B metadata is
   registered here, keyed by doc_id. get_provenance(doc_id) joins the
   registry with the graph path to answer "why did the agent say this?"
   all the way back to the Kafka offset and Delta table version.

The Unity Catalog table-level lineage (bronze -> silver) is captured by
Databricks automatically; the pipeline reads it in delta_writer.py and the
lineage id is stamped on each chunk, joining the two systems.
"""
from __future__ import annotations

from functools import lru_cache

try:
    from module7.memory.neo4j_store import Neo4jStore
except ImportError:  # standalone module9 checkout
    from module9.mock.module7_contract import Neo4jStore

AGENT_NODE = "DevOpsCompanion"


class LineageRegistry:
    """Process-local record of loaded chunks and graph edges."""

    def __init__(self) -> None:
        self.chunks: dict[str, dict] = {}  # doc_id -> chunk metadata
        self.edges: list[dict] = []  # graph edges written this process

    def register_chunk(self, doc_id: str, metadata: dict) -> None:
        self.chunks[doc_id] = dict(metadata)

    def register_edge(self, edge: dict) -> None:
        if edge not in self.edges:
            self.edges.append(edge)

    def chunks_for_corpus(self, corpus: str) -> list[tuple[str, dict]]:
        return [
            (doc_id, meta)
            for doc_id, meta in self.chunks.items()
            if meta.get("corpus") == corpus
        ]

    def clear(self) -> None:
        self.chunks.clear()
        self.edges.clear()


_REGISTRY = LineageRegistry()


def get_registry() -> LineageRegistry:
    return _REGISTRY


def reset_lineage() -> None:
    """Clear the registry and the cached Neo4j store (test isolation)."""
    _REGISTRY.clear()
    _get_neo4j.cache_clear()


@lru_cache(maxsize=1)
def _get_neo4j() -> Neo4jStore:
    return Neo4jStore()


def ensure_lineage_graph(
    source_uri: str,
    dataset: str,
    corpus: str,
    *,
    delta_version: int | None = None,
    unity_catalog_lineage_id: str | None = None,
    pipeline_run_id: str | None = None,
    access_level: str | None = None,
) -> list[str]:
    """Write the Source -> Dataset -> Corpus -> Agent path to Neo4j.

    MERGE semantics on the store make repeated calls idempotent. Returns
    the store's confirmation strings.
    """
    store = _get_neo4j()
    results = []

    edges = [
        {
            "source": source_uri,
            "source_type": "Source",
            "relationship": "FEEDS",
            "target": dataset,
            "target_type": "Dataset",
            "properties": {
                "delta_version": delta_version,
                "unity_catalog_lineage_id": unity_catalog_lineage_id,
            },
        },
        {
            "source": dataset,
            "source_type": "Dataset",
            "relationship": "POPULATES",
            "target": corpus,
            "target_type": "Corpus",
            "properties": {"pipeline_run_id": pipeline_run_id},
        },
        {
            "source": corpus,
            "source_type": "Corpus",
            "relationship": "SERVES",
            "target": AGENT_NODE,
            "target_type": "Agent",
            "properties": {"access_level": access_level},
        },
    ]

    for edge in edges:
        properties = {k: v for k, v in edge["properties"].items() if v is not None}
        results.append(
            store.create_relationship(
                edge["source"],
                edge["source_type"],
                edge["relationship"],
                edge["target"],
                edge["target_type"],
                properties,
            )
        )
        _REGISTRY.register_edge(
            {
                "source": edge["source"],
                "relationship": edge["relationship"],
                "target": edge["target"],
                "properties": properties,
            }
        )

    return results


def get_lineage(corpus: str) -> dict:
    """Corpus-level lineage view: graph edges plus chunk counts.

    Walks the chain outward from the corpus node: the POPULATES and SERVES
    edges touch the corpus directly, and the FEEDS edges are included when
    they feed a dataset that populates the corpus.
    """
    direct = [
        e for e in _REGISTRY.edges if corpus in (e["source"], e["target"])
    ]
    datasets = {e["source"] for e in direct if e["relationship"] == "POPULATES"}
    upstream = [
        e
        for e in _REGISTRY.edges
        if e["relationship"] == "FEEDS" and e["target"] in datasets
    ]
    edges = upstream + direct
    chunks = _REGISTRY.chunks_for_corpus(corpus)
    return {
        "corpus": corpus,
        "graph_edges": edges,
        "chunk_count": len(chunks),
        "doc_ids": [doc_id for doc_id, _ in chunks],
    }


def get_provenance(doc_id: str) -> dict:
    """Trace one loaded chunk back to its origin.

    Answers the v5 Section 5 lineage question "which source produced this
    fact?" by joining the chunk's Appendix B metadata (Kafka offset, Delta
    version, Unity Catalog lineage id) with the graph path.
    """
    metadata = _REGISTRY.chunks.get(doc_id)
    if metadata is None:
        return {
            "found": False,
            "doc_id": doc_id,
            "error": f"No lineage record for doc_id {doc_id!r}",
        }

    corpus = metadata.get("corpus", "")
    graph_path = [
        AGENT_NODE,
        "<-SERVES-",
        corpus,
        "<-POPULATES-",
        metadata.get("delta_table") or "(direct load)",
        "<-FEEDS-",
        metadata.get("source_uri", ""),
    ]
    return {
        "found": True,
        "doc_id": doc_id,
        "corpus": corpus,
        "graph_path": graph_path,
        "source": {
            "source_uri": metadata.get("source_uri"),
            "source_type": metadata.get("source_type"),
            "source_modified": metadata.get("source_modified"),
        },
        "confluent": {
            "kafka_topic": metadata.get("kafka_topic"),
            "kafka_partition": metadata.get("kafka_partition"),
            "kafka_offset": metadata.get("kafka_offset"),
        },
        "databricks": {
            "delta_table": metadata.get("delta_table"),
            "delta_version": metadata.get("delta_version"),
            "unity_catalog_lineage_id": metadata.get("unity_catalog_lineage_id"),
            "unity_catalog_lineage_status": metadata.get(
                "unity_catalog_lineage_status"
            ),
        },
        "pipeline": {
            "pipeline_run_id": metadata.get("pipeline_run_id"),
            "ingested_at": metadata.get("ingested_at"),
            "content_hash": metadata.get("content_hash"),
            "embedding_model": metadata.get("embedding_model"),
            "chunking_strategy": metadata.get("chunking_strategy"),
        },
        "access": {
            "access_level": metadata.get("access_level"),
            "allowed_agent_roles": metadata.get("allowed_agent_roles"),
            "agent_scope": metadata.get("agent_scope"),
        },
    }
