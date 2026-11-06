"""Signed AgentCore Gateway client used from the Module 12 Runtime."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

try:
    from .cedar_policy import (
        MCP_PROTOCOL_VERSION,
        TOOL_TARGET_NAME,
        gateway_tool_action,
    )
    from .telemetry import add_sanitized_span_attributes
except ImportError:
    from cedar_policy import (
        MCP_PROTOCOL_VERSION,
        TOOL_TARGET_NAME,
        gateway_tool_action,
    )
    from telemetry import add_sanitized_span_attributes


class GatewayInvocationError(RuntimeError):
    """Raised when Gateway does not authorize or execute a requested tool."""


def _decode_response(raw: str) -> Any:
    stripped = raw.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        for line in reversed(stripped.splitlines()):
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
    return {"unparsed_response": stripped[:500]}


def _extract_tool_result(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise GatewayInvocationError("Gateway returned an invalid MCP response")
    if payload.get("error"):
        raise GatewayInvocationError("AgentCore Gateway denied the tool request")
    result = payload.get("result", payload)
    if isinstance(result, Mapping) and result.get("isError"):
        raise GatewayInvocationError("Gateway tool target returned an error")
    if isinstance(result, Mapping):
        structured = result.get("structuredContent")
        if isinstance(structured, Mapping):
            return dict(structured)
        content = result.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                text = block.get("text")
                if not isinstance(text, str):
                    continue
                try:
                    decoded = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, Mapping):
                    return dict(decoded)
        if "status" in result:
            return dict(result)
    raise GatewayInvocationError("Gateway response did not contain a tool result")


class AgentCoreGatewayInvoker:
    """Invoke one explicitly configured AgentCore Gateway with SigV4."""

    def __init__(
        self,
        gateway_url: str,
        *,
        gateway_id: str = "",
        target_name: str = TOOL_TARGET_NAME,
        region_name: str | None = None,
        boto_session: boto3.Session | None = None,
    ) -> None:
        if not gateway_url.rstrip("/").endswith("/mcp"):
            gateway_url = f"{gateway_url.rstrip('/')}/mcp"
        self.gateway_url = gateway_url
        self.gateway_id = gateway_id
        self.target_name = target_name
        self.region_name = (
            region_name
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.boto_session = boto_session or boto3.Session(
            region_name=self.region_name
        )
        self.client_config = Config(
            connect_timeout=5,
            read_timeout=30,
            retries={"mode": "adaptive", "total_max_attempts": 4},
            user_agent_extra="module12-agentcore-runtime",
        )

    def invoke(
        self,
        tool: str,
        *,
        workflow_id: str,
        trusted_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Trace and invoke one Gateway tool request."""

        action = gateway_tool_action(tool, target_name=self.target_name)
        tracer = trace.get_tracer("module12.agentcore_gateway")
        with tracer.start_as_current_span(
            "agentcore.gateway.invoke",
            kind=SpanKind.CLIENT,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            add_sanitized_span_attributes(
                span,
                {
                    "workflow.id": workflow_id,
                    "tool.name": tool,
                    "gateway.id": self.gateway_id,
                    "gateway.target": self.target_name,
                    "gateway.action": action,
                },
            )
            try:
                result = self._invoke(
                    tool,
                    workflow_id=workflow_id,
                    trusted_context=trusted_context,
                )
            except GatewayInvocationError as error:
                add_sanitized_span_attributes(
                    span,
                    {
                        "error.type": type(error).__name__,
                    },
                )
                span.set_status(
                    Status(StatusCode.ERROR, type(error).__name__)
                )
                raise
            gateway = result.get("_gateway")
            gateway_detail = (
                dict(gateway) if isinstance(gateway, Mapping) else {}
            )
            add_sanitized_span_attributes(
                span,
                {
                    "gateway.status_code": gateway_detail.get("status_code"),
                    "gateway.request_id": gateway_detail.get("request_id"),
                    "gateway.governance_source": gateway_detail.get(
                        "governance_source"
                    ),
                },
            )
            span.set_status(Status(StatusCode.OK))
            return result

    def _invoke(
        self,
        tool: str,
        *,
        workflow_id: str,
        trusted_context: Mapping[str, Any],
    ) -> dict[str, Any]:
        action = gateway_tool_action(tool, target_name=self.target_name)
        request_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": uuid.uuid4().hex,
                "method": "tools/call",
                "params": {
                    "name": action,
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": (
                            MCP_PROTOCOL_VERSION
                        ),
                        "io.modelcontextprotocol/clientCapabilities": {},
                    },
                    "arguments": {
                        "workflow_id": workflow_id,
                        "mutation": tool
                        in {"apply_infrastructure", "rollback_infrastructure"},
                        **dict(trusted_context),
                    },
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            "Mcp-Method": "tools/call",
            "Mcp-Name": action,
        }
        propagate.inject(headers)
        credentials = self.boto_session.get_credentials()
        if credentials is None:
            raise GatewayInvocationError(
                "Runtime has no AWS credentials for AgentCore Gateway"
            )
        data_client = self.boto_session.client(
            "bedrock-agentcore",
            region_name=self.region_name,
            config=self.client_config,
        )
        signing_name = (
            data_client.meta.service_model.signing_name or "bedrock-agentcore"
        )
        aws_request = AWSRequest(
            method="POST",
            url=self.gateway_url,
            data=request_body,
            headers=headers,
        )
        SigV4Auth(
            credentials.get_frozen_credentials(),
            signing_name,
            self.region_name,
        ).add_auth(aws_request)
        prepared = aws_request.prepare()
        request = urllib.request.Request(
            prepared.url,
            data=request_body,
            headers=dict(prepared.headers.items()),
            method="POST",
        )
        response_headers: Mapping[str, Any] = {}
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status_code = response.status
                response_headers = response.headers
                payload = _decode_response(
                    response.read().decode("utf-8", errors="replace")
                )
        except urllib.error.HTTPError as error:
            status_code = error.code
            response_headers = error.headers
            payload = _decode_response(
                error.read().decode("utf-8", errors="replace")
            )
        if status_code >= 400:
            raise GatewayInvocationError(
                f"AgentCore Gateway returned HTTP {status_code}"
            )
        result = _extract_tool_result(payload)
        result["_gateway"] = {
            "source": "agentcore_gateway_authorization",
            "gateway_id": self.gateway_id,
            "target_name": self.target_name,
            "tool_action": action,
            "status_code": status_code,
            "request_id": str(
                response_headers.get("x-amzn-requestid")
                or response_headers.get("x-amz-request-id")
                or ""
            ),
            "governance_source": str(
                result.get("governance_source") or ""
            ),
        }
        return result


def invoker_from_environment() -> AgentCoreGatewayInvoker | None:
    gateway_url = os.environ.get("MODULE12_GATEWAY_URL")
    if not gateway_url:
        return None
    return AgentCoreGatewayInvoker(
        gateway_url,
        gateway_id=os.environ.get("MODULE12_GATEWAY_ID", ""),
        target_name=os.environ.get(
            "MODULE12_GATEWAY_TARGET_NAME",
            TOOL_TARGET_NAME,
        ),
    )
