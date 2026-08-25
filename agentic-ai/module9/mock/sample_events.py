# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/mock/sample_events.py
==============================
Deterministic, relative-dated DevOps events for the mock pipeline.

Timestamps are computed relative to the current date (the
mongo_mock._ts(days_ago) convention) so the history corpus always looks
current no matter when the demo runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _ts(days_ago: int, hour: int = 14, minute: int = 2, second: int = 11) -> str:
    """Return an ISO 8601 UTC timestamp N days ago at the given time."""
    dt = datetime.now(timezone.utc).replace(
        hour=hour, minute=minute, second=second, microsecond=0
    ) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def deployment_event() -> dict:
    """The Act 1 default: a production deployment record for checkout-api."""
    return {
        "event_type": "deployment",
        "service": "checkout-api",
        "version": "v2.4.0",
        "environment": "production",
        "region": "us-east-1",
        "status": "succeeded",
        "duration_minutes": 12,
        "alarm": (
            "checkout-api-5xx-error-rate triggered, resolved after traffic "
            "stabilization"
        ),
        "initiated_by": "release-pipeline",
        "event_time": _ts(0, 14, 2, 11),
    }


def followup_deployment_event() -> dict:
    """A later, distinct deployment for the full-loop beat.

    Distinct content, so it is genuinely new knowledge rather than a
    content-hash duplicate of the earlier event. This keeps the end-to-end
    section honest: a new release ships, the pipeline ingests it, and the
    agent's answer changes.
    """
    return {
        "event_type": "deployment",
        "service": "checkout-api",
        "version": "v2.4.1",
        "environment": "production",
        "region": "us-east-1",
        "status": "succeeded",
        "duration_minutes": 8,
        "alarm": None,
        "initiated_by": "release-pipeline",
        "event_time": _ts(0, 16, 47, 3),
    }


def incident_event() -> dict:
    """The alternate event: a resolved incident record."""
    return {
        "event_type": "incident",
        "incident_id": "INC-2043",
        "affected_services": ["checkout-api", "payments-gateway"],
        "severity": "high",
        "root_cause": "connection pool exhaustion after deploy",
        "resolution": "raised pool size, added circuit breaker",
        "duration_minutes": 38,
        "event_time": _ts(0, 15, 20, 0),
    }


def pii_deployment_event() -> dict:
    """A deployment event whose notes contain PII, for the write-path
    guardrail beat: the on-call engineer's email must be anonymized before
    the record reaches the knowledge base."""
    event = deployment_event()
    event["alarm"] = (
        "checkout-api-5xx-error-rate triggered; on-call jordan.lee@example.com "
        "acknowledged, resolved after traffic stabilization"
    )
    return event


def bad_event() -> dict:
    """A malformed event for the quality-gate beat: its rendered chunk falls
    below the 50-token minimum and must be rejected before embedding."""
    return {
        "event_type": "deployment",
        "service": "x",
        "environment": "",
        "region": "",
        "status": "",
        "event_time": _ts(0, 16, 0, 0),
    }
