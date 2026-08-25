# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/demo_prep.py
=====================
Self-preparing demo environment.

The demo is run repeatedly, in rehearsals and on stage, and it must open
identically every time without the presenter remembering a checklist. This
module runs automatically at the start of a full demo run and does five
things:

1. **Health check.** Confirms each live partner is reachable.
2. **Automatic degradation.** If a partner is unreachable, switches just
   that partner to its in-process mock and says so on screen. Confluent and
   Databricks degrade independently, so one outage does not cost both.
3. **Backlog skip.** Advances the ingestion consumer group to the end of the
   topic, so the demo consumes only the events it produces and never replays
   a pile of rehearsal leftovers. Non-destructive: no messages are deleted.
4. **Lakehouse reset.** Truncates the demo bronze and silver tables so row
   counts and the Catalog Explorer view reflect this run only.
5. **Warm-up.** Wakes the SQL warehouse and makes one small Bedrock call, so
   the first on-stage interaction does not pay a cold start.

In-process state (dedup index, lineage registry, store caches) is cleared
too, so running the demo twice in one session behaves like a fresh start.

Nothing here is required for correctness: the demo runs without it. It
exists to make repeated runs boring and predictable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class PrepStep:
    name: str
    ok: bool
    detail: str
    degraded: bool = False


@dataclass
class PrepReport:
    steps: list[PrepStep] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, degraded: bool = False) -> None:
        self.steps.append(PrepStep(name, ok, detail, degraded))

    @property
    def degraded_partners(self) -> list[str]:
        return [s.name for s in self.steps if s.degraded]


def _clear_process_state() -> None:
    """Reset in-process caches so a repeat run starts clean."""
    from module9.ingestion import embed, kb_sink, lineage, load, quality
    from module9.tools import pipeline_tools

    quality.reset_dedup_index()
    lineage.reset_lineage()
    load.get_mongo_store.cache_clear()
    embed._get_embedding_service.cache_clear()
    pipeline_tools._get_stores.cache_clear()
    kb_sink.reset_sink()


def _reset_mock_partners() -> None:
    from module9.mock import confluent_mock, databricks_mock

    confluent_mock.reset()
    databricks_mock.reset()


def _prepare_confluent(report: PrepReport, reset: bool) -> None:
    """Verify Confluent, then skip any backlog on the ingestion group."""
    from module9.config.settings import ConfluentSettings, is_mock_confluent

    settings = ConfluentSettings()

    if is_mock_confluent():
        report.add("Confluent Cloud", True, "in-process mock, topic reset")
        return

    try:
        settings.validate_for_live()
        from confluent_kafka import Consumer, TopicPartition  # type: ignore[import]
    except Exception as exc:
        os.environ["CONFLUENT_MOCK"] = "true"
        report.add(
            "Confluent Cloud",
            True,
            f"unavailable ({str(exc)[:80]}), switched to in-process mock",
            degraded=True,
        )
        return

    consumer = None
    try:
        config = settings.client_config()
        config.update(
            {"group.id": settings.group_id, "enable.auto.commit": False}
        )
        consumer = Consumer(config)
        metadata = consumer.list_topics(settings.topic, timeout=15)
        topic_meta = metadata.topics.get(settings.topic)
        if topic_meta is None or topic_meta.error is not None:
            raise RuntimeError(f"topic {settings.topic} not found on the cluster")

        if not reset:
            report.add(
                "Confluent Cloud",
                True,
                f"reachable, {len(topic_meta.partitions)} partition(s), "
                "backlog left in place",
            )
            return

        # Mark everything currently on the topic as already consumed, so the
        # demo only sees what it produces. Messages are not deleted.
        commits = []
        total = 0
        for partition_id in topic_meta.partitions:
            partition = TopicPartition(settings.topic, partition_id)
            _low, high = consumer.get_watermark_offsets(
                partition, timeout=10, cached=False
            )
            total += int(high)
            commits.append(TopicPartition(settings.topic, partition_id, int(high)))
        if commits:
            consumer.commit(offsets=commits, asynchronous=False)
        report.add(
            "Confluent Cloud",
            True,
            f"reachable, ingestion group advanced past {total} existing "
            f"event(s) on {len(commits)} partition(s)",
        )
    except Exception as exc:
        os.environ["CONFLUENT_MOCK"] = "true"
        report.add(
            "Confluent Cloud",
            True,
            f"unavailable ({str(exc)[:80]}), switched to in-process mock",
            degraded=True,
        )
    finally:
        if consumer is not None:
            try:
                consumer.close()
            except Exception:
                pass


def _prepare_databricks(report: PrepReport, reset: bool) -> None:
    """Verify Databricks, warm the warehouse, and reset the demo tables."""
    from module9.config.settings import DatabricksSettings, is_mock_databricks

    settings = DatabricksSettings()

    if is_mock_databricks():
        report.add("Databricks", True, "in-process mock, Delta tables reset")
        return

    lakehouse = None
    try:
        from module9.ingestion.delta_writer import DatabricksLakehouse

        lakehouse = DatabricksLakehouse(settings)
        lakehouse.ensure_tables()  # also warms the warehouse
        if reset:
            versions = lakehouse.truncate_tables()
            report.add(
                "Databricks",
                True,
                f"warehouse warm, tables truncated "
                f"(bronze v{versions['bronze_version']}, "
                f"silver v{versions['silver_version']})",
            )
        else:
            report.add("Databricks", True, "warehouse warm, tables left in place")
    except Exception as exc:
        os.environ["DATABRICKS_MOCK"] = "true"
        report.add(
            "Databricks",
            True,
            f"unavailable ({str(exc)[:80]}), switched to in-process mock",
            degraded=True,
        )
    finally:
        if lakehouse is not None:
            try:
                lakehouse.close()
            except Exception:
                pass


def _prepare_knowledge_sink(report: PrepReport) -> None:
    """Resolve the knowledge sink and report which backend is active.

    resolve_sink degrades on its own, so this only has to report the outcome.
    A knowledge base id that is set but unreachable shows as degraded.
    """
    from module9.config.settings import KnowledgeBaseSettings
    from module9.ingestion.kb_sink import BACKEND_BEDROCK_KB, resolve_sink

    configured = KnowledgeBaseSettings().configured
    try:
        info = resolve_sink().info()
    except Exception as exc:
        report.add("Knowledge sink", False, f"could not resolve: {str(exc)[:90]}")
        return

    degraded = configured and info.backend != BACKEND_BEDROCK_KB
    detail = info.detail
    if degraded:
        detail = f"knowledge base unreachable, fell back to {info.detail}"
    report.add(
        "Knowledge sink",
        True,
        f"{info.display_name or info.backend}: {detail}",
        degraded=degraded,
    )


def _purge_knowledge_base(report: PrepReport) -> None:
    """Remove pipeline-authored documents from the knowledge base.

    Unlike the in-process mock, a real knowledge base persists between runs.
    Left alone it accumulates every rehearsal's chunks, and the agent starts
    citing a previous run's Kafka offset and Delta version, which then
    contradicts the provenance panel. Only documents using this pipeline's
    id convention are removed, in batches, so anything else living in the
    knowledge base is untouched.
    """
    from module9.config.settings import KnowledgeBaseSettings
    from module9.ingestion.kb_sink import BACKEND_BEDROCK_KB, resolve_sink

    try:
        if resolve_sink().info().backend != BACKEND_BEDROCK_KB:
            return
    except Exception:
        return

    settings = KnowledgeBaseSettings()
    try:
        import boto3

        client = boto3.Session(region_name=settings.region).client("bedrock-agent")
        identifiers = []
        token = None
        while True:
            kwargs = {
                "knowledgeBaseId": settings.knowledge_base_id,
                "dataSourceId": settings.data_source_id,
                "maxResults": 100,
            }
            if token:
                kwargs["nextToken"] = token
            page = client.list_knowledge_base_documents(**kwargs)
            for detail in page.get("documentDetails", []):
                doc_id = (
                    detail.get("identifier", {}).get("custom", {}).get("id", "")
                )
                if doc_id.startswith("kb-"):
                    identifiers.append(
                        {"dataSourceType": "CUSTOM", "custom": {"id": doc_id}}
                    )
            token = page.get("nextToken")
            if not token:
                break

        if not identifiers:
            report.add("Knowledge base reset", True, "no pipeline documents to remove")
            return

        for start in range(0, len(identifiers), 25):  # API accepts 25 per call
            client.delete_knowledge_base_documents(
                knowledgeBaseId=settings.knowledge_base_id,
                dataSourceId=settings.data_source_id,
                documentIdentifiers=identifiers[start : start + 25],
            )
        report.add(
            "Knowledge base reset",
            True,
            f"removed {len(identifiers)} document(s) from the previous run",
        )
    except Exception as exc:
        report.add(
            "Knowledge base reset",
            False,
            f"could not purge documents ({str(exc)[:80]}); the demo will run but "
            "may retrieve chunks from an earlier run",
        )


def seed_corpora_and_wait(
    report: PrepReport | None = None, timeout: float = 120.0
) -> None:
    """Load the seed corpora and wait until they are actually retrievable.

    A real knowledge base indexes asynchronously, a few seconds in practice.
    Section 1 asks its question immediately, so seeding has to complete
    before the demo starts rather than racing it. Doing this during
    preparation also means the wait happens while nobody is watching.
    """
    import time

    from module9.ingestion.kb_sink import BACKEND_BEDROCK_KB, resolve_sink
    from module9.ingestion.load import load_seed_corpora

    results = load_seed_corpora()
    loaded = [r for r in results if r.action == "stored"]

    try:
        sink = resolve_sink()
        backend = sink.info().backend
    except Exception as exc:
        if report:
            report.add("Seed corpora", False, f"sink unavailable: {str(exc)[:80]}")
        return

    if backend != BACKEND_BEDROCK_KB or not loaded:
        if report:
            report.add(
                "Seed corpora",
                True,
                f"{len(loaded)} chunk(s) loaded across service, policy, history",
            )
        return

    target = next(
        (
            r.doc_id
            for r in loaded
            if (r.metadata or {}).get("corpus") == "history"
        ),
        loaded[0].doc_id,
    )
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            if sink.search("checkout-api deployment", {"doc_id": target}, 5):
                if report:
                    report.add(
                        "Seed corpora",
                        True,
                        f"{len(loaded)} chunk(s) loaded and retrievable after "
                        f"{round(time.monotonic() - started, 1)}s",
                    )
                return
        except Exception:
            pass
        time.sleep(3)

    if report:
        report.add(
            "Seed corpora",
            False,
            f"{len(loaded)} chunk(s) loaded but not retrievable within "
            f"{int(timeout)}s; section 1 may show an empty knowledge base",
        )


def _warm_bedrock(report: PrepReport) -> None:
    """Warm the Amazon Bedrock calls the demo actually makes.

    Sections 1 and 9 invoke the chat model, which is the call with a
    noticeable cold start, so warm that first. Embeddings are only warmed
    when this pipeline is the one embedding: a managed knowledge base does
    its own embedding, and under AGENT_MOCK_MEMORY the vector is computed
    locally, so in neither case is there an endpoint to warm.
    """
    from module9.config.settings import is_mock_memory

    warmed: list[str] = []
    skipped: list[str] = []

    try:
        from module9.config.models import get_chat_bedrock_model

        get_chat_bedrock_model().invoke([("user", "Reply with the word ready.")])
        warmed.append("chat model")
    except Exception as exc:
        report.add(
            "Amazon Bedrock", False, f"chat model warm-up failed: {str(exc)[:90]}"
        )
        return

    embeds_here = False
    try:
        from module9.ingestion.kb_sink import resolve_sink

        info = resolve_sink().info()
        embeds_here = not info.embeds_internally
        if info.embeds_internally:
            skipped.append("embeddings owned by the knowledge base")
    except Exception:
        embeds_here = True

    if embeds_here and is_mock_memory():
        skipped.append("embeddings computed locally under AGENT_MOCK_MEMORY")
    elif embeds_here:
        try:
            from module9.ingestion.embed import embed_chunk

            embed_chunk("Module 9 warm up call for the embedding endpoint.")
            warmed.append("Amazon Titan embeddings")
        except Exception as exc:
            report.add(
                "Amazon Bedrock",
                False,
                f"embedding warm-up failed: {str(exc)[:90]}",
            )
            return

    detail = f"{', '.join(warmed)} warm"
    if skipped:
        detail += f"; {', '.join(skipped)}"
    report.add("Amazon Bedrock", True, detail)


def recreate_topic(report: PrepReport) -> None:
    """Delete and recreate the topic so offsets restart at zero.

    Opt-in, for use before a final recording when tidy offset numbers matter
    in the narration. Destructive: every message on the topic is discarded.
    Deletion and creation are asynchronous in Kafka, so this waits for the
    topic to come back before returning. Falls back to leaving the topic
    alone if anything goes wrong.
    """
    import time

    from module9.config.settings import ConfluentSettings, is_mock_confluent

    settings = ConfluentSettings()

    if is_mock_confluent():
        from module9.mock import confluent_mock

        confluent_mock.reset()
        report.add("Topic reset", True, "in-process topic cleared, offsets at 0")
        return

    try:
        from confluent_kafka.admin import (  # type: ignore[import]
            AdminClient,
            NewTopic,
        )

        admin = AdminClient(settings.client_config())
        existing = admin.list_topics(timeout=15).topics
        partitions = 1
        if settings.topic in existing:
            partitions = max(1, len(existing[settings.topic].partitions))
            for _topic, future in admin.delete_topics([settings.topic]).items():
                future.result(timeout=60)
            # Deletion propagates asynchronously; wait for it to disappear.
            for _ in range(30):
                if settings.topic not in admin.list_topics(timeout=10).topics:
                    break
                time.sleep(2)

        for _topic, future in admin.create_topics(
            [NewTopic(settings.topic, num_partitions=partitions, replication_factor=3)]
        ).items():
            future.result(timeout=60)

        # Wait until the new topic is describable before anyone produces.
        for _ in range(30):
            meta = admin.list_topics(timeout=10).topics.get(settings.topic)
            if meta is not None and meta.error is None:
                break
            time.sleep(2)

        report.add(
            "Topic reset",
            True,
            f"{settings.topic} recreated with {partitions} partition(s), "
            "offsets restart at 0",
        )
    except Exception as exc:
        report.add(
            "Topic reset",
            False,
            f"could not recreate {settings.topic} ({str(exc)[:70]}); "
            "continuing with the existing topic and a backlog skip",
        )


def prepare_environment(
    reset: bool = True, warm: bool = True, fresh_topic: bool = False
) -> PrepReport:
    """Prepare the demo environment. Safe to call on every run.

    Parameters
    ----------
    reset : bool
        Skip the topic backlog and truncate the demo Delta tables. Set False
        to leave partner state untouched.
    warm : bool
        Make a small Bedrock call to avoid a cold start on stage.
    fresh_topic : bool
        Delete and recreate the Kafka topic so offsets restart at zero.
        Destructive and slower; intended for a final recording.
    """
    report = PrepReport()
    _clear_process_state()
    _reset_mock_partners()
    if fresh_topic:
        recreate_topic(report)
    _prepare_confluent(report, reset)
    _prepare_databricks(report, reset)
    _prepare_knowledge_sink(report)
    if reset:
        _purge_knowledge_base(report)
    seed_corpora_and_wait(report)
    if warm:
        _warm_bedrock(report)
    return report
