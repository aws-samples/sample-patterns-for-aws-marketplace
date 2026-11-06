"""Normalization and Honeycomb navigation helpers for Module 12 telemetry."""
from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.parse import quote, urlencode, urlsplit, urlunsplit


def _decode(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def normalize_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    outcome = _decode(item.get("outcome", {}))
    response = outcome.get("response", {}) if isinstance(outcome, dict) else {}
    policy = response.get("policy", {}) if isinstance(response, dict) else {}
    telemetry = (
        response.get("telemetry", {}) if isinstance(response, dict) else {}
    )
    return {
        "workflow_id": outcome.get("workflow_id"),
        "session_id": outcome.get("session_id"),
        "scenario": outcome.get("scenario"),
        "status": outcome.get("status"),
        "policy_decision": policy.get("decision"),
        "policy_rule": policy.get("rule"),
        "session_tainted": policy.get("context", {}).get("session_tainted"),
        "companion_posture": response.get("companion_posture"),
        "snyk_posture": response.get("snyk_posture"),
        "artifact_digest": response.get("artifact_digest"),
        "smoke_test": response.get("smoke_test"),
        "mutation_recorded": outcome.get("mutation_recorded"),
        "honeycomb_export_enabled": telemetry.get(
            "honeycomb_export_enabled"
        ),
        "honeycomb_export": telemetry.get("honeycomb_export"),
    }


def honeycomb_investigation_link(
    *,
    dataset: str,
    base_url: str | None = None,
) -> str | None:
    base_url = base_url or os.environ.get("MODULE12_HONEYCOMB_UI_URL")
    if not base_url or not dataset:
        return None
    return base_url.rstrip("/")


def honeycomb_query_template_link(
    *,
    dataset: str,
    query: Mapping[str, Any],
    base_url: str | None = None,
) -> str | None:
    """Build a Honeycomb Query Template link for a pre-populated query."""

    base_url = base_url or os.environ.get("MODULE12_HONEYCOMB_UI_URL")
    if not base_url or not dataset:
        return None

    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        return None

    segments = [segment for segment in parsed.path.split("/") if segment]
    if "environments" in segments:
        environment_index = segments.index("environments")
        if environment_index + 1 >= len(segments):
            return None
        segments = segments[: environment_index + 2]
    elif "datasets" in segments:
        segments = segments[: segments.index("datasets")]

    environment_path = "/" + "/".join(segments)
    query_json = json.dumps(query, separators=(",", ":"), ensure_ascii=False)
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{environment_path}/datasets/{quote(dataset, safe='')}/",
            urlencode({"query": query_json}),
            "",
        )
    )
