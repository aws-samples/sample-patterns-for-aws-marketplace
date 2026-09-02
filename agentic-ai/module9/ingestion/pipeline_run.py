# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/pipeline_run.py
==================================
Orchestrates the five pipeline stages end to end for the history corpus:

    consume (Confluent) -> land (Databricks Delta) -> chunk -> quality
    gates -> embed and load (Module 7 knowledge base + lineage graph)

Each run gets a pipeline_run_id stamped on every chunk (v5 Appendix B).
Re-running is idempotent: content-derived doc ids overwrite on upsert and
the dedup index skips unchanged records (v5 Section 3.3).

The run is authorized under the write-scoped pipeline identity from
module9/identity.py before any data moves: the Module 8 "agent identity
vs pipeline identity" split, enforced in code.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from module9.config.corpora import get_corpus
from module9.config.settings import ConfluentSettings, DatabricksSettings
from module9.identity import (
    PIPELINE_INGEST_SCOPE,
    authorize_pipeline_write,
    build_audit_record,
)
from module9.ingestion.chunk import chunk_record
from module9.ingestion.delta_writer import create_lakehouse, land_event
from module9.ingestion.lineage import ensure_lineage_graph
from module9.ingestion.load import LoadResult, load_chunk
from module9.ingestion.stream_consumer import create_stream_source


def new_run_id() -> str:
    """Opaque pipeline run id.

    Deliberately carries no date. The run's timing is already recorded in
    every chunk's ingested_at, and keeping the date out of the identifier
    means the id can be shown on screen in a recording without pinning it
    to a calendar day.
    """
    return f"run-{secrets.token_hex(4)}"


@dataclass
class PipelineRunResult:
    """Summary of one end-to-end pipeline run."""

    run_id: str
    corpus: str
    consumed: int = 0
    landed: int = 0
    chunks_stored: int = 0
    chunks_rejected: int = 0
    chunks_skipped: int = 0
    doc_ids: list[str] = field(default_factory=list)
    load_results: list[LoadResult] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    audit_records: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "corpus": self.corpus,
            "consumed": self.consumed,
            "landed": self.landed,
            "chunks_stored": self.chunks_stored,
            "chunks_rejected": self.chunks_rejected,
            "chunks_skipped": self.chunks_skipped,
            "doc_ids": self.doc_ids,
        }


def run_pipeline(
    corpus: str = "history",
    max_events: int = 10,
    stream=None,
    lakehouse=None,
) -> PipelineRunResult:
    """Run the full ingest loop for events waiting on the stream.

    Raises module8's Auth0Error if the pipeline identity is not authorized
    to ingest, before any data is read or written.
    """
    spec = get_corpus(corpus)
    run_id = new_run_id()
    result = PipelineRunResult(run_id=run_id, corpus=corpus)

    # Stage 0: authorize the write-scoped pipeline identity (Module 8 seam).
    decision = authorize_pipeline_write(corpus)
    result.audit_records.append(
        build_audit_record(
            run_id,
            "pipeline-authorization",
            "Pipeline identity authorized for corpus ingest",
            "module8.identity.delegation.authorize_agent_call",
            actor=decision.a2a_principal,
            action="ingest_corpus",
            required_scope=PIPELINE_INGEST_SCOPE,
            decision="allow",
            token_fingerprint=decision.token_fingerprint,
            details={"corpus": corpus, "iam_role_arn": decision.iam_role_arn},
        )
    )

    confluent = ConfluentSettings()
    databricks = DatabricksSettings()
    owns_stream = stream is None
    stream = stream or create_stream_source(confluent)
    lakehouse = lakehouse or create_lakehouse(databricks)

    # Stage 1: consume a bounded window from the Confluent topic. Close the
    # consumer we created so it does not keep the partition assignment and
    # starve the next run under the same consumer group.
    try:
        events = stream.poll_events(max_records=max_events)
    finally:
        if owns_stream:
            stream.close()
    result.consumed = len(events)

    for consumed in events:
        # Stage 2: land in Delta Lake bronze -> silver; Unity Catalog
        # captures the table-level lineage edge automatically.
        delta = land_event(consumed, lakehouse=lakehouse, settings=databricks)
        result.landed += 1

        # Stages 3 to 5 per chunk: chunk, gate, embed, load.
        event_outcome = {
            "source_uri": consumed.source_uri,
            "kafka_offset": consumed.offset,
            "delta_version": delta.silver_version,
            "chunks": [],
        }
        for chunk in chunk_record("", corpus, event=consumed.event):
            load_result = load_chunk(
                chunk,
                spec,
                pipeline_run_id=run_id,
                source_uri=consumed.source_uri,
                source_type="structured-record",
                source_modified=consumed.event_time,
                consumed=consumed,
                delta=delta,
            )
            result.load_results.append(load_result)
            event_outcome["chunks"].append(
                {"action": load_result.action, "doc_id": load_result.doc_id}
            )
            if load_result.action == "stored":
                result.chunks_stored += 1
                result.doc_ids.append(load_result.doc_id)
            elif load_result.action == "rejected":
                result.chunks_rejected += 1
            else:
                result.chunks_skipped += 1

        result.events.append(event_outcome)

        # Lineage graph: Source -> Dataset -> Corpus -> Agent (Seam C).
        ensure_lineage_graph(
            f"confluent://{consumed.topic}",
            delta.silver_table,
            corpus,
            delta_version=delta.silver_version,
            unity_catalog_lineage_id=delta.unity_catalog_lineage_id,
            pipeline_run_id=run_id,
            access_level=spec.access_level,
        )

    result.audit_records.append(
        build_audit_record(
            run_id,
            "pipeline-completion",
            (
                f"Run complete: {result.consumed} consumed, "
                f"{result.chunks_stored} stored, {result.chunks_rejected} "
                f"rejected, {result.chunks_skipped} skipped"
            ),
            "module9.ingestion.pipeline_run",
            actor=decision.a2a_principal,
            action="ingest_corpus",
            required_scope=PIPELINE_INGEST_SCOPE,
            decision="complete",
            token_fingerprint=decision.token_fingerprint,
            details=result.summary(),
        )
    )
    return result
