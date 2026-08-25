# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
tests/test_module9_lineage.py
==============================
Module 9 lineage and access-control tests: the lineage graph has the
Source -> Dataset -> Corpus -> Agent shape, the provenance chain resolves
to the Kafka offset and Delta version, every chunk carries the full
Appendix B metadata plus access stamps, and the Module 8 authorization
layers enforce corpus scopes. No credentials required.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AGENT_MOCK_PIPELINE"] = "true"
os.environ["AGENT_MOCK_MEMORY"] = "true"
os.environ["AGENT_MOCK_MODE"] = "true"

APPENDIX_B_KEYS = {
    "source_uri",
    "source_type",
    "source_modified",
    "ingested_at",
    "pipeline_run_id",
    "content_hash",
    "embedding_model",
    "chunking_strategy",
    "chunk_index",
    "chunk_count",
    "parent_chunk_id",
    "domain",
    "access_level",
    "allowed_agent_roles",
    "is_deprecated",
    "deprecated_at",
}

PARTNER_ANCHOR_KEYS = {
    "delta_table",
    "delta_version",
    "unity_catalog_lineage_id",
    "kafka_topic",
    "kafka_partition",
    "kafka_offset",
}

ACCESS_KEYS = {"agent_scope", "owner_team"}


def _reset_module9_state() -> None:
    from module9.ingestion import embed, kb_sink, lineage, load, quality
    from module9.mock import confluent_mock, databricks_mock
    from module9.tools import pipeline_tools

    confluent_mock.reset()
    databricks_mock.reset()
    lineage.reset_lineage()
    quality.reset_dedup_index()
    load.get_mongo_store.cache_clear()
    embed._get_embedding_service.cache_clear()
    pipeline_tools._get_stores.cache_clear()
    kb_sink.reset_sink()


@pytest.fixture(autouse=True)
def mock_pipeline_env(monkeypatch):
    monkeypatch.setenv("AGENT_MOCK_PIPELINE", "true")
    monkeypatch.setenv("AGENT_MOCK_MEMORY", "true")
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    # Another module's tests may load agentic-ai/.env, which would point the
    # knowledge sink at a real Bedrock knowledge base. Keep these tests
    # hermetic regardless of suite ordering.
    monkeypatch.delenv("BEDROCK_KB_ID", raising=False)
    monkeypatch.delenv("BEDROCK_KB_DATA_SOURCE_ID", raising=False)
    _reset_module9_state()
    yield
    _reset_module9_state()


def _run_pipeline_once():
    from module9.ingestion.pipeline_run import run_pipeline
    from module9.producers.devops_event_producer import produce_event

    produce_event()
    return run_pipeline(corpus="history", max_events=5)


class TestLineageGraph:
    def test_graph_has_source_dataset_corpus_agent_shape(self):
        from module9.ingestion.lineage import get_lineage

        _run_pipeline_once()
        lineage = get_lineage("history")
        rels = {
            (e["source"], e["relationship"], e["target"])
            for e in lineage["graph_edges"]
        }
        assert (
            "confluent://devops-events",
            "FEEDS",
            "devops.silver.deployment_events",
        ) in rels
        assert (
            "devops.silver.deployment_events",
            "POPULATES",
            "history",
        ) in rels
        assert ("history", "SERVES", "DevOpsCompanion") in rels

    def test_graph_edges_carry_delta_and_run_properties(self):
        from module9.ingestion.lineage import get_lineage

        result = _run_pipeline_once()
        edges = {e["relationship"]: e for e in get_lineage("history")["graph_edges"]}
        assert edges["FEEDS"]["properties"]["delta_version"] == 1
        assert edges["FEEDS"]["properties"]["unity_catalog_lineage_id"].startswith("lin-")
        assert edges["POPULATES"]["properties"]["pipeline_run_id"] == result.run_id
        assert edges["SERVES"]["properties"]["access_level"] == "internal"

    def test_graph_writes_are_idempotent(self):
        from module9.ingestion.lineage import ensure_lineage_graph, get_registry

        for _ in range(2):
            ensure_lineage_graph(
                "confluent://devops-events",
                "devops.silver.deployment_events",
                "history",
                pipeline_run_id="run-x",
            )
        assert len(get_registry().edges) == 3


class TestProvenance:
    def test_chain_resolves_to_kafka_offset_and_delta_version(self):
        from module9.ingestion.lineage import get_provenance

        result = _run_pipeline_once()
        prov = get_provenance(result.doc_ids[0])

        assert prov["found"] is True
        assert prov["corpus"] == "history"
        assert prov["confluent"]["kafka_topic"] == "devops-events"
        assert prov["confluent"]["kafka_partition"] == 0
        assert prov["confluent"]["kafka_offset"] == 0
        assert prov["databricks"]["delta_table"] == "devops.silver.deployment_events"
        assert prov["databricks"]["delta_version"] == 1
        assert prov["databricks"]["unity_catalog_lineage_id"].startswith("lin-")
        assert prov["pipeline"]["pipeline_run_id"] == result.run_id
        assert prov["pipeline"]["content_hash"].startswith("sha256:")
        assert prov["source"]["source_uri"] == (
            "confluent://devops-events/partition-0/offset-0"
        )

    def test_graph_path_runs_agent_back_to_source(self):
        from module9.ingestion.lineage import get_provenance

        result = _run_pipeline_once()
        path = get_provenance(result.doc_ids[0])["graph_path"]
        assert path[0] == "DevOpsCompanion"
        assert "history" in path
        assert path[-1].startswith("confluent://devops-events/")


class TestChunkMetadataSchema:
    def test_every_appendix_b_field_is_populated(self):
        from module9.ingestion.lineage import get_registry

        result = _run_pipeline_once()
        metadata = get_registry().chunks[result.doc_ids[0]]

        missing = APPENDIX_B_KEYS - set(metadata)
        assert not missing, f"Appendix B fields missing: {missing}"
        missing_anchors = PARTNER_ANCHOR_KEYS - set(metadata)
        assert not missing_anchors, f"partner anchors missing: {missing_anchors}"
        missing_access = ACCESS_KEYS - set(metadata)
        assert not missing_access, f"access fields missing: {missing_access}"

        assert metadata["source_type"] == "structured-record"
        assert metadata["embedding_model"] == "amazon.titan-embed-text-v2:0"
        assert metadata["chunking_strategy"] == "fixed"
        assert metadata["domain"] == "history"
        assert metadata["corpus"] == "history"
        assert metadata["source_module"] == "module9"
        assert metadata["is_deprecated"] is False

    def test_access_stamps_match_history_corpus_policy(self):
        from module9.ingestion.lineage import get_registry

        result = _run_pipeline_once()
        metadata = get_registry().chunks[result.doc_ids[0]]

        assert metadata["access_level"] == "internal"
        assert set(metadata["allowed_agent_roles"]) == {
            "Orchestrator",
            "DeployObserve",
        }
        assert metadata["agent_scope"] == "operations"


class TestModule8AccessControl:
    def test_operations_roles_are_authorized_for_history(self):
        from module9.identity import authorize_retrieval

        for role in ("DeployObserve", "Orchestrator"):
            decision = authorize_retrieval(role, "history")
            assert "devops:knowledge:history" in decision.effective_scopes
            assert decision.token_fingerprint.startswith("sha256:")

    def test_non_operations_roles_are_denied_history(self):
        from module9.identity import Auth0Error, authorize_retrieval

        for role in ("RepositoryAnalysis", "InfrastructureGeneration"):
            with pytest.raises(Auth0Error):
                authorize_retrieval(role, "history")

    def test_unknown_role_and_corpus_are_denied(self):
        from module9.identity import Auth0Error, authorize_retrieval

        with pytest.raises(Auth0Error):
            authorize_retrieval("Intruder", "history")
        with pytest.raises(Auth0Error):
            authorize_retrieval("DeployObserve", "secrets")

    def test_compiled_filter_pins_corpus_and_scope(self):
        from module9.identity import authorize_retrieval, compile_retrieval_filter

        decision = authorize_retrieval("DeployObserve", "history")
        assert compile_retrieval_filter(decision, "history") == {
            "corpus": "history",
            "agent_scope": "operations",
        }
        general = authorize_retrieval("RepositoryAnalysis", "policy")
        assert compile_retrieval_filter(general, "policy") == {"corpus": "policy"}

    def test_allowed_corpora_reflect_permission_ceilings(self):
        from module9.identity import allowed_corpora

        assert sorted(allowed_corpora("DeployObserve")) == [
            "history",
            "policy",
            "service",
        ]
        assert sorted(allowed_corpora("RepositoryAnalysis")) == ["policy", "service"]

    def test_retrieval_filter_excludes_history_chunks_for_denied_role(self):
        from module9.tools.pipeline_tools import governed_recall

        _run_pipeline_once()
        denied = governed_recall(
            "checkout-api deployment", corpus="history", role="RepositoryAnalysis"
        )
        assert denied["access"] == "denied"
        assert denied["results"] == []

    def test_pipeline_identity_is_write_scoped_only(self):
        from module9.identity import (
            PIPELINE_WRITE_POLICY,
            authorize_pipeline_write,
        )

        decision = authorize_pipeline_write("history")
        assert decision.effective_scopes == frozenset({"devops:pipeline:ingest"})
        assert "retrieve_corpus" not in PIPELINE_WRITE_POLICY.allowed_operations

    def test_audit_record_mirrors_module8_evidence_shape(self):
        from module9.identity import build_audit_record

        record = build_audit_record(
            "run-test",
            "pipeline-authorization",
            "answer",
            "source",
            actor="a2a://devops-companion/pipeline",
            action="ingest_corpus",
            required_scope="devops:pipeline:ingest",
            decision="allow",
            token_fingerprint="sha256:abc",
        )
        for key in (
            "workflow_execution_id",
            "trace_point",
            "answer",
            "evidence_source",
            "actor",
            "action",
            "required_scope",
            "decision",
            "token_fingerprint",
            "details",
        ):
            assert key in record
        # Deterministic event id (uuid5 over run id + trace point)
        again = build_audit_record(
            "run-test",
            "pipeline-authorization",
            "answer",
            "source",
            actor="a2a://devops-companion/pipeline",
            action="ingest_corpus",
        )
        assert record["event_id"] == again["event_id"]
