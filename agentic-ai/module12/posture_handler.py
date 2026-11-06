"""AWS Lambda publisher and controller for trusted Snyk posture."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    import boto3
except ImportError:  # pragma: no cover - present in Lambda and the project venv.
    boto3 = None

try:
    from .posture import (
        EVENT_SOURCE,
        FINDING_EVENT_TYPE,
        RECOVERY_EVENT_TYPE,
        build_finding_event,
        build_recovery_event,
        normalize_snyk_report,
        posture_from_detail,
    )
except ImportError:  # Lambda package layout.
    from posture import (
        EVENT_SOURCE,
        FINDING_EVENT_TYPE,
        RECOVERY_EVENT_TYPE,
        build_finding_event,
        build_recovery_event,
        normalize_snyk_report,
        posture_from_detail,
    )

try:
    from .telemetry import SanitizedLogSpan
except ImportError:
    try:
        from telemetry import SanitizedLogSpan
    except ImportError:  # pragma: no cover - Lambda package includes telemetry.py.
        SanitizedLogSpan = None


def _clients() -> tuple[Any, Any, Any]:
    if boto3 is None:  # pragma: no cover
        raise RuntimeError("boto3 is required by the posture Lambda")
    return (
        boto3.client("s3"),
        boto3.client("events"),
        boto3.resource("dynamodb"),
    )


def _response(status_code: int, body: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(dict(body), sort_keys=True),
    }


def _decode_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(event.get("body"), str):
        return json.loads(event["body"])
    return dict(event)


def _publish_event(
    *,
    events_client: Any,
    bus_name: str,
    detail_type: str,
    detail: Mapping[str, Any],
) -> dict[str, Any]:
    result = events_client.put_events(
        Entries=[
            {
                "EventBusName": bus_name,
                "Source": EVENT_SOURCE,
                "DetailType": detail_type,
                "Detail": json.dumps(dict(detail), sort_keys=True),
            }
        ]
    )
    entry = (result.get("Entries") or [{}])[0]
    if entry.get("ErrorCode"):
        raise RuntimeError(
            f"EventBridge publish failed: {entry['ErrorCode']}"
        )
    return {"event_id": entry.get("EventId", "")}


def publish_finding(
    request: Mapping[str, Any],
    *,
    s3_client: Any,
    events_client: Any,
) -> dict[str, Any]:
    payload = build_finding_event(
        subject=str(request.get("subject", "companion-tools")),
        repository_digest=str(
            request.get("repository_digest", "sha256:repository")
        ),
        tool_digest=str(request.get("tool_digest", "sha256:tool-observed")),
        reviewed_tool_digest=str(
            request.get("reviewed_tool_digest", "sha256:tool-reviewed")
        ),
        finding_id=str(request.get("finding_id", "SNYK-MODULE12-001")),
        severity=str(request.get("severity", "high")),
        package_name=str(
            request.get("package_name", "module12-companion-tools")
        ),
        package_version=str(request.get("package_version", "")),
        title=str(request.get("title", "")),
        dependency_path=str(request.get("dependency_path", "")),
        fixed_in=str(request.get("fixed_in", "")),
        recommended_upgrade=str(request.get("recommended_upgrade", "")),
        severity_counts=request.get("severity_counts")
        if isinstance(request.get("severity_counts"), Mapping)
        else {},
        issue_count=int(request.get("issue_count", 1)),
        source_scan_digest=str(request.get("source_scan_digest", "")),
    )
    bucket = os.environ["MODULE12_EVIDENCE_BUCKET"]
    finding = payload["finding"]
    scan_key = f"scans/{finding['scan_digest']}.json"
    finding_key = (
        f"findings/{finding['finding_id']}/{finding['scan_digest']}.json"
    )
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    for key in (scan_key, finding_key):
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
    event_result = _publish_event(
        events_client=events_client,
        bus_name=os.environ["MODULE12_POSTURE_EVENT_BUS"],
        detail_type=FINDING_EVENT_TYPE,
        detail=payload["posture"],
    )
    return {
        "status": "published",
        "mode": str(request.get("mode", "deterministic")),
        "scan_digest": finding["scan_digest"],
        "finding_key": finding_key,
        "scan_key": scan_key,
        "finding": finding,
        "posture": payload["posture"],
        **event_result,
    }


def publish_recovery(
    request: Mapping[str, Any],
    *,
    events_client: Any,
) -> dict[str, Any]:
    payload = build_recovery_event(
        subject=str(request.get("subject", "companion-tools")),
        repository_digest=str(
            request.get("repository_digest", "sha256:repository")
        ),
        tool_digest=str(request.get("tool_digest", "")),
        reviewed_tool_digest=str(request.get("reviewed_tool_digest", "")),
    )
    event_result = _publish_event(
        events_client=events_client,
        bus_name=os.environ["MODULE12_POSTURE_EVENT_BUS"],
        detail_type=RECOVERY_EVENT_TYPE,
        detail=payload["posture"],
    )
    return {
        "status": "recovery_published",
        "posture": payload["posture"]["posture"],
        **event_result,
    }


def record_posture_transition(
    event: Mapping[str, Any],
    *,
    dynamodb_resource: Any,
) -> dict[str, Any]:
    detail = event.get("detail", event)
    transition = posture_from_detail(detail)
    observed_at = str(
        event.get("time", datetime.now(timezone.utc).isoformat())
    )
    table = dynamodb_resource.Table(os.environ["MODULE12_POSTURE_TABLE"])
    table.put_item(
        Item={
            "subject": transition.subject,
            "observedAt": observed_at,
            "posture": transition.posture,
            "postureField": transition.posture_field,
            "reason": transition.reason,
            "toolDigest": transition.tool_digest,
            "reviewedToolDigest": transition.reviewed_tool_digest,
            "scanDigest": transition.scan_digest,
            "findingId": transition.finding_id or "",
            "severity": transition.severity or "",
            "source": EVENT_SOURCE,
        }
    )
    return {
        "status": "posture_recorded",
        "subject": transition.subject,
        "posture": transition.posture,
        "posture_field": transition.posture_field,
        "scan_digest": transition.scan_digest,
    }


def _handle_request(request: dict[str, Any]) -> dict:
    s3_client, events_client, dynamodb_resource = _clients()
    detail_type = request.get("detail-type", request.get("detailType"))
    if detail_type in {FINDING_EVENT_TYPE, RECOVERY_EVENT_TYPE}:
        return _response(
            200,
            record_posture_transition(
                request, dynamodb_resource=dynamodb_resource
            ),
        )
    action = request.get("action", "publish_finding")
    if action == "publish_finding":
        return _response(
            200,
            publish_finding(
                request, s3_client=s3_client, events_client=events_client
            ),
        )
    if action == "recover_digest":
        return _response(200, publish_recovery(request, events_client=events_client))
    if action == "publish-live":
        return _response(
            501,
            {
                "status": "live_mode_requires_codebuild",
                "message": "Run the optional Snyk CLI buildspec in CodeBuild.",
            },
        )
    return _response(400, {"status": "denied", "reason": "unknown_action"})


def handler(event: dict, _context: object) -> dict:
    request = _decode_event(event)
    detail = request.get("detail", request)
    posture = detail.get("posture") if isinstance(detail, Mapping) else None
    span_attributes = {
        "workflow.id": request.get("workflowId"),
        "session.id": request.get("sessionId"),
        "tool.name": "posture_controller",
        "snyk.posture": posture,
        "finding.severity": detail.get("severity")
        if isinstance(detail, Mapping)
        else None,
        "scan.digest": detail.get("scan_digest")
        if isinstance(detail, Mapping)
        else None,
        "tool.digest": detail.get("tool_digest")
        if isinstance(detail, Mapping)
        else None,
        "reviewed.tool.digest": detail.get("reviewed_tool_digest")
        if isinstance(detail, Mapping)
        else None,
        "posture.transition": request.get("detail-type", request.get("action")),
    }
    if SanitizedLogSpan is None:
        return _handle_request(request)
    with SanitizedLogSpan("posture.controller", span_attributes):
        return _handle_request(request)


def _live_request(scan_path: str) -> dict[str, Any]:
    """Convert Snyk JSON output to the normalized publisher contract."""

    report = json.loads(Path(scan_path).read_text())
    finding = normalize_snyk_report(report)
    request = {
        "action": "publish_finding",
        "mode": "live",
        "finding_id": finding["finding_id"],
        "severity": finding["severity"],
        "repository_digest": finding["source_scan_digest"],
        "package_name": finding["package_name"],
        "package_version": finding["package_version"],
        "title": finding["title"],
        "dependency_path": finding["dependency_path"],
        "fixed_in": finding["fixed_in"],
        "recommended_upgrade": finding["recommended_upgrade"],
        "severity_counts": finding["severity_counts"],
        "issue_count": finding["issue_count"],
        "source_scan_digest": finding["source_scan_digest"],
        "tool_digest": os.environ.get("MODULE12_TOOL_DIGEST", "sha256:live-tool"),
        "reviewed_tool_digest": os.environ.get(
            "MODULE12_REVIEWED_TOOL_DIGEST", "sha256:live-tool"
        ),
    }
    if not finding["quarantine_required"]:
        request["action"] = "recover_digest"
    return request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("publish-live",), required=True)
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    s3_client, events_client, _ = _clients()
    request = _live_request(args.input)
    if request["action"] == "publish_finding":
        result = publish_finding(
            request,
            s3_client=s3_client,
            events_client=events_client,
        )
    else:
        result = publish_recovery(request, events_client=events_client)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
