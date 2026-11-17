"""AgentCore Gateway request interceptor for authoritative governance context.

The Runtime may attest facts that exist only inside the active execution, such
as repository taint and the proposed artifact digest. Before Gateway evaluates a
tool request, this interceptor replaces externally governed fields with values
read from DynamoDB. Missing state is represented with fail-closed values.
"""
from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from typing import Any, Mapping

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config


APPROVAL_VALUES = frozenset({"pending", "approved", "rejected"})
POSTURE_VALUES = frozenset({"healthy", "quarantine"})
GOVERNANCE_SOURCE = "gateway_request_interceptor"
DEFAULT_POSTURE_SUBJECT = "companion-tools"


@lru_cache(maxsize=1)
def _dynamodb_resource() -> Any:
    return boto3.resource(
        "dynamodb",
        config=Config(
            connect_timeout=3,
            read_timeout=5,
            retries={"mode": "adaptive", "total_max_attempts": 4},
            user_agent_extra="module12-agentcore-gateway-interceptor",
        ),
    )


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    mcp = event.get("mcp")
    if not isinstance(mcp, Mapping):
        raise ValueError("AgentCore interceptor event is missing mcp")
    gateway_request = mcp.get("gatewayRequest")
    if not isinstance(gateway_request, Mapping):
        raise ValueError("AgentCore interceptor event is missing gatewayRequest")
    body = gateway_request.get("body")
    if isinstance(body, str):
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise ValueError("AgentCore Gateway request body must be an object")
        return decoded
    if not isinstance(body, Mapping):
        raise ValueError("AgentCore Gateway request body must be an object")
    return copy.deepcopy(dict(body))


def _fail_closed_state() -> dict[str, Any]:
    return {
        "companion_posture": "quarantine",
        "snyk_posture": "quarantine",
        "security_review": "pending",
        "financial_approval": "pending",
        "reviewed_artifact_digest": "",
        "environment": "production",
    }


def _governance_state(
    workflow_id: str,
    *,
    governance_table: Any,
    posture_table: Any,
    posture_subject: str,
) -> dict[str, Any]:
    state = _fail_closed_state()
    if not workflow_id:
        return state

    response = governance_table.get_item(
        Key={"workflowId": workflow_id},
        ConsistentRead=True,
    )
    item = response.get("Item")
    if isinstance(item, Mapping):
        companion_posture = item.get("companion_posture")
        security_review = item.get("security_review")
        financial_approval = item.get("financial_approval")
        reviewed_digest = item.get("reviewed_artifact_digest")
        environment = item.get("environment")
        if companion_posture in POSTURE_VALUES:
            state["companion_posture"] = companion_posture
        if security_review in APPROVAL_VALUES:
            state["security_review"] = security_review
        if financial_approval in APPROVAL_VALUES:
            state["financial_approval"] = financial_approval
        if isinstance(reviewed_digest, str):
            state["reviewed_artifact_digest"] = reviewed_digest
        if isinstance(environment, str) and environment:
            state["environment"] = environment

    posture_response = posture_table.query(
        KeyConditionExpression=Key("subject").eq(posture_subject),
        ScanIndexForward=False,
        Limit=1,
        ConsistentRead=True,
    )
    posture_items = posture_response.get("Items") or []
    if posture_items and isinstance(posture_items[0], Mapping):
        posture_item = posture_items[0]
        posture_field = posture_item.get("postureField", "snyk_posture")
        posture = posture_item.get("posture")
        if (
            posture_field in {"companion_posture", "snyk_posture"}
            and posture in POSTURE_VALUES
        ):
            state[posture_field] = posture
    return state


def transform_request(
    event: Mapping[str, Any],
    *,
    governance_table: Any,
    posture_table: Any,
    posture_subject: str = DEFAULT_POSTURE_SUBJECT,
) -> dict[str, Any]:
    """Return a request whose external governance fields are authoritative."""

    body = _body(event)
    if body.get("method") != "tools/call":
        return body
    params = body.get("params")
    if not isinstance(params, dict):
        params = {}
        body["params"] = params
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
        params["arguments"] = arguments
    workflow_id = str(arguments.get("workflow_id") or "")
    arguments.update(
        _governance_state(
            workflow_id,
            governance_table=governance_table,
            posture_table=posture_table,
            posture_subject=posture_subject,
        )
    )
    arguments["governance_source"] = GOVERNANCE_SOURCE
    return body


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Enrich an MCP request before AgentCore Gateway authorization."""

    del context
    governance_table_name = os.environ["MODULE12_GOVERNANCE_STATE_TABLE"]
    posture_table_name = os.environ["MODULE12_POSTURE_STATE_TABLE"]
    dynamodb = _dynamodb_resource()
    transformed = transform_request(
        event,
        governance_table=dynamodb.Table(governance_table_name),
        posture_table=dynamodb.Table(posture_table_name),
        posture_subject=os.environ.get(
            "MODULE12_POSTURE_SUBJECT",
            DEFAULT_POSTURE_SUBJECT,
        ),
    )
    workflow_id = (
        transformed.get("params", {}).get("arguments", {}).get("workflow_id", "")
    )
    print(
        json.dumps(
            {
                "event": "gateway_governance_enriched",
                "workflow_id": workflow_id,
                "source": GOVERNANCE_SOURCE,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return {
        "interceptorOutputVersion": "1.0",
        "mcp": {"transformedGatewayRequest": {"body": transformed}},
    }
