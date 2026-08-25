# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/mock/seed_corpora_data.py
==================================
Tiny per-corpus seed documents so list_corpora and cross-corpus retrieval
return real content offline, and so the three-corpus story is complete
even though the live demo ingests only into the history corpus.

Timestamps are relative-dated. The history seed record is deliberately
old (an earlier checkout-api release) so Section 1's stale-agent beat has
outdated knowledge to answer from before the fresh event arrives.
"""
from __future__ import annotations

from module9.mock.sample_events import _ts

SEED_DOCS: list[dict] = [
    {
        "corpus": "service",
        "source_uri": "s3://kb-sources/service/docs/cloudwatch-alarms.md",
        "source_type": "Markdown",
        "source_modified": _ts(6, 0, 5, 0),
        "content": (
            "CloudWatch alarm configuration for ECS services. A 5xx error "
            "rate alarm should evaluate the sum of HTTPCode_Target_5XX_Count "
            "over three consecutive one-minute periods against a threshold "
            "derived from baseline traffic. Configure the alarm to notify the "
            "service's PagerDuty escalation via an SNS topic, and pair it "
            "with a deployment circuit breaker so ECS rolls back a deployment "
            "that trips the alarm during its bake window. For checkout-tier "
            "services, the recommended bake window is fifteen minutes."
        ),
    },
    {
        "corpus": "policy",
        "source_uri": "confluence://ops-space/runbooks/production-deployment",
        "source_type": "HTML",
        "source_modified": _ts(0, 9, 30, 0),
        "content": (
            "Production deployment runbook, step 4 of 7: monitor the release "
            "for one full bake window before declaring success. If any "
            "service alarm fires during the bake window, hold the release, "
            "capture the alarm context, and page the owning team. A release "
            "may be declared successful only after all triggered alarms have "
            "resolved and error rates have returned to the pre-deployment "
            "baseline. Record the outcome in the deployment log so the "
            "history corpus captures it for future retrieval."
        ),
    },
    {
        "corpus": "history",
        "source_uri": "confluent://devops-events/partition-0/offset-legacy-3899",
        "source_type": "structured-record",
        "source_modified": _ts(45, 11, 15, 0),
        "content": (
            "A while ago, service checkout-api version v1.18.2 was deployed "
            "to production in us-east-1. The deployment succeeded after 9 "
            "minutes. No CloudWatch alarms were triggered during the "
            "deployment. The release contained dependency upgrades and no "
            "customer-facing changes. This is the most recent checkout-api "
            "deployment on record prior to the current release cycle."
        ),
    },
]
