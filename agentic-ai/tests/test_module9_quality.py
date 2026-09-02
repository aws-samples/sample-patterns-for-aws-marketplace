# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
tests/test_module9_quality.py
==============================
Module 9 quality gate and freshness tests: the gates reject bad batches,
dedup skips unchanged content, and freshness verdicts track corpus SLAs.
No credentials required.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AGENT_MOCK_PIPELINE"] = "true"
os.environ["AGENT_MOCK_MEMORY"] = "true"
os.environ["AGENT_MOCK_MODE"] = "true"

GOOD_CONTENT = (
    "Today, service checkout-api version v2.4.0 was deployed to production "
    "in us-east-1. The deployment succeeded after 12 minutes. CloudWatch "
    "alarm checkout-api-5xx-error-rate triggered, resolved after traffic "
    "stabilization. The deployment was initiated by release-pipeline."
)


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


class TestQualityGates:
    def test_good_content_passes_all_gates(self):
        from module9.ingestion.quality import run_quality_gates

        report = run_quality_gates(GOOD_CONTENT)
        assert report.verdict == "pass"
        assert report.content_hash.startswith("sha256:")
        assert len(report.content_hash) == len("sha256:") + 64
        assert all(c["passed"] for c in report.checks)

    def test_empty_content_is_rejected(self):
        from module9.ingestion.quality import run_quality_gates

        report = run_quality_gates("")
        assert report.verdict == "reject"
        failed = {c["check"] for c in report.checks if not c["passed"]}
        assert "non_empty" in failed

    def test_short_content_fails_min_token_gate(self):
        from module9.ingestion.quality import run_quality_gates

        report = run_quality_gates("deployment ok")
        assert report.verdict == "reject"
        failed = {c["check"] for c in report.checks if not c["passed"]}
        assert "min_tokens" in failed

    def test_markup_noise_fails_structural_gate(self):
        from module9.ingestion.quality import run_quality_gates

        noise = "{}[]()<><> 1234 5678 " * 20
        report = run_quality_gates(noise)
        assert report.verdict == "reject"
        failed = {c["check"] for c in report.checks if not c["passed"]}
        assert "structural" in failed

    def test_bad_sample_event_is_rejected_before_embedding(self):
        from module9.ingestion.chunk import render_history_record
        from module9.ingestion.quality import run_quality_gates
        from module9.mock.sample_events import bad_event

        rendered = render_history_record(bad_event())
        report = run_quality_gates(rendered)
        assert report.verdict == "reject"

    def test_duplicate_content_is_skipped_not_rejected(self):
        from module9.ingestion.quality import get_dedup_index, run_quality_gates

        index = get_dedup_index()
        first = run_quality_gates(GOOD_CONTENT, index)
        assert first.verdict == "pass"
        index.record(first.content_hash, "kb-his-test")

        second = run_quality_gates(GOOD_CONTENT, index)
        assert second.verdict == "skip_duplicate"
        dedup_check = next(c for c in second.checks if c["check"] == "dedup")
        assert "kb-his-test" in dedup_check["detail"]

    def test_estimate_tokens_uses_char_heuristic_for_dense_text(self):
        from module9.ingestion.quality import estimate_tokens

        assert estimate_tokens("") == 0
        assert estimate_tokens("one two three") == 3
        # 400 chars with few spaces: the chars/4 heuristic dominates.
        assert estimate_tokens("x" * 400) == 100


class TestEmbeddingValidation:
    def test_correct_dimension_passes(self):
        from module9.ingestion.quality import validate_embedding

        validate_embedding([0.1] * 1024)

    def test_wrong_dimension_raises(self):
        from module9.ingestion.quality import validate_embedding

        with pytest.raises(ValueError, match="1024"):
            validate_embedding([0.1] * 512)

    def test_mock_embedding_service_returns_1024_dims(self):
        from module9.ingestion.embed import embed_chunk

        vector = embed_chunk(GOOD_CONTENT)
        assert len(vector) == 1024


class TestFreshness:
    def test_empty_corpus_reports_empty_status(self):
        from module9.ingestion.freshness import check_freshness

        verdict = check_freshness("history")
        assert verdict["status"] == "empty"
        assert verdict["chunk_count"] == 0
        assert verdict["newest_chunk_age_hours"] is None

    def test_fresh_after_pipeline_run(self):
        from module9.ingestion.freshness import check_freshness
        from module9.ingestion.pipeline_run import run_pipeline
        from module9.producers.devops_event_producer import produce_event

        produce_event()
        run_pipeline(corpus="history", max_events=5)
        verdict = check_freshness("history")
        assert verdict["status"] == "fresh"
        assert verdict["chunk_count"] == 1
        assert verdict["newest_chunk_age_hours"] <= verdict["sla_hours"]

    def test_stale_when_newest_chunk_exceeds_sla(self):
        from module9.ingestion.freshness import check_freshness
        from module9.ingestion.lineage import get_registry

        old = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        get_registry().register_chunk(
            "kb-his-old", {"corpus": "history", "ingested_at": old}
        )
        verdict = check_freshness("history")
        assert verdict["status"] == "stale"
        assert verdict["newest_chunk_age_hours"] > verdict["sla_hours"]

    def test_explain_staleness_narrates_the_verdict(self):
        from module9.ingestion.freshness import explain_staleness

        verdict = explain_staleness("history")
        assert "explanation" in verdict
        assert "history" in verdict["explanation"]

    def test_check_all_corpora_covers_three(self):
        from module9.ingestion.freshness import check_all_corpora

        verdicts = check_all_corpora()
        assert sorted(v["corpus"] for v in verdicts) == [
            "history",
            "policy",
            "service",
        ]


class TestWritePathGuardrail:
    def test_pii_is_anonymized_before_load(self):
        from module9.config.corpora import get_corpus
        from module9.ingestion.chunk import chunk_record
        from module9.ingestion.load import load_chunk
        from module9.mock.sample_events import pii_deployment_event

        event = pii_deployment_event()
        chunk = chunk_record("", "history", event=event)[0]
        assert "jordan.lee@example.com" in chunk.content  # PII present pre-load

        result = load_chunk(
            chunk,
            get_corpus("history"),
            pipeline_run_id="run-test",
            source_uri="confluent://devops-events/partition-0/offset-9",
            source_type="structured-record",
            source_modified=event["event_time"],
        )
        assert result.action == "stored"
        assert "jordan.lee@example.com" not in result.metadata.get("timestamp", "")

        from module9.ingestion.load import get_mongo_store

        stored = get_mongo_store().vector_search(
            [0.0] * 1024, filter_dict={"corpus": "history"}, top_k=5
        )
        assert stored, "chunk should be retrievable"
        assert "jordan.lee@example.com" not in stored[0]["content"]
        assert "[REDACTED_EMAIL]" in stored[0]["content"]
