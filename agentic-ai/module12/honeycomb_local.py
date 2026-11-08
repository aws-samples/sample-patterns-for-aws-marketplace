"""Local Honeycomb-style investigation over Module 12 spans.

This module does not emulate Honeycomb's storage or query engine. It preserves
the parts of the demo story that matter locally: wide structured events,
high-cardinality filtering, population comparison, and behavioral investigation.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_COMPARISON_FIELDS = (
    "workflow.scenario",
    "policy.rule",
    "session.tainted",
    "snyk.posture",
    "companion.posture",
    "security.review.status",
    "financial.approval.status",
    "deployment.environment",
    "tool.manifest.digest",
    "harness.digest",
)


def _policy_context(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    response = outcome.get("response", {})
    if not isinstance(response, Mapping):
        return {}
    policy = response.get("policy", {})
    if not isinstance(policy, Mapping):
        return {}
    context = policy.get("context", {})
    return context if isinstance(context, Mapping) else {}


def _common_fields(outcome: Mapping[str, Any]) -> dict[str, Any]:
    response = outcome.get("response", {})
    if not isinstance(response, Mapping):
        response = {}
    context = _policy_context(outcome)
    return {
        "workflow.id": outcome.get("workflow_id"),
        "workflow.scenario": outcome.get("scenario"),
        "workflow.status": outcome.get("status"),
        "session.id": outcome.get("session_id"),
        "companion.posture": response.get("companion_posture"),
        "snyk.posture": response.get("snyk_posture"),
        "security.review.status": context.get("security_review"),
        "financial.approval.status": context.get("financial_approval"),
        "artifact.digest": response.get("artifact_digest"),
        "tool.manifest.digest": response.get("tool_manifest_digest"),
        "harness.digest": response.get("harness_digest"),
        "deployment.environment": context.get("environment"),
        "deployment.invocation_recorded": bool(
            outcome.get("mutation_recorded", False)
        ),
        "smoke_test.status": outcome.get("smoke_test_status"),
        "content.exported": False,
    }


@dataclass(frozen=True)
class LocalHoneycombDataset:
    """A collection of span events with Honeycomb-like operations."""

    events: tuple[dict[str, Any], ...]

    @classmethod
    def from_outcomes(
        cls,
        outcomes: Iterable[Mapping[str, Any]],
    ) -> "LocalHoneycombDataset":
        events: list[dict[str, Any]] = []
        for outcome in outcomes:
            common = _common_fields(outcome)
            spans = [
                span
                for span in outcome.get("spans", [])
                if isinstance(span, Mapping)
            ]
            spans.sort(key=lambda span: int(span.get("start_time_ns") or 0))
            for sequence, span in enumerate(spans, start=1):
                attributes = span.get("attributes", {})
                event = dict(attributes) if isinstance(attributes, Mapping) else {}
                for key, value in common.items():
                    if value is not None:
                        event.setdefault(key, value)
                event.update(
                    {
                        "name": span.get("name"),
                        "span.sequence": sequence,
                        "span.status": span.get("status"),
                        "span.duration_ms": float(span.get("duration_ms") or 0),
                    }
                )
                events.append(event)
        return cls(tuple(events))

    @property
    def trace_count(self) -> int:
        return len(
            {
                event.get("workflow.id")
                for event in self.events
                if event.get("workflow.id")
            }
        )

    @property
    def field_count(self) -> int:
        return len({key for event in self.events for key in event})

    def where(self, **filters: Any) -> list[dict[str, Any]]:
        return [
            event
            for event in self.events
            if all(event.get(key) == value for key, value in filters.items())
        ]

    @staticmethod
    def counts(
        field: str,
        events: Sequence[Mapping[str, Any]],
    ) -> Counter[Any]:
        return Counter(
            event.get(field)
            for event in events
            if event.get(field) is not None
        )

    def compare_populations(
        self,
        focus: Sequence[Mapping[str, Any]],
        baseline: Sequence[Mapping[str, Any]],
        *,
        fields: Sequence[str] = DEFAULT_COMPARISON_FIELDS,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return values overrepresented in focus versus baseline events."""

        if not focus:
            return []
        focus_total = len(focus)
        baseline_total = len(baseline)
        rows: list[dict[str, Any]] = []
        for field in fields:
            focus_counts = self.counts(field, focus)
            baseline_counts = self.counts(field, baseline)
            for value, focus_count in focus_counts.items():
                focus_share = focus_count / focus_total
                baseline_share = (
                    baseline_counts[value] / baseline_total
                    if baseline_total
                    else 0.0
                )
                delta = focus_share - baseline_share
                if delta <= 0:
                    continue
                rows.append(
                    {
                        "field": field,
                        "value": value,
                        "focus_count": focus_count,
                        "focus_share": focus_share,
                        "baseline_share": baseline_share,
                        "delta": delta,
                    }
                )
        rows.sort(
            key=lambda row: (
                -float(row["delta"]),
                -int(row["focus_count"]),
                str(row["field"]),
                str(row["value"]),
            )
        )
        return rows[:limit]
