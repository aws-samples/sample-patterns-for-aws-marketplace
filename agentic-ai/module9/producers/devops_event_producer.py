# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/producers/devops_event_producer.py
============================================
Act 1: produce a DevOps event (deployment or incident record) to the
Confluent Kafka topic devops-events.

The live path uses the confluent-kafka Producer against Confluent Cloud
with SASL_SSL cluster credentials. Under AGENT_MOCK_PIPELINE=true the
producer writes to the in-process mock topic with the same produce()
surface, so this file's logic is identical in both modes.

CLI usage (mock):
    AGENT_MOCK_PIPELINE=true python -m module9.producers.devops_event_producer
    AGENT_MOCK_PIPELINE=true python -m module9.producers.devops_event_producer \
        --event-type incident
"""
from __future__ import annotations

import argparse
import json

from module9.config.settings import ConfluentSettings, is_mock_confluent
from module9.mock.sample_events import deployment_event, incident_event


def get_producer(settings: ConfluentSettings | None = None):
    """Return a Kafka producer: confluent-kafka live, or the mock."""
    settings = settings or ConfluentSettings()
    if is_mock_confluent():
        from module9.mock.confluent_mock import MockProducer

        return MockProducer({"client.id": "module9-producer"})

    settings.validate_for_live()
    from confluent_kafka import Producer  # type: ignore[import]

    return Producer(settings.client_config())


def produce_event(
    event: dict | None = None,
    settings: ConfluentSettings | None = None,
) -> dict:
    """Produce one event to the devops-events topic.

    Returns a delivery report dict: topic, partition, offset, and the
    event payload. The (topic, offset) pair is the Confluent provenance
    anchor that rides on every chunk produced from this event.
    """
    settings = settings or ConfluentSettings()
    event = event or deployment_event()
    producer = get_producer(settings)

    report: dict = {}

    def _on_delivery(err, msg) -> None:
        if err is not None:
            raise RuntimeError(f"Delivery failed: {err}")
        report.update(
            {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
            }
        )

    producer.produce(
        settings.topic,
        value=json.dumps(event),
        key=str(event.get("service") or event.get("incident_id") or "devops"),
        on_delivery=_on_delivery,
    )
    producer.poll(0)
    producer.flush(10)

    report["event"] = event
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce a DevOps event to the Confluent devops-events topic."
    )
    parser.add_argument(
        "--event-type",
        choices=["deployment", "incident"],
        default="deployment",
        help="Which sample event to produce (default: deployment).",
    )
    args = parser.parse_args()

    event = deployment_event() if args.event_type == "deployment" else incident_event()
    report = produce_event(event)
    mode = "mock" if is_mock_confluent() else "live"
    print(
        f"Produced {args.event_type} event to {report['topic']} "
        f"partition {report['partition']} offset {report['offset']} ({mode})"
    )


if __name__ == "__main__":
    main()
