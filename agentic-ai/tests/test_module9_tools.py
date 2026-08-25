# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
tests/test_module9_tools.py
============================
Module 9 tool tests: the six pipeline tools return well-formed JSON
envelopes and the governed recall tool enforces the caller's role.
No credentials required.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AGENT_MOCK_PIPELINE"] = "true"
os.environ["AGENT_MOCK_MEMORY"] = "true"
os.environ["AGENT_MOCK_MODE"] = "true"

ENVELOPE_KEYS = {"tool", "timestamp", "mock_pipeline", "data"}


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


def _invoke(tool, args: dict) -> dict:
    """Invoke a LangChain tool and parse its JSON envelope."""
    raw = tool.invoke(args)
    payload = json.loads(raw)
    assert ENVELOPE_KEYS <= set(payload), f"missing envelope keys in {payload}"
    assert payload["mock_pipeline"] is True
    return payload


class TestToolEnvelopes:
    def test_all_six_tools_return_json_envelopes(self):
        from module9.tools.pipeline_tools import PIPELINE_TOOLS

        assert len(PIPELINE_TOOLS) == 6
        args_by_tool = {
            "run_ingestion": {"corpus": "history", "max_events": 1},
            "check_freshness": {"corpus": "all"},
            "get_provenance": {"doc_id": "kb-his-nonexistent"},
            "assert_quality": {},
            "list_corpora": {},
            "explain_staleness": {"corpus": "history"},
        }
        for name, tool in PIPELINE_TOOLS.items():
            payload = _invoke(tool, args_by_tool[name])
            assert payload["tool"] == name

    def test_run_ingestion_reports_pipeline_summary(self):
        from module9.producers.devops_event_producer import produce_event
        from module9.tools.pipeline_tools import run_ingestion

        produce_event()
        payload = _invoke(run_ingestion, {"corpus": "history", "max_events": 5})
        data = payload["data"]
        assert data["consumed"] == 1
        assert data["chunks_stored"] == 1
        assert data["run_id"].startswith("run-")

    def test_run_ingestion_rejects_unknown_corpus(self):
        from module9.tools.pipeline_tools import run_ingestion

        payload = _invoke(run_ingestion, {"corpus": "nope"})
        assert "error" in payload["data"]

    def test_check_freshness_all_returns_three_corpora(self):
        from module9.tools.pipeline_tools import check_freshness

        payload = _invoke(check_freshness, {"corpus": "all"})
        assert sorted(v["corpus"] for v in payload["data"]) == [
            "history",
            "policy",
            "service",
        ]

    def test_get_provenance_unknown_doc_reports_not_found(self):
        from module9.tools.pipeline_tools import get_provenance

        payload = _invoke(get_provenance, {"doc_id": "kb-his-missing"})
        assert payload["data"]["found"] is False

    def test_get_provenance_resolves_loaded_doc(self):
        from module9.producers.devops_event_producer import produce_event
        from module9.ingestion.pipeline_run import run_pipeline
        from module9.tools.pipeline_tools import get_provenance

        produce_event()
        result = run_pipeline(corpus="history", max_events=5)
        payload = _invoke(get_provenance, {"doc_id": result.doc_ids[0]})
        data = payload["data"]
        assert data["found"] is True
        assert data["confluent"]["kafka_offset"] == 0
        assert data["databricks"]["delta_version"] == 1

    def test_assert_quality_evaluates_content(self):
        from module9.tools.pipeline_tools import assert_quality

        payload = _invoke(assert_quality, {"content": "too short"})
        assert payload["data"]["verdict"] == "reject"

    def test_assert_quality_without_content_reports_configuration(self):
        from module9.tools.pipeline_tools import assert_quality

        payload = _invoke(assert_quality, {})
        assert "gates" in payload["data"]
        assert "dedup_index_size" in payload["data"]

    def test_list_corpora_returns_catalog_with_access_stamps(self):
        from module9.tools.pipeline_tools import list_corpora

        payload = _invoke(list_corpora, {})
        catalog = {c["corpus"]: c for c in payload["data"]}
        assert set(catalog) == {"service", "policy", "history"}
        history = catalog["history"]
        assert history["access_level"] == "internal"
        assert history["agent_scope"] == "operations"
        assert set(history["allowed_agent_roles"]) == {"Orchestrator", "DeployObserve"}

    def test_explain_staleness_narrates(self):
        from module9.tools.pipeline_tools import explain_staleness

        payload = _invoke(explain_staleness, {"corpus": "history"})
        assert "explanation" in payload["data"]


class TestGovernedRecallTool:
    def _load_history_chunk(self) -> None:
        from module9.ingestion.pipeline_run import run_pipeline
        from module9.producers.devops_event_producer import produce_event

        produce_event()
        run_pipeline(corpus="history", max_events=5)

    def test_authorized_role_retrieves(self):
        from module9.tools.pipeline_tools import make_governed_recall

        self._load_history_chunk()
        recall_tool = make_governed_recall("DeployObserve")
        assert recall_tool.name == "recall_semantic_memory"
        payload = _invoke(
            recall_tool, {"query": "checkout-api deployment", "corpus": "history"}
        )
        data = payload["data"]
        assert data["access"] == "granted"
        assert len(data["results"]) == 1
        assert data["results"][0]["kafka_offset"] == 0

    def test_unauthorized_role_is_denied_with_no_results(self):
        from module9.tools.pipeline_tools import make_governed_recall

        self._load_history_chunk()
        recall_tool = make_governed_recall("RepositoryAnalysis")
        payload = _invoke(
            recall_tool, {"query": "checkout-api deployment", "corpus": "history"}
        )
        data = payload["data"]
        assert data["access"] == "denied"
        assert data["results"] == []
        assert "devops:knowledge:history" in data["reason"]

    def test_unauthorized_role_still_reads_general_corpora(self):
        from module9.ingestion.load import load_seed_corpora
        from module9.tools.pipeline_tools import make_governed_recall

        load_seed_corpora()
        recall_tool = make_governed_recall("RepositoryAnalysis")
        payload = _invoke(
            recall_tool, {"query": "deployment runbook", "corpus": "policy"}
        )
        assert payload["data"]["access"] == "granted"
        assert len(payload["data"]["results"]) >= 1
