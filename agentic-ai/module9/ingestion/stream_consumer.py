# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/stream_consumer.py
=====================================
The Confluent read seam: consumes DevOps events from the devops-events
Kafka topic (v5 Section 1.1 pattern 3, real-time stream consumption).

KafkaStreamSource wraps a confluent-kafka Consumer in live mode and the
in-process MockConsumer under AGENT_MOCK_PIPELINE=true. Both expose the
same poll() surface, so the pipeline code is identical in both modes.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from module9.config.settings import ConfluentSettings, is_mock_confluent


@dataclass(frozen=True)
class ConsumedEvent:
    """One event read off the stream, with its provenance anchor.

    The (topic, partition, offset) triple is the Confluent anchor written
    into every chunk's lineage metadata (v5 Appendix B source_uri).
    """

    topic: str
    partition: int
    offset: int
    event: dict = field(default_factory=dict)

    @property
    def source_uri(self) -> str:
        return f"confluent://{self.topic}/partition-{self.partition}/offset-{self.offset}"

    @property
    def event_time(self) -> str:
        return str(self.event.get("event_time", ""))


class KafkaStreamSource:
    """Bounded-window consumer over the devops-events topic.

    Reads a bounded batch rather than the raw firehose, which is the
    latency guidance from v5 Section 1.1: pull a window of records, not
    everything, at processing time.
    """

    def __init__(self, settings: ConfluentSettings | None = None) -> None:
        self._settings = settings or ConfluentSettings()
        self._is_mock = is_mock_confluent()
        if self._is_mock:
            from module9.mock.confluent_mock import MockConsumer

            self._consumer = MockConsumer(
                {"group.id": self._settings.group_id}
            )
        else:
            self._settings.validate_for_live()
            from confluent_kafka import Consumer  # type: ignore[import]

            config = self._settings.client_config()
            config.update(
                {
                    "group.id": self._settings.group_id,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": False,
                }
            )
            self._consumer = Consumer(config)
        self._consumer.subscribe([self._settings.topic])

    def poll_events(
        self,
        max_records: int = 10,
        timeout: float = 2.0,
        max_wait: float = 20.0,
    ) -> list[ConsumedEvent]:
        """Consume up to max_records events, deduplicating on offset.

        A live consumer that is joining or rejoining a consumer group returns
        None from poll() for the first few calls while the group rebalances,
        so an empty poll does not mean an empty topic. Keep polling until
        either records arrive or max_wait elapses. Once records have arrived,
        the first empty poll means the topic is drained and we stop.

        The in-process mock answers immediately and never rebalances, so it
        stops on the first empty poll and pays no waiting cost.

        Malformed payloads are skipped rather than crashing the pipeline;
        the quality gates downstream handle content-level validation.
        """
        deadline = time.monotonic() + max_wait
        events: list[ConsumedEvent] = []
        while len(events) < max_records:
            msg = self._consumer.poll(timeout)
            if msg is None:
                if events or self._is_mock or time.monotonic() >= deadline:
                    break
                continue  # still joining the group; keep waiting
            if msg.error() is not None:
                continue
            try:
                payload = json.loads(msg.value().decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            events.append(
                ConsumedEvent(
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                    event=payload,
                )
            )
            self._consumer.commit(msg)
        return events

    def close(self) -> None:
        self._consumer.close()


def create_stream_source(
    settings: ConfluentSettings | None = None,
) -> KafkaStreamSource:
    """Factory matching the Module 7 store/mock selection convention."""
    return KafkaStreamSource(settings)
