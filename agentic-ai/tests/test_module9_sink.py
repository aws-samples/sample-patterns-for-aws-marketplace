# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
tests/test_module9_sink.py
===========================
Knowledge sink tests: metadata conversion, retrieval filter compilation,
and backend resolution with graceful degradation.

All offline. The Bedrock paths are exercised through pure functions and a
stubbed client, so no knowledge base and no credentials are required.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AGENT_MOCK_PIPELINE"] = "true"
os.environ["AGENT_MOCK_MEMORY"] = "true"
os.environ["AGENT_MOCK_MODE"] = "true"


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
def mock_env(monkeypatch):
    monkeypatch.setenv("AGENT_MOCK_PIPELINE", "true")
    monkeypatch.setenv("AGENT_MOCK_MEMORY", "true")
    monkeypatch.setenv("AGENT_MOCK_MODE", "true")
    monkeypatch.delenv("BEDROCK_KB_ID", raising=False)
    monkeypatch.delenv("BEDROCK_KB_DATA_SOURCE_ID", raising=False)
    _reset_module9_state()
    yield
    _reset_module9_state()


class TestInlineAttributes:
    def test_types_are_mapped(self):
        from module9.ingestion.kb_sink import to_inline_attributes

        attrs = to_inline_attributes({
            "corpus": "history",
            "chunk_index": 0,
            "delta_version": 13,
            "is_deprecated": False,
            "allowed_agent_roles": ["Orchestrator", "DeployObserve"],
        })
        by_key = {a["key"]: a["value"] for a in attrs}

        assert by_key["corpus"] == {"type": "STRING", "stringValue": "history"}
        assert by_key["chunk_index"]["type"] == "NUMBER"
        assert by_key["chunk_index"]["numberValue"] == 0.0
        assert by_key["delta_version"]["numberValue"] == 13.0
        # Managed knowledge bases reject BOOLEAN inline attributes at index
        # time, so booleans are encoded as strings that filter predictably.
        assert by_key["is_deprecated"] == {"type": "STRING", "stringValue": "false"}
        assert by_key["allowed_agent_roles"] == {
            "type": "STRING_LIST",
            "stringListValue": ["Orchestrator", "DeployObserve"],
        }

    def test_none_and_empty_are_dropped(self):
        from module9.ingestion.kb_sink import to_inline_attributes

        attrs = to_inline_attributes({
            "parent_chunk_id": None,
            "deprecated_at": None,
            "empty": "",
            "empty_list": [],
            "kept": "value",
        })
        assert [a["key"] for a in attrs] == ["kept"]

    def test_booleans_become_strings_not_numbers(self):
        """bool is a subclass of int in Python, so the order of the type
        checks matters: a boolean must not be emitted as NUMBER 1.0."""
        from module9.ingestion.kb_sink import to_inline_attributes

        true_attr = to_inline_attributes({"flag": True})[0]["value"]
        false_attr = to_inline_attributes({"flag": False})[0]["value"]
        assert true_attr == {"type": "STRING", "stringValue": "true"}
        assert false_attr == {"type": "STRING", "stringValue": "false"}

    def test_no_boolean_attributes_are_emitted(self):
        """Guard the index-time constraint across the full metadata schema."""
        from module9.config.corpora import get_corpus
        from module9.ingestion.chunk import chunk_record
        from module9.ingestion.kb_sink import to_inline_attributes
        from module9.ingestion.load import build_chunk_metadata
        from module9.mock.sample_events import deployment_event

        event = deployment_event()
        chunk = chunk_record("", "history", event=event)[0]
        metadata = build_chunk_metadata(
            chunk,
            get_corpus("history"),
            pipeline_run_id="run-test",
            chunk_hash="sha256:abc",
            source_uri="confluent://devops-events/partition-0/offset-1",
            source_type="structured-record",
            source_modified=event["event_time"],
        )
        types = {a["value"]["type"] for a in to_inline_attributes(metadata)}
        assert "BOOLEAN" not in types
        assert types <= {"STRING", "NUMBER", "STRING_LIST"}

    def test_full_appendix_b_metadata_converts(self):
        from module9.config.corpora import get_corpus
        from module9.ingestion.chunk import chunk_record
        from module9.ingestion.kb_sink import to_inline_attributes
        from module9.ingestion.load import build_chunk_metadata
        from module9.mock.sample_events import deployment_event

        event = deployment_event()
        chunk = chunk_record("", "history", event=event)[0]
        metadata = build_chunk_metadata(
            chunk,
            get_corpus("history"),
            pipeline_run_id="run-test",
            chunk_hash="sha256:abc",
            source_uri="confluent://devops-events/partition-0/offset-1",
            source_type="structured-record",
            source_modified=event["event_time"],
        )
        attrs = to_inline_attributes(metadata)
        keys = {a["key"] for a in attrs}
        # Filterable fields the access-control beat depends on must survive.
        for required in ("corpus", "domain", "access_level", "agent_scope"):
            assert required in keys
        assert all("key" in a and "value" in a for a in attrs)


class TestRetrievalFilter:
    def test_none_filter(self):
        from module9.ingestion.kb_sink import to_retrieval_filter

        assert to_retrieval_filter(None) is None
        assert to_retrieval_filter({}) is None

    def test_single_key_uses_equals(self):
        from module9.ingestion.kb_sink import to_retrieval_filter

        assert to_retrieval_filter({"corpus": "policy"}) == {
            "equals": {"key": "corpus", "value": "policy"}
        }

    def test_multiple_keys_use_and_all(self):
        from module9.ingestion.kb_sink import to_retrieval_filter

        compiled = to_retrieval_filter(
            {"corpus": "history", "agent_scope": "operations"}
        )
        assert "andAll" in compiled
        assert len(compiled["andAll"]) == 2
        assert {"equals": {"key": "corpus", "value": "history"}} in compiled["andAll"]
        assert {
            "equals": {"key": "agent_scope", "value": "operations"}
        } in compiled["andAll"]

    def test_role_filter_compiles_end_to_end(self):
        from module9.identity import authorize_retrieval, compile_retrieval_filter
        from module9.ingestion.kb_sink import to_retrieval_filter

        decision = authorize_retrieval("DeployObserve", "history")
        filter_dict = compile_retrieval_filter(decision, "history")
        compiled = to_retrieval_filter(filter_dict)
        assert "andAll" in compiled


class TestBackendResolution:
    def test_defaults_to_mock_when_nothing_configured(self):
        from module9.ingestion.kb_sink import BACKEND_MOCK, resolve_sink

        info = resolve_sink().info()
        assert info.backend == BACKEND_MOCK
        assert info.embeds_internally is False
        assert info.embedding_model == "amazon.titan-embed-text-v2:0"

    def test_partial_kb_config_is_ignored(self, monkeypatch):
        from module9.config.settings import KnowledgeBaseSettings
        from module9.ingestion.kb_sink import BACKEND_MOCK, resolve_sink

        monkeypatch.setenv("BEDROCK_KB_ID", "ABC123")  # data source id missing
        assert KnowledgeBaseSettings().configured is False
        assert resolve_sink().info().backend == BACKEND_MOCK

    def test_unreachable_kb_degrades_instead_of_raising(self, monkeypatch):
        from module9.ingestion import kb_sink

        monkeypatch.setenv("BEDROCK_KB_ID", "DOESNOTEXIST")
        monkeypatch.setenv("BEDROCK_KB_DATA_SOURCE_ID", "DOESNOTEXIST")

        def _boom(_settings):
            raise RuntimeError("simulated unreachable knowledge base")

        monkeypatch.setattr(kb_sink, "BedrockManagedKBSink", _boom)
        kb_sink.reset_sink()
        assert resolve_backend(kb_sink) == kb_sink.BACKEND_MOCK

    def test_settings_validation_message_names_missing_vars(self):
        from module9.config.settings import KnowledgeBaseSettings

        settings = KnowledgeBaseSettings(knowledge_base_id="", data_source_id="")
        with pytest.raises(ValueError, match="BEDROCK_KB_ID"):
            settings.validate_for_live()


def resolve_backend(kb_sink_module) -> str:
    return kb_sink_module.resolve_sink().info().backend


class TestSinkAttributionOnChunks:
    def test_metadata_records_the_active_sink(self):
        from module9.ingestion.pipeline_run import run_pipeline
        from module9.ingestion.lineage import get_registry
        from module9.producers.devops_event_producer import produce_event

        produce_event()
        result = run_pipeline(corpus="history", max_events=5)
        metadata = get_registry().chunks[result.doc_ids[0]]
        assert metadata["knowledge_sink"] == "in-process-mock"
        assert metadata["embedding_model"] == "amazon.titan-embed-text-v2:0"
