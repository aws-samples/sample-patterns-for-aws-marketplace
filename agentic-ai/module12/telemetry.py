"""Telemetry helpers for the Module 12 security workflow."""
from __future__ import annotations

import json
import os
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator, Mapping

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from opentelemetry import baggage, context as otel_context, propagate, trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode


SAFE_ATTRIBUTE_KEYS = frozenset(
    {
        "workflow.id",
        "workflow.scenario",
        "workflow.status",
        "session.id",
        "agent.role",
        "agent.model.id",
        "agent.stop_reason",
        "agent.input_tokens",
        "agent.output_tokens",
        "agent.total_tokens",
        "harness.digest",
        "tool.manifest.digest",
        "tool.name",
        "tool.sequence",
        "runtime.action",
        "runtime.request.type",
        "gateway.id",
        "gateway.target",
        "gateway.action",
        "gateway.status_code",
        "gateway.request_id",
        "gateway.decision",
        "gateway.governance_source",
        "session.tainted",
        "taint.reason",
        "companion.posture",
        "snyk.posture",
        "policy.decision",
        "policy.rule",
        "policy.layer",
        "policy.handler",
        "intervention.action",
        "approval.id",
        "security.review.status",
        "financial.approval.status",
        "artifact.digest",
        "deployment.environment",
        "deployment.invocation_recorded",
        "smoke_test.status",
        "content.exported",
        "posture.transition",
        "posture.reason",
        "finding.severity",
        "scan.digest",
        "tool.digest",
        "reviewed.tool.digest",
        "error.type",
    }
)
SENSITIVE_KEY_PARTS = (
    "prompt",
    "completion",
    "argument",
    "result",
    "secret",
    "content",
    "body",
    "payload",
)
DEFAULT_HONEYCOMB_ENDPOINT = "https://api.honeycomb.io/v1/traces"
DEFAULT_HONEYCOMB_SERVICE_NAME = "module12-security-observability"
STRANDS_REDACTION_TOKENS = (
    "gen_ai_latest_experimental",
    "gen_ai_use_latest_invocation_tokens",
    "gen_ai_unredacted_attributes=",
)
_HONEYCOMB_CONFIG_STATE: dict[str, str] = {
    "state": "not_configured",
    "detail": "secret_arn_not_set",
}


def sanitize_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only the approved low-cardinality security attributes."""

    sanitized: dict[str, Any] = {"content.exported": False}
    for key, value in attributes.items():
        normalized = str(key)
        lowered = normalized.casefold()
        if normalized not in SAFE_ATTRIBUTE_KEYS:
            continue
        if any(part in lowered for part in SENSITIVE_KEY_PARTS):
            continue
        if value is None:
            if normalized == "approval.id":
                sanitized[normalized] = None
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[normalized] = value
    return sanitized


def _set_honeycomb_config_state(state: str, detail: str) -> None:
    _HONEYCOMB_CONFIG_STATE.clear()
    _HONEYCOMB_CONFIG_STATE.update({"state": state, "detail": detail})


def honeycomb_config_state() -> dict[str, str]:
    """Return a non-sensitive explanation of the current exporter state."""

    return dict(_HONEYCOMB_CONFIG_STATE)


@lru_cache(maxsize=1)
def load_honeycomb_config() -> dict[str, Any] | None:
    """Load the complete Honeycomb Ingest Key from Secrets Manager."""

    secret_arn = os.environ.get("MODULE12_HONEYCOMB_SECRET_ARN")
    if not secret_arn:
        _set_honeycomb_config_state("not_configured", "secret_arn_not_set")
        return None
    try:
        import boto3

        response = boto3.client(
            "secretsmanager",
            region_name=(
                os.environ.get("AWS_REGION")
                or os.environ.get("AWS_DEFAULT_REGION")
                or "us-east-1"
            ),
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"mode": "adaptive", "total_max_attempts": 3},
                user_agent_extra="module12-honeycomb-config",
            ),
        ).get_secret_value(
            SecretId=secret_arn,
        )
    except (BotoCoreError, ClientError) as error:
        _set_honeycomb_config_state(
            "unavailable",
            type(error).__name__,
        )
        return None
    secret_string = response.get("SecretString", "")
    if not secret_string:
        _set_honeycomb_config_state("misconfigured", "secret_value_empty")
        return None
    ingest_key = secret_string.strip()
    if not ingest_key:
        _set_honeycomb_config_state("misconfigured", "ingest_key_empty")
        return None
    endpoint = os.environ.get(
        "MODULE12_HONEYCOMB_OTLP_ENDPOINT",
        DEFAULT_HONEYCOMB_ENDPOINT,
    )
    _set_honeycomb_config_state("configured", "otlp_http")
    return {
        "endpoint": str(endpoint),
        "ingest_key": ingest_key,
        "service_name": os.environ.get(
            "MODULE12_HONEYCOMB_DATASET",
            DEFAULT_HONEYCOMB_SERVICE_NAME,
        ),
    }


def create_honeycomb_exporter() -> Any | None:
    """Create an OTLP HTTP exporter only when credentials are configured."""

    config = load_honeycomb_config()
    if not config:
        return None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
    except ImportError:
        return None
    return OTLPSpanExporter(
        endpoint=config["endpoint"],
        headers={"x-honeycomb-team": config["ingest_key"]},
        timeout=10,
    )


def configure_strands_redaction() -> str:
    """Enable Strands GenAI spans without exporting model content fields."""

    existing = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN", "")
    values = [value.strip() for value in existing.split(",") if value.strip()]
    for required in STRANDS_REDACTION_TOKENS:
        if not any(
            value == required
            or (
                required.startswith("gen_ai_unredacted_attributes=")
                and value.startswith("gen_ai_unredacted_attributes=")
            )
            for value in values
        ):
            values.append(required)
    configured = ",".join(values)
    os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = configured
    return configured


@dataclass
class RuntimeTelemetry:
    """Process-level OpenTelemetry provider used by Runtime and Strands spans."""

    provider: TracerProvider
    tracer: Any
    export_enabled: bool
    service_name: str

    def force_flush(self, timeout_millis: int = 10_000) -> bool:
        return bool(self.provider.force_flush(timeout_millis=timeout_millis))


class WorkflowCorrelationProcessor(SpanProcessor):
    """Stamp safe workflow baggage onto Runtime, Strands, and Gateway spans."""

    CORRELATION_KEYS = (
        "workflow.id",
        "workflow.scenario",
        "session.id",
    )

    def __init__(self) -> None:
        self._correlations: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def on_start(
        self,
        span: Span,
        parent_context: otel_context.Context | None = None,
    ) -> None:
        attributes = {
            key: baggage.get_baggage(key, context=parent_context)
            for key in self.CORRELATION_KEYS
        }
        trace_id = span.get_span_context().trace_id
        if any(value is not None for value in attributes.values()):
            with self._lock:
                self._correlations[trace_id] = dict(attributes)
        else:
            with self._lock:
                attributes = dict(self._correlations.get(trace_id, {}))
        add_sanitized_span_attributes(span, attributes)

    def on_end(self, span: ReadableSpan) -> None:
        if span.name != "devops_companion.workflow":
            return
        with self._lock:
            self._correlations.pop(span.context.trace_id, None)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        del timeout_millis
        return True


@lru_cache(maxsize=1)
def configure_runtime_telemetry() -> RuntimeTelemetry:
    """Configure the global provider before the first Strands Agent is created."""

    configure_strands_redaction()
    config = load_honeycomb_config()
    service_name = str(
        (config or {}).get("service_name")
        or os.environ.get(
            "MODULE12_HONEYCOMB_DATASET",
            DEFAULT_HONEYCOMB_SERVICE_NAME,
        )
    )
    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": service_name,
                "service.namespace": "module12-devops-companion",
                "deployment.environment": os.environ.get(
                    "MODULE12_DEPLOYMENT_ENVIRONMENT",
                    "aws-agentcore",
                ),
            }
        )
    )
    provider.add_span_processor(WorkflowCorrelationProcessor())
    exporter = create_honeycomb_exporter()
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return RuntimeTelemetry(
        provider=provider,
        tracer=provider.get_tracer("module12.runtime"),
        export_enabled=exporter is not None,
        service_name=service_name,
    )


def add_sanitized_span_attributes(
    span: Any,
    attributes: Mapping[str, Any],
) -> None:
    """Apply the shared Module 12 allowlist to an OpenTelemetry span."""

    for key, value in sanitize_attributes(attributes).items():
        span.set_attribute(key, value)


@contextmanager
def runtime_request_span(
    *,
    action: str,
    workflow_id: str,
    session_id: str,
    scenario: str,
    carrier: Mapping[str, str] | None = None,
) -> Iterator[Any]:
    """Create one trace root for a complete AgentCore Runtime request."""

    runtime = configure_runtime_telemetry()
    parent_context = propagate.extract(carrier=carrier) if carrier else None
    workflow_context = parent_context or otel_context.get_current()
    workflow_context = baggage.set_baggage(
        "workflow.id",
        workflow_id,
        context=workflow_context,
    )
    workflow_context = baggage.set_baggage(
        "workflow.scenario",
        scenario,
        context=workflow_context,
    )
    workflow_context = baggage.set_baggage(
        "session.id",
        session_id,
        context=workflow_context,
    )
    with runtime.tracer.start_as_current_span(
        "devops_companion.workflow",
        context=workflow_context,
        kind=SpanKind.SERVER,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        add_sanitized_span_attributes(
            span,
            {
                "runtime.action": action,
                "runtime.request.type": "agentcore_runtime_invocation",
                "workflow.id": workflow_id,
                "workflow.scenario": scenario,
                "session.id": session_id,
            },
        )
        try:
            yield span
        except Exception as error:
            add_sanitized_span_attributes(
                span,
                {"error.type": type(error).__name__},
            )
            span.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise
        else:
            span.set_status(Status(StatusCode.OK))


def force_flush_runtime_telemetry() -> bool:
    """Flush completed Runtime and Strands spans before returning the response."""

    return configure_runtime_telemetry().force_flush()


def emit_sanitized_span(
    name: str,
    attributes: Mapping[str, Any],
    *,
    duration_ms: float | None = None,
) -> dict[str, Any]:
    """Emit a security-focused span envelope to the local Lambda log stream."""

    record = {
        "telemetry": "otel_span",
        "name": name,
        "attributes": sanitize_attributes(attributes),
    }
    if duration_ms is not None:
        record["duration_ms"] = round(duration_ms, 3)
    print(json.dumps(record, sort_keys=True), flush=True)
    return record


class SanitizedLogSpan:
    """Context manager used when a full OTel SDK is not packaged."""

    def __init__(self, name: str, attributes: Mapping[str, Any]) -> None:
        self.name = name
        self.attributes = dict(attributes)
        self.started = 0.0

    def __enter__(self) -> "SanitizedLogSpan":
        self.started = time.perf_counter()
        return self

    def __exit__(self, _kind: Any, _value: Any, _traceback: Any) -> None:
        emit_sanitized_span(
            self.name,
            self.attributes,
            duration_ms=(time.perf_counter() - self.started) * 1000,
        )
