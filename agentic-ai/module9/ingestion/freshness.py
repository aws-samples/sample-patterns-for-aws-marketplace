# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/freshness.py
===============================
Per-corpus freshness verdicts (v5 Sections 3 and 9.2).

A corpus is fresh when its newest chunk is younger than the corpus
freshness SLA. The SLA encodes the refresh strategy: event-driven for
policy, nightly for history, weekly for service. An empty corpus is
reported as stale with an explanation, which is what powers the
stale-agent beat in the demo.
"""
from __future__ import annotations

from datetime import datetime, timezone

from module9.config.corpora import CORPORA, get_corpus
from module9.ingestion.lineage import get_registry

STATUS_FRESH = "fresh"
STATUS_STALE = "stale"
STATUS_EMPTY = "empty"

_REFRESH_STRATEGY = {
    "service": "scheduled weekly full refresh with incremental hash-based skip",
    "policy": "event-driven refresh, under 10 minutes of lag",
    "history": "event-driven streaming ingest plus nightly consolidation sync",
}


def _parse_ts(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def check_freshness(corpus: str, now: datetime | None = None) -> dict:
    """Return the freshness verdict for one corpus.

    The verdict compares the age of the newest chunk (by ingested_at)
    against the corpus SLA from config/corpora.py.
    """
    spec = get_corpus(corpus)
    now = now or datetime.now(timezone.utc)

    newest: datetime | None = None
    chunk_count = 0
    for _, meta in get_registry().chunks_for_corpus(corpus):
        chunk_count += 1
        ts = _parse_ts(str(meta.get("ingested_at", "")))
        if ts and (newest is None or ts > newest):
            newest = ts

    if newest is None:
        return {
            "corpus": corpus,
            "status": STATUS_EMPTY,
            "chunk_count": 0,
            "newest_chunk_age_hours": None,
            "sla_hours": spec.freshness_sla_hours,
            "refresh_strategy": _REFRESH_STRATEGY.get(corpus, ""),
            "detail": "No chunks loaded; treat as stale until first ingest.",
        }

    age_hours = round((now - newest).total_seconds() / 3600.0, 3)
    status = STATUS_FRESH if age_hours <= spec.freshness_sla_hours else STATUS_STALE
    return {
        "corpus": corpus,
        "status": status,
        "chunk_count": chunk_count,
        "newest_chunk_age_hours": age_hours,
        "sla_hours": spec.freshness_sla_hours,
        "refresh_strategy": _REFRESH_STRATEGY.get(corpus, ""),
        "detail": (
            f"Newest chunk is {age_hours} hours old against an SLA of "
            f"{spec.freshness_sla_hours} hours."
        ),
    }


def check_all_corpora(now: datetime | None = None) -> list[dict]:
    """Freshness verdicts for all three corpora (the dashboard view)."""
    return [check_freshness(name, now) for name in CORPORA]


def explain_staleness(corpus: str) -> dict:
    """Narrative explanation of a corpus's freshness state, for the agent."""
    verdict = check_freshness(corpus)
    spec = get_corpus(corpus)
    if verdict["status"] == STATUS_FRESH:
        explanation = (
            f"The {corpus} corpus is fresh: its newest chunk is "
            f"{verdict['newest_chunk_age_hours']} hours old, within the "
            f"{spec.freshness_sla_hours}-hour SLA. Refresh strategy: "
            f"{verdict['refresh_strategy']}."
        )
    elif verdict["status"] == STATUS_EMPTY:
        explanation = (
            f"The {corpus} corpus has no chunks loaded in this environment. "
            f"Any answer drawn from it would be unsupported. Run the "
            f"ingestion pipeline to populate it. Refresh strategy: "
            f"{verdict['refresh_strategy']}."
        )
    else:
        explanation = (
            f"The {corpus} corpus is STALE: its newest chunk is "
            f"{verdict['newest_chunk_age_hours']} hours old, beyond the "
            f"{spec.freshness_sla_hours}-hour SLA. Answers from this corpus "
            f"may cite outdated state and should be qualified. Refresh "
            f"strategy: {verdict['refresh_strategy']}."
        )
    verdict["explanation"] = explanation
    return verdict
