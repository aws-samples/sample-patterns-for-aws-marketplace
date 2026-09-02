# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/mock/confluent_mock.py
===============================
In-process Confluent Kafka mock for demo and test use.

MockProducer and MockConsumer expose the same produce()/poll() surface as
the confluent-kafka Producer and Consumer, so the calling code in
producers/ and ingestion/ is identical in mock and live mode. Events sit
in a module-level topic registry with monotonically increasing offsets on
a single synthetic partition, mirroring the ordering guarantee a real
Kafka partition provides.
"""
from __future__ import annotations

import json
import time

# Module-level topic registry: topic name -> ordered list of MockMessage.
_TOPICS: dict[str, list["MockMessage"]] = {}

# Consumer group offsets: (group_id, topic) -> next offset to read.
_GROUP_OFFSETS: dict[tuple[str, str], int] = {}


def reset() -> None:
    """Clear all topics and consumer group offsets (test isolation)."""
    _TOPICS.clear()
    _GROUP_OFFSETS.clear()


class MockMessage:
    """Mirrors the confluent_kafka.Message read surface."""

    def __init__(
        self,
        topic: str,
        partition: int,
        offset: int,
        value: bytes,
        key: bytes | None,
        timestamp_ms: int,
    ) -> None:
        self._topic = topic
        self._partition = partition
        self._offset = offset
        self._value = value
        self._key = key
        self._timestamp_ms = timestamp_ms

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset

    def value(self) -> bytes:
        return self._value

    def key(self) -> bytes | None:
        return self._key

    def timestamp(self) -> tuple[int, int]:
        # (timestamp_type, timestamp_ms); 1 = create time, as Kafka reports
        return (1, self._timestamp_ms)

    def error(self):
        return None


class MockProducer:
    """Mirrors the confluent_kafka.Producer write surface."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._pending: list = []

    def produce(
        self,
        topic: str,
        value: bytes | str,
        key: bytes | str | None = None,
        on_delivery=None,
    ) -> None:
        if isinstance(value, str):
            value = value.encode("utf-8")
        if isinstance(key, str):
            key = key.encode("utf-8")
        messages = _TOPICS.setdefault(topic, [])
        msg = MockMessage(
            topic=topic,
            partition=0,
            offset=len(messages),
            value=value,
            key=key,
            timestamp_ms=int(time.time() * 1000),
        )
        messages.append(msg)
        if on_delivery is not None:
            self._pending.append((on_delivery, msg))

    def poll(self, timeout: float = 0) -> int:
        """Fire pending delivery callbacks, as the real client does."""
        fired = 0
        while self._pending:
            callback, msg = self._pending.pop(0)
            callback(None, msg)
            fired += 1
        return fired

    def flush(self, timeout: float = 10) -> int:
        self.poll(0)
        return 0


class MockConsumer:
    """Mirrors the confluent_kafka.Consumer read surface."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}
        self._group_id = str(self._config.get("group.id", "module9-ingestion"))
        self._topics: list[str] = []

    def subscribe(self, topics: list[str]) -> None:
        self._topics = list(topics)

    def poll(self, timeout: float = 0) -> MockMessage | None:
        for topic in self._topics:
            messages = _TOPICS.get(topic, [])
            key = (self._group_id, topic)
            position = _GROUP_OFFSETS.get(key, 0)
            if position < len(messages):
                _GROUP_OFFSETS[key] = position + 1
                return messages[position]
        return None

    def commit(self, message: MockMessage | None = None, asynchronous: bool = True):
        return None  # offsets are advanced on poll in the mock

    def close(self) -> None:
        return None


def topic_depth(topic: str) -> int:
    """Number of events currently in a mock topic (demo display helper)."""
    return len(_TOPICS.get(topic, []))


def peek_topic(topic: str, last_n: int = 5) -> list[dict]:
    """Return the last N events in a topic as dicts (demo display helper)."""
    records = []
    for msg in _TOPICS.get(topic, [])[-last_n:]:
        try:
            payload = json.loads(msg.value().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {"raw": repr(msg.value())}
        records.append(
            {
                "partition": msg.partition(),
                "offset": msg.offset(),
                "value": payload,
            }
        )
    return records
