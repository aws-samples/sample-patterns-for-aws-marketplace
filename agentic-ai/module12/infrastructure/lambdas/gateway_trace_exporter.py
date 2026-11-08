"""Forward authoritative AgentCore Gateway policy spans to Honeycomb."""
from __future__ import annotations

import base64
import gzip
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Mapping

import boto3


EXPORTED_SPANS = frozenset(
    {
        "AgentCore.Gateway.InvokeTool",
        "AgentCore.Policy.AuthorizeAction",
    }
)


@lru_cache(maxsize=1)
def _ingest_key() -> str:
    secret_id = os.environ["HONEYCOMB_SECRET_ID"]
    response = boto3.client("secretsmanager").get_secret_value(
        SecretId=secret_id,
    )
    value = str(response.get("SecretString") or "").strip()
    if not value:
        raise ValueError("Honeycomb ingest key is empty")
    return value


def _event_time(start_time_unix_nano: Any) -> str:
    seconds = int(start_time_unix_nano or 0) / 1_000_000_000
    return (
        datetime.fromtimestamp(seconds, tz=timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _policy_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item)
        for item in value
        if isinstance(item, str) and not item.startswith("arn:")
    ]


def _honeycomb_event(message: Mapping[str, Any]) -> dict[str, Any] | None:
    name = str(message.get("name") or "")
    if name not in EXPORTED_SPANS:
        return None

    resource = message.get("resource")
    resource_attributes = (
        resource.get("attributes", {})
        if isinstance(resource, Mapping)
        else {}
    )
    gateway_arn = str(
        resource_attributes.get("cloud.resource_id") or ""
    )
    if gateway_arn != os.environ["AGENTCORE_GATEWAY_ARN"]:
        return None

    attributes = message.get("attributes")
    attributes = attributes if isinstance(attributes, Mapping) else {}
    status = message.get("status")
    status = status if isinstance(status, Mapping) else {}
    decision = attributes.get(
        "aws.agentcore.policy.authorization_decision"
    )
    data = {
        "name": name,
        "service.name": "devops-companion-agentcore-gateway",
        "meta.signal_type": "trace",
        "trace.trace_id": message.get("traceId"),
        "trace.span_id": message.get("spanId"),
        "trace.parent_id": message.get("parentSpanId"),
        "duration_ms": float(message.get("durationNano") or 0) / 1_000_000,
        "span.kind": str(message.get("kind") or "internal").lower(),
        "status_code": status.get("code"),
        "gateway.name": os.environ["AGENTCORE_GATEWAY_NAME"],
        "gateway.id": resource_attributes.get("service.name"),
        "gateway.action": attributes.get("tool.name"),
        "gateway.decision": decision,
        "gateway.policy.decision": decision,
        "gateway.policy.reason": attributes.get(
            "aws.agentcore.policy.authorization_reason"
        ),
        "gateway.policy.mode": attributes.get(
            "aws.agentcore.gateway.policy.mode"
        ),
        "gateway.policy.determining_policies": _policy_names(
            attributes.get(
                "aws.agentcore.policy.determining_policies"
            )
        ),
        "gateway.policy.authoritative": True,
        "gateway.policy.source": "aws_managed_trace",
        "http.status_code": (
            attributes.get("http.response.status_code")
            or attributes.get("http.status_code")
        ),
    }
    return {
        "time": _event_time(message.get("startTimeUnixNano")),
        "samplerate": 1,
        "data": {
            key: value
            for key, value in data.items()
            if value not in (None, "", [])
        },
    }


def _batch_url() -> str:
    host = os.environ.get("HONEYCOMB_API_HOST", "https://api.honeycomb.io")
    dataset = urllib.parse.quote(
        os.environ["HONEYCOMB_DATASET"],
        safe="",
    )
    return f"{host.rstrip('/')}/1/batch/{dataset}"


def handler(event: Mapping[str, Any], _context: Any) -> dict[str, int]:
    encoded = event.get("awslogs", {}).get("data")
    if not encoded:
        return {"received": 0, "exported": 0}
    envelope = json.loads(
        gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
    )
    if envelope.get("messageType") == "CONTROL_MESSAGE":
        return {"received": 0, "exported": 0}

    events = []
    for log_event in envelope.get("logEvents", []):
        try:
            message = json.loads(log_event.get("message") or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(message, Mapping):
            continue
        honeycomb_event = _honeycomb_event(message)
        if honeycomb_event is not None:
            events.append(honeycomb_event)
    if not events:
        return {
            "received": len(envelope.get("logEvents", [])),
            "exported": 0,
        }

    request = urllib.request.Request(
        _batch_url(),
        data=json.dumps(events, separators=(",", ":")).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "module12-agentcore-gateway-trace-exporter",
            "X-Honeycomb-Team": _ingest_key(),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        results = json.loads(response.read())
    failures = [
        result
        for result in results
        if int(result.get("status") or 500) >= 300
    ]
    if failures:
        raise RuntimeError(
            f"Honeycomb rejected {len(failures)} of {len(events)} events"
        )
    result = {
        "received": len(envelope.get("logEvents", [])),
        "exported": len(events),
    }
    print(json.dumps(result, sort_keys=True))
    return result
