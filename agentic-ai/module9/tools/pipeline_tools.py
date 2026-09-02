# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/tools/pipeline_tools.py
================================
Six LangGraph @tool definitions for the pipeline-aware DevOps Companion,
plus the governed recall factory that binds retrieval to a fixed agent
role.

Every tool returns a JSON string envelope with tool, timestamp,
mock_pipeline, and data fields, following the Module 1 tool envelope
convention. Store instances are lazily initialized and cached via
@lru_cache; tests clear the cache through _get_stores.cache_clear().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache

from langchain_core.tools import tool

from module9.config.corpora import CORPORA, VALID_CORPUS_NAMES
from module9.config.settings import is_mock_pipeline
from module9.identity import (
    Auth0Error,
    authorize_retrieval,
    compile_retrieval_filter,
    get_current_role,
)
from module9.ingestion import freshness as freshness_mod
from module9.ingestion import lineage as lineage_mod
from module9.ingestion.pipeline_run import run_pipeline
from module9.ingestion.quality import get_dedup_index, run_quality_gates

try:
    from module7.memory.embeddings import EmbeddingService
except ImportError:  # standalone module9 checkout
    from module9.mock.module7_contract import EmbeddingService

from module9.ingestion.load import get_mongo_store


@lru_cache(maxsize=1)
def _get_stores():
    """Lazily initialize and cache the knowledge base stores.

    Reuses the loader's shared MongoStore so reads see the writes in mock
    mode (one MockMongo instance per process).
    """
    return get_mongo_store(), EmbeddingService()


def _wrap(tool_name: str, data) -> str:
    """JSON envelope shared by all Module 9 tools."""
    return json.dumps(
        {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "mock_pipeline": is_mock_pipeline(),
            "data": data,
        },
        default=str,
    )


# ---------------------------------------------------------------------------
# The six pipeline tools
# ---------------------------------------------------------------------------

@tool
def run_ingestion(corpus: str = "history", max_events: int = 5) -> str:
    """Run the ingestion pipeline for events waiting on the devops-events
    stream: consume from Confluent, land in Databricks Delta, chunk,
    validate, embed, and load into the knowledge base with lineage.

    corpus: target corpus, normally 'history' (the streamed corpus).
    max_events: bounded consumption window (1-50).
    Returns the pipeline run summary as JSON.
    """
    max_events = max(1, min(int(max_events), 50))
    if corpus not in VALID_CORPUS_NAMES:
        return _wrap(
            "run_ingestion",
            {"error": f"Unknown corpus {corpus!r}. Valid: {sorted(VALID_CORPUS_NAMES)}"},
        )
    try:
        result = run_pipeline(corpus=corpus, max_events=max_events)
    except Auth0Error as exc:
        return _wrap(
            "run_ingestion", {"error": f"Authorization denied: {exc}"}
        )
    return _wrap("run_ingestion", result.summary())


@tool
def check_freshness(corpus: str = "all") -> str:
    """Check whether a corpus meets its freshness SLA.

    corpus: 'service', 'policy', 'history', or 'all' (default) for the
    cross-corpus dashboard view.
    Returns per-corpus status (fresh, stale, or empty), newest chunk age,
    SLA, and refresh strategy as JSON.
    """
    if corpus == "all":
        return _wrap("check_freshness", freshness_mod.check_all_corpora())
    if corpus not in VALID_CORPUS_NAMES:
        return _wrap(
            "check_freshness",
            {"error": f"Unknown corpus {corpus!r}. Valid: {sorted(VALID_CORPUS_NAMES)} or 'all'"},
        )
    return _wrap("check_freshness", freshness_mod.check_freshness(corpus))


@tool
def get_provenance(doc_id: str) -> str:
    """Trace a knowledge base document back to its origin: the lineage
    graph path, source URI, Kafka topic and offset, Delta table and
    version, Unity Catalog lineage id, pipeline run, and access stamps.

    doc_id: the document id from a retrieval result (metadata 'id' field).
    Returns the provenance chain as JSON.
    """
    return _wrap("get_provenance", lineage_mod.get_provenance(doc_id))


@tool
def assert_quality(content: str = "") -> str:
    """Run the pre-embedding data quality gates.

    With content: evaluates that text against the gates (non-empty, 50-token
    minimum, structural validation, dedup by content hash) and reports each
    check without loading anything.
    Without content: reports the dedup index size, the gate configuration,
    and where the gates run in the pipeline.
    Returns the quality report as JSON.
    """
    if content:
        report = run_quality_gates(content, get_dedup_index())
        return _wrap(
            "assert_quality",
            {
                "verdict": report.verdict,
                "content_hash": report.content_hash,
                "checks": report.checks,
            },
        )
    return _wrap(
        "assert_quality",
        {
            "gates": [
                "non_empty",
                "min_tokens (50)",
                "structural",
                "dedup by SHA-256 content hash",
                "embedding dimension == 1024",
            ],
            "dedup_index_size": len(get_dedup_index()),
            "stage": "runs after chunking, before embedding",
        },
    )


@tool
def list_corpora() -> str:
    """List the three knowledge corpora with their pipeline design: chunking
    strategy, freshness SLA, access level, allowed agent roles, and current
    chunk count.

    Returns the corpus catalog as JSON.
    """
    registry = lineage_mod.get_registry()
    catalog = []
    for name, spec in CORPORA.items():
        catalog.append(
            {
                "corpus": name,
                "description": spec.description,
                "chunking_strategy": spec.chunking_strategy,
                "freshness_sla_hours": spec.freshness_sla_hours,
                "access_level": spec.access_level,
                "allowed_agent_roles": list(spec.allowed_agent_roles),
                "agent_scope": spec.agent_scope,
                "chunk_count": len(registry.chunks_for_corpus(name)),
            }
        )
    return _wrap("list_corpora", catalog)


@tool
def explain_staleness(corpus: str = "history") -> str:
    """Explain a corpus's freshness state in plain language: how old its
    newest chunk is, what the SLA allows, which refresh strategy applies,
    and how to interpret answers drawn from it.

    corpus: 'service', 'policy', or 'history'.
    Returns the verdict with a narrative explanation as JSON.
    """
    if corpus not in VALID_CORPUS_NAMES:
        return _wrap(
            "explain_staleness",
            {"error": f"Unknown corpus {corpus!r}. Valid: {sorted(VALID_CORPUS_NAMES)}"},
        )
    return _wrap("explain_staleness", freshness_mod.explain_staleness(corpus))


# ---------------------------------------------------------------------------
# Governed recall (row-level security at the retrieval layer)
# ---------------------------------------------------------------------------

def governed_recall(
    query: str, corpus: str = "history", top_k: int = 5, role: str | None = None
) -> dict:
    """Retrieve from a corpus under the caller's role, enforcing both
    Module 8 layers: policy authorization at the boundary, then the
    role-compiled filter_dict applied server-side of the store.

    Returns a dict (not JSON) so demo code and the tool wrapper share it.
    """
    role = role or get_current_role()
    top_k = max(1, min(int(top_k), 20))
    try:
        decision = authorize_retrieval(role, corpus)
    except Auth0Error as exc:
        return {
            "access": "denied",
            "role": role,
            "corpus": corpus,
            "reason": str(exc),
            "results": [],
        }

    filter_dict = compile_retrieval_filter(decision, corpus)
    from module9.ingestion.kb_sink import resolve_sink

    sink = resolve_sink()
    raw = sink.search(query, filter_dict=filter_dict, top_k=top_k)
    results = []
    for r in raw:
        meta = r.get("metadata", {})
        results.append(
            {
                "id": r.get("id", ""),
                "score": round(float(r.get("score", 0.0)), 4),
                "content": r.get("content", ""),
                "corpus": meta.get("corpus", ""),
                "ingested_at": meta.get("ingested_at", ""),
                "access_level": meta.get("access_level", ""),
                "kafka_offset": meta.get("kafka_offset"),
                "delta_version": meta.get("delta_version"),
            }
        )
    return {
        "access": "granted",
        "role": role,
        "corpus": corpus,
        "filter": filter_dict,
        "sink": sink.info().backend,
        "results": results,
    }


def make_governed_recall(role: str):
    """Build the agent's recall tool with the role fixed at composition
    time, so the model can never choose its own access role. The tool name
    matches Module 7's recall_semantic_memory, and the row-level-security
    filter is compiled from the role, not from model input.
    """

    @tool
    def recall_semantic_memory(
        query: str, corpus: str = "history", top_k: int = 5
    ) -> str:
        """Recall knowledge from the governed corpora using semantic search.

        corpus: 'service', 'policy', or 'history'. Retrieval is filtered by
        your assigned role's access scope inside the vector store; content
        you are not cleared for is excluded before similarity scoring.
        top_k: number of results (1-20).
        Returns matching records with provenance anchors as JSON.
        """
        return _wrap(
            "recall_semantic_memory",
            governed_recall(query, corpus=corpus, top_k=top_k, role=role),
        )

    return recall_semantic_memory


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

PIPELINE_TOOLS: dict = {
    "run_ingestion":     run_ingestion,
    "check_freshness":   check_freshness,
    "get_provenance":    get_provenance,
    "assert_quality":    assert_quality,
    "list_corpora":      list_corpora,
    "explain_staleness": explain_staleness,
}
