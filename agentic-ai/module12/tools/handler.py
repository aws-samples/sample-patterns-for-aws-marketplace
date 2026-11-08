"""Deterministic Lambda-backed tools for the Module 12 Gateway manifest."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

try:
    from ..telemetry import SanitizedLogSpan
except ImportError:
    try:
        from telemetry import SanitizedLogSpan
    except ImportError:  # pragma: no cover - Lambda package includes telemetry.py.
        SanitizedLogSpan = None


READ_ONLY = {
    "read_repository",
    "validate_iac",
    "generate_iac",
    "security_review",
    "get_approval_state",
    "smoke_test",
}
TOOL_NAMES = READ_ONLY | {"apply_infrastructure", "rollback_infrastructure"}
TRUSTED_CONTEXT_FIELDS = {
    "workflow_id",
    "governance_source",
    "session_tainted",
    "companion_posture",
    "snyk_posture",
    "security_review",
    "financial_approval",
    "environment",
    "artifact_digest",
    "reviewed_artifact_digest",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def invoke_tool(
    tool_name: str,
    *,
    trusted_context: Mapping[str, Any] | None = None,
    arguments: Mapping[str, Any] | None = None,
    repository: Mapping[str, Any] | None = None,
    artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a deterministic tool without merging model arguments into trust."""

    if tool_name not in TOOL_NAMES:
        return {
            "tool": tool_name,
            "status": "denied",
            "mutation": False,
            "infrastructure_changed": False,
            "error": "unknown_tool",
        }

    trusted_context = dict(trusted_context or {})
    arguments = dict(arguments or {})
    ignored_governance_fields = sorted(
        set(arguments).intersection(TRUSTED_CONTEXT_FIELDS)
    )
    result: dict[str, Any] = {
        "tool": tool_name,
        "mutation": tool_name not in READ_ONLY,
        "infrastructure_changed": False,
        "ignored_governance_fields": ignored_governance_fields,
        "governance_source": trusted_context.get("governance_source", ""),
    }

    if tool_name == "read_repository":
        result.update(
            {
                "status": "completed",
                "repository_digest": _digest(repository or {}),
                "file_count": len((repository or {}).get("content", {})),
            }
        )
    elif tool_name == "validate_iac":
        service = (repository or {}).get("content", {}).get("service.yaml", {})
        valid = all(
            field in service for field in ("name", "port", "health_path")
        )
        result.update({"status": "completed" if valid else "failed", "valid": valid})
    elif tool_name == "generate_iac":
        result.update(
            {
                "status": "completed",
                "artifact_digest": _digest(artifact or {}),
            }
        )
    elif tool_name == "security_review":
        result.update(
            {
                "status": trusted_context.get("security_review", "pending"),
                "review_source": "trusted_workflow_context",
            }
        )
    elif tool_name == "get_approval_state":
        result.update(
            {
                "status": "completed",
                "security_review": trusted_context.get("security_review", "pending"),
                "financial_approval": trusted_context.get(
                    "financial_approval", "pending"
                ),
                "approval_source": "trusted_workflow_context",
            }
        )
    elif tool_name == "apply_infrastructure":
        result.update(
            {
                "status": "simulated",
                "simulated_mutation": True,
                "infrastructure_changed": False,
                "mutation_source": "companion_demo_simulation",
            }
        )
    elif tool_name == "rollback_infrastructure":
        result.update(
            {
                "status": "simulated",
                "simulated_mutation": True,
                "infrastructure_changed": False,
                "mutation_source": "companion_demo_simulation",
            }
        )
    elif tool_name == "smoke_test":
        result.update(
            {
                "status": "passed",
                "target": "simulated_companion",
            }
        )
    return result


def _gateway_tool_name(context: object) -> str | None:
    client_context = getattr(context, "client_context", None)
    custom = getattr(client_context, "custom", None)
    if not isinstance(custom, Mapping):
        return None
    name = custom.get("bedrockAgentCoreToolName")
    if not isinstance(name, str) or not name:
        return None
    return name.rsplit("___", 1)[-1]


def _invoke_gateway_tool(
    event: Mapping[str, Any],
    *,
    tool_name: str,
) -> dict[str, Any]:
    trusted_context = {
        field: event[field]
        for field in TRUSTED_CONTEXT_FIELDS
        if field in event
    }
    arguments = {
        key: value
        for key, value in event.items()
        if key not in TRUSTED_CONTEXT_FIELDS and key != "mutation"
    }
    return invoke_tool(
        tool_name,
        trusted_context=trusted_context,
        arguments=arguments,
        repository=event.get("repository"),
        artifact=event.get("artifact"),
    )


def handler(event: dict, context: object) -> dict:
    gateway_tool_name = _gateway_tool_name(context)
    if gateway_tool_name:
        # AgentCore Gateway Lambda targets pass tool arguments as the event and
        # expect the tool result directly, without an API Gateway envelope.
        return _invoke_gateway_tool(event, tool_name=gateway_tool_name)

    if isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except json.JSONDecodeError:
            return {"statusCode": 400, "body": json.dumps({"error": "invalid_json"})}
    tool_name = event.get("toolName", event.get("name", "unknown"))
    trusted_context = event.get("trustedContext", {})
    span_attributes = {
        "workflow.id": event.get("workflowId"),
        "session.id": event.get("sessionId"),
        "tool.name": tool_name,
        "session.tainted": trusted_context.get("session_tainted"),
        "companion.posture": trusted_context.get("companion_posture"),
        "snyk.posture": trusted_context.get("snyk_posture"),
        "policy.decision": event.get("policyDecision"),
    }
    span_context = (
        SanitizedLogSpan(f"tool.{tool_name}", span_attributes)
        if SanitizedLogSpan is not None
        else None
    )
    if span_context is None:
        result = invoke_tool(
            tool_name,
            trusted_context=trusted_context,
            arguments=event.get("arguments", event.get("input", {})),
            repository=event.get("repository"),
            artifact=event.get("artifact"),
        )
    else:
        with span_context:
            result = invoke_tool(
                tool_name,
                trusted_context=trusted_context,
                arguments=event.get("arguments", event.get("input", {})),
                repository=event.get("repository"),
                artifact=event.get("artifact"),
            )
    return {
        "statusCode": 200 if result.get("status") != "denied" else 400,
        "body": json.dumps(result, sort_keys=True),
    }
