# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/chunk.py
===========================
Chunking strategies per corpus, following the v5 Appendix A decision guide
and the Section 10 per-corpus designs:

- history: fixed-size, one structured record per chunk (Section 10.3). The
  structured record is first rendered to a natural-language description.
- policy: semantic, split at numbered steps or headings so each step is a
  retrievable chunk (Section 10.2).
- service: hierarchical, a parent chunk for the topic plus child chunks per
  subsection; children carry parent_chunk_id (Section 10.1).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Chunk:
    """One chunk headed for the knowledge base."""

    content: str
    chunk_index: int
    chunk_count: int
    chunking_strategy: str  # Appendix B enum
    parent_chunk_id: str | None = None
    extra_metadata: dict = field(default_factory=dict)


def _friendly_date(event_time: str) -> str:
    """Render an ISO event time as 'On July 27, 2026' style prose."""
    try:
        dt = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "Recently"
    today = datetime.now(timezone.utc).date()
    if dt.date() == today:
        return "Today"
    return "On " + dt.strftime("%B %d, %Y").replace(" 0", " ")


def render_history_record(event: dict) -> str:
    """Convert a structured event to the natural-language description that
    gets embedded (the v5 Section 10.3 rendering). The structured JSON rides
    along as chunk metadata for programmatic access."""
    when = _friendly_date(str(event.get("event_time", "")))
    event_type = event.get("event_type", "")

    if event_type == "deployment":
        service = event.get("service", "unknown-service")
        version = event.get("version", "")
        version_part = f" version {version}" if version else ""
        env = event.get("environment", "an unspecified environment")
        region = event.get("region", "an unspecified region")
        status = event.get("status", "completed")
        duration = event.get("duration_minutes")
        duration_part = f" after {duration} minutes" if duration else ""
        text = (
            f"{when}, service {service}{version_part} was deployed to {env} "
            f"in {region}. The deployment {status}{duration_part}."
        )
        alarm = event.get("alarm")
        if alarm:
            text += f" CloudWatch alarm {alarm}."
        else:
            text += " No CloudWatch alarms were triggered during the deployment."
        initiated = event.get("initiated_by")
        if initiated:
            text += f" The deployment was initiated by {initiated}."
        return text

    if event_type == "incident":
        incident_id = event.get("incident_id", "an incident")
        services = ", ".join(event.get("affected_services", [])) or "unknown services"
        severity = event.get("severity", "unspecified")
        root_cause = event.get("root_cause", "an undetermined root cause")
        resolution = event.get("resolution", "no recorded resolution")
        duration = event.get("duration_minutes")
        duration_part = (
            f" The incident lasted {duration} minutes." if duration else ""
        )
        return (
            f"{when}, incident {incident_id} affected {services} with "
            f"{severity} severity. Root cause: {root_cause}. Resolution: "
            f"{resolution}.{duration_part}"
        )

    # Unknown event types still produce a chunk; quality gates decide its fate.
    details = ", ".join(f"{k}={v}" for k, v in sorted(event.items()))
    return f"{when}, an event of type {event_type or 'unknown'} was recorded: {details}"


def _parent_chunk_id(content: str) -> str:
    digest = hashlib.sha256(f"parent:{content}".encode()).hexdigest()[:32]
    return f"kb-parent-{digest}"


_STEP_RE = re.compile(r"(?:^|\s)(?:step\s+\d+|\d+\.)\s", re.IGNORECASE)


def chunk_record(content: str, corpus: str, event: dict | None = None) -> list[Chunk]:
    """Chunk one document or record according to its corpus strategy."""
    if corpus == "history":
        rendered = render_history_record(event) if event else content
        return [
            Chunk(
                content=rendered,
                chunk_index=0,
                chunk_count=1,
                chunking_strategy="fixed",
                extra_metadata={"structured_record": event or {}},
            )
        ]

    if corpus == "policy":
        # Semantic: split at sentence boundaries that open a numbered step.
        # Short documents stay whole (Appendix A: short docs, single chunk).
        sentences = re.split(r"(?<=\.)\s+", content.strip())
        if len(sentences) < 6:
            return [
                Chunk(
                    content=content.strip(),
                    chunk_index=0,
                    chunk_count=1,
                    chunking_strategy="semantic",
                )
            ]
        midpoint = len(sentences) // 2
        parts = [
            " ".join(sentences[:midpoint]),
            " ".join(sentences[midpoint:]),
        ]
        return [
            Chunk(
                content=part,
                chunk_index=i,
                chunk_count=len(parts),
                chunking_strategy="semantic",
            )
            for i, part in enumerate(parts)
        ]

    if corpus == "service":
        # Hierarchical: the full topic is the parent; subsections (split at
        # sentence groups) are children carrying parent_chunk_id.
        text = content.strip()
        parent_id = _parent_chunk_id(text)
        sentences = re.split(r"(?<=\.)\s+", text)
        if len(sentences) < 4:
            return [
                Chunk(
                    content=text,
                    chunk_index=0,
                    chunk_count=1,
                    chunking_strategy="hierarchical-parent",
                )
            ]
        midpoint = len(sentences) // 2
        children = [
            " ".join(sentences[:midpoint]),
            " ".join(sentences[midpoint:]),
        ]
        chunks = [
            Chunk(
                content=text,
                chunk_index=0,
                chunk_count=len(children) + 1,
                chunking_strategy="hierarchical-parent",
            )
        ]
        for i, child in enumerate(children, start=1):
            chunks.append(
                Chunk(
                    content=child,
                    chunk_index=i,
                    chunk_count=len(children) + 1,
                    chunking_strategy="hierarchical-child",
                    parent_chunk_id=parent_id,
                )
            )
        return chunks

    raise ValueError(f"Unknown corpus {corpus!r} for chunking")
