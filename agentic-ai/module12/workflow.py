"""Companion security workflow with deterministic governance.

Deployed runs execute small real-model Strands agents inside one AgentCore
Runtime request. The workflow deliberately separates those untrusted agent
replies from trusted governance facts. The former can suggest work; the latter
is assembled by the workflow/control plane and is the only input used by the
deployment policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

try:  # Package imports when executed from the repository.
    from .contracts import GovernanceContext, PolicyResult, WorkflowEvent, WorkflowOutcome
    from .gateway_client import GatewayInvocationError, invoker_from_environment
    from .live_agents import session_from_environment
    from .posture import POSTURE_SUBJECT
    from .strands_intervention import (
        INTERVENTION_LAYER,
        INTERVENTION_NAME,
        run_strands_tool_call,
    )
    from .tools.handler import invoke_tool
except ImportError:  # Top-level imports inside the Runtime container.
    from contracts import GovernanceContext, PolicyResult, WorkflowEvent, WorkflowOutcome
    from gateway_client import GatewayInvocationError, invoker_from_environment
    from live_agents import session_from_environment
    from posture import POSTURE_SUBJECT
    from strands_intervention import (
        INTERVENTION_LAYER,
        INTERVENTION_NAME,
        run_strands_tool_call,
    )
    from tools.handler import invoke_tool

try:
    import boto3
except ImportError:  # pragma: no cover - boto3 is present in the project venv.
    boto3 = None

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
try:
    from .telemetry import (
        add_sanitized_span_attributes,
        create_honeycomb_exporter,
        honeycomb_config_state,
        sanitize_attributes,
    )
except ImportError:  # Top-level imports inside the Runtime container.
    from telemetry import (
        add_sanitized_span_attributes,
        create_honeycomb_exporter,
        honeycomb_config_state,
        sanitize_attributes,
    )


FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCENARIOS = FIXTURE_DIR / "scenarios.json"
TRUSTED_GOVERNANCE_FIELDS = frozenset(
    {
        "session_tainted",
        "companion_posture",
        "snyk_posture",
        "security_review",
        "financial_approval",
        "environment",
        "artifact_digest",
        "reviewed_artifact_digest",
        "tool_manifest_digest",
        "harness_digest",
    }
)
TOOL_MANIFEST = (
    "read_repository",
    "validate_iac",
    "generate_iac",
    "security_review",
    "get_approval_state",
    "apply_infrastructure",
    "rollback_infrastructure",
    "smoke_test",
)
AGENT_ROLE_BY_TOOL = {
    "read_repository": "Analysis",
    "validate_iac": "IaC",
    "generate_iac": "IaC",
    "security_review": "Analysis",
    "get_approval_state": "Deployment",
    "apply_infrastructure": "Deployment",
    "rollback_infrastructure": "Deployment",
    "smoke_test": "Deployment",
}
TAINT_MARKERS = (
    "instructions for an ai assistant",
    "skip the security review",
    "ignore previous instructions",
    "external notification tool",
)


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible value."""

    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


TOOL_MANIFEST_DIGEST = canonical_digest(TOOL_MANIFEST)
HARNESS_DIGEST = canonical_digest(
    {
        "workflow": "companion-security-workflow",
        "policy": INTERVENTION_LAYER,
    }
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _flatten_text(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value.casefold()
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _flatten_text(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _flatten_text(item)


def detect_taint(repository: Mapping[str, Any]) -> tuple[bool, str]:
    """Classify untrusted repository content without asking a model."""

    text = "\n".join(_flatten_text(repository))
    for marker in TAINT_MARKERS:
        if marker in text:
            return True, "prompt_injection_marker"
    return False, "clean_repository_content"


def load_scenarios() -> dict[str, dict[str, Any]]:
    return json.loads(SCENARIOS.read_text())


def load_repository_fixture(scenario: Mapping[str, Any]) -> dict[str, Any]:
    fixture_name = str(scenario["repository_fixture"])
    fixture_path = FIXTURE_DIR / fixture_name
    if fixture_path.parent != FIXTURE_DIR:
        raise ValueError("repository fixture must remain inside module12/fixtures")
    return json.loads(fixture_path.read_text())


def _trusted_context(
    scenario: Mapping[str, Any],
    *,
    approvals: Mapping[str, Any] | None = None,
) -> GovernanceContext:
    approvals = approvals or {}
    return GovernanceContext(
        session_tainted=False,
        companion_posture=str(scenario.get("companion_posture", "healthy")),
        snyk_posture=str(scenario.get("snyk_posture", "healthy")),
        security_review=str(
            approvals.get(
                "security_review", scenario.get("security_review", "approved")
            )
        ),
        financial_approval=str(
            approvals.get(
                "financial_approval", scenario.get("financial_approval", "approved")
            )
        ),
        environment=str(scenario.get("environment", "staging")),
        reviewed_artifact_digest=str(
            scenario.get("reviewed_artifact_digest", "")
        ),
    )


def _sanitize_model_output(model_output: Mapping[str, Any] | None) -> dict[str, Any]:
    """Keep proposal fields and explicitly report ignored governance attempts."""

    if not model_output:
        return {
            "requested_tool": "apply_infrastructure",
            "rejected_governance_fields": [],
        }
    rejected = sorted(set(model_output) & TRUSTED_GOVERNANCE_FIELDS)
    return {
        "requested_tool": str(model_output.get("requested_tool", "apply_infrastructure")),
        "proposal_summary": str(model_output.get("proposal_summary", ""))[:160],
        "rejected_governance_fields": rejected,
    }


class WorkflowStore:
    """Small persistence interface used by the workflow and Runtime."""

    def read_approval_state(
        self, workflow_id: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        return dict(defaults)

    def read_governance_state(
        self, workflow_id: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        del workflow_id
        return dict(defaults)

    def read_posture_state(
        self, subject: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        del subject
        return dict(defaults)

    def record_event(
        self, workflow_id: str, record_type: str, event: Mapping[str, Any]
    ) -> None:
        del workflow_id, record_type, event

    def record_outcome(self, outcome: WorkflowOutcome) -> None:
        del outcome


class InMemoryWorkflowStore(WorkflowStore):
    """Deterministic store for local runs and unit tests."""

    def __init__(
        self,
        posture_state: Mapping[str, Any] | None = None,
        governance_state: Mapping[str, Any] | None = None,
    ) -> None:
        self.records: list[dict[str, Any]] = []
        self.posture_state = dict(posture_state or {})
        self.governance_state = dict(governance_state or {})

    def read_governance_state(
        self, workflow_id: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        del workflow_id
        return {**dict(defaults), **self.governance_state}

    def read_posture_state(
        self, subject: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        del subject
        values = dict(defaults)
        for field in ("companion_posture", "snyk_posture"):
            if self.posture_state.get(field) in {"healthy", "quarantine"}:
                values[field] = self.posture_state[field]
        return values

    def record_event(
        self, workflow_id: str, record_type: str, event: Mapping[str, Any]
    ) -> None:
        self.records.append(
            {
                "workflowId": workflow_id,
                "recordType": record_type,
                "event": dict(event),
            }
        )

    def record_outcome(self, outcome: WorkflowOutcome) -> None:
        self.records.append(
            {
                "workflowId": outcome.workflow_id,
                "recordType": "summary",
                "outcome": outcome.to_dict(),
            }
        )


class DynamoWorkflowStore(WorkflowStore):
    """Optional DynamoDB-backed state store for the deployed Runtime."""

    def __init__(
        self,
        table_name: str,
        *,
        posture_table_name: str | None = None,
        governance_table_name: str | None = None,
        resource: Any = None,
    ) -> None:
        if boto3 is None:  # pragma: no cover
            raise RuntimeError("boto3 is required for DynamoWorkflowStore")
        dynamodb = resource or boto3.resource("dynamodb")
        self.table = dynamodb.Table(table_name)
        self.posture_table = (
            dynamodb.Table(posture_table_name) if posture_table_name else None
        )
        self.governance_table = (
            dynamodb.Table(governance_table_name)
            if governance_table_name
            else None
        )

    def read_approval_state(
        self, workflow_id: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        return self.read_governance_state(workflow_id, defaults)

    def read_governance_state(
        self, workflow_id: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self.governance_table is None:
            return dict(defaults)
        response = self.governance_table.get_item(
            Key={"workflowId": workflow_id},
            ConsistentRead=True,
        )
        item = response.get("Item", {})
        values = dict(defaults)
        for field in ("security_review", "financial_approval"):
            if item.get(field) in {"pending", "approved", "rejected"}:
                values[field] = item[field]
        if item.get("companion_posture") in {"healthy", "quarantine"}:
            values["companion_posture"] = item["companion_posture"]
        environment = item.get("environment")
        if isinstance(environment, str) and environment:
            values["environment"] = environment
        reviewed_digest = item.get("reviewed_artifact_digest")
        if isinstance(reviewed_digest, str):
            values["reviewed_artifact_digest"] = reviewed_digest
        return values

    def read_posture_state(
        self, subject: str, defaults: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self.posture_table is None:
            return dict(defaults)
        from boto3.dynamodb.conditions import Key

        response = self.posture_table.query(
            KeyConditionExpression=Key("subject").eq(subject),
            ScanIndexForward=False,
            Limit=1,
        )
        item = (response.get("Items") or [{}])[0]
        values = dict(defaults)
        field = item.get("postureField", "snyk_posture")
        posture = item.get("posture")
        if field in {"companion_posture", "snyk_posture"} and posture in {
            "healthy",
            "quarantine",
        }:
            values[field] = posture
        return values

    def record_event(
        self, workflow_id: str, record_type: str, event: Mapping[str, Any]
    ) -> None:
        self.table.put_item(
            Item={
                "workflowId": workflow_id,
                "recordType": record_type,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "event": json.dumps(event, sort_keys=True),
            }
        )

    def record_outcome(self, outcome: WorkflowOutcome) -> None:
        self.table.put_item(
            Item={
                "workflowId": outcome.workflow_id,
                "recordType": "summary",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "outcome": json.dumps(outcome.to_dict(), sort_keys=True),
            }
        )


def store_from_environment() -> WorkflowStore:
    table_name = os.environ.get("MODULE12_WORKFLOW_STATE_TABLE")
    posture_table_name = os.environ.get("MODULE12_POSTURE_STATE_TABLE")
    governance_table_name = os.environ.get("MODULE12_GOVERNANCE_STATE_TABLE")
    if table_name:
        return DynamoWorkflowStore(
            table_name,
            posture_table_name=posture_table_name,
            governance_table_name=governance_table_name,
        )
    return InMemoryWorkflowStore()


class SpanCollector:
    """Capture the security-focused spans used by the demo."""

    def __init__(self) -> None:
        self.exporter = InMemorySpanExporter()
        self.provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": os.environ.get(
                        "MODULE12_HONEYCOMB_DATASET",
                        "module12-security-observability",
                    ),
                    "service.version": "security-workflow",
                }
            )
        )
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.honeycomb_exporter = create_honeycomb_exporter()
        if self.honeycomb_exporter is not None:
            self.provider.add_span_processor(
                BatchSpanProcessor(self.honeycomb_exporter)
            )
        self.tracer = self.provider.get_tracer("module12.security_workflow")

    @contextmanager
    def span(
        self,
        name: str,
        *,
        workflow_id: str,
        session_id: str,
        agent_role: str,
        tool: str = "",
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        with self.tracer.start_as_current_span(
            name,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            base_attributes = {
                "workflow.id": workflow_id,
                "session.id": session_id,
                "agent.role": agent_role,
                **dict(attributes or {}),
            }
            if tool:
                base_attributes["tool.name"] = tool
            add_sanitized_span_attributes(span, base_attributes)
            yield span

    def records(self) -> list[dict[str, Any]]:
        self.provider.force_flush()
        records = [
            {
                "name": span.name,
                "attributes": dict(span.attributes),
                "status": span.status.status_code.name,
                "trace_id": f"{span.context.trace_id:032x}",
                "span_id": f"{span.context.span_id:016x}",
                "parent_span_id": (
                    f"{span.parent.span_id:016x}" if span.parent else None
                ),
                "start_time_ns": span.start_time,
                "end_time_ns": span.end_time,
                "duration_ms": round(
                    max((span.end_time - span.start_time) / 1_000_000, 0),
                    3,
                ),
            }
            for span in self.exporter.get_finished_spans()
        ]
        self.provider.shutdown()
        return records

    def status(self) -> dict[str, Any]:
        config_state = honeycomb_config_state()
        return {
            "redaction": "strict_allowlist",
            "content_exported": False,
            "honeycomb_export_enabled": self.honeycomb_exporter is not None,
            "honeycomb_export": (
                "otlp_http"
                if self.honeycomb_exporter is not None
                else config_state["state"]
            ),
        }


@dataclass
class _Execution:
    workflow_id: str
    session_id: str
    scenario_name: str
    context: GovernanceContext
    events: list[WorkflowEvent]
    spans: SpanCollector
    store: WorkflowStore
    repository: dict[str, Any]
    model_proposal: dict[str, Any]
    agent_session: Any = None
    gateway_invoker: Any = None
    agent_runs: list[dict[str, Any]] = field(default_factory=list)
    gateway_invocations: list[dict[str, Any]] = field(default_factory=list)
    artifact: dict[str, Any] | None = None
    mutation_recorded: bool = False
    smoke_test_status: str = "not_started"

    def run_agent(self, role: str, *, span: Any = None) -> None:
        """Run one real-model agent when deployed live execution is enabled."""

        if self.agent_session is None:
            return
        record = self.agent_session.invoke(
            role,
            scenario=self.scenario_name,
        )
        self.agent_runs.append(dict(record))
        usage = record.get("usage", {})
        if span is not None:
            add_sanitized_span_attributes(
                span,
                {
                    "agent.role": role,
                    "agent.model.id": record.get("model_id"),
                    "agent.stop_reason": record.get("stop_reason"),
                    "agent.input_tokens": usage.get("input_tokens"),
                    "agent.output_tokens": usage.get("output_tokens"),
                    "agent.total_tokens": usage.get("total_tokens"),
                },
            )

    def record(
        self,
        *,
        stage: str,
        agent_role: str,
        tool: str,
        status: str,
        detail: str = "",
        policy: PolicyResult | None = None,
    ) -> None:
        event = WorkflowEvent(
            stage=stage,
            agent_role=agent_role,
            tool=tool,
            status=status,
            detail=detail,
            policy=policy,
        )
        self.events.append(event)
        self.store.record_event(
            self.workflow_id,
            f"event#{len(self.events):03d}",
            event.to_dict(),
        )

    def call_tool(
        self,
        tool: str,
        *,
        stage: str,
        agent_role: str,
        arguments: Mapping[str, Any] | None = None,
        telemetry_attributes: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        context_attributes = {
            "workflow.scenario": self.scenario_name,
            "session.tainted": self.context.session_tainted,
            "companion.posture": self.context.companion_posture,
            "snyk.posture": self.context.snyk_posture,
            "security.review.status": self.context.security_review,
            "financial.approval.status": self.context.financial_approval,
            "artifact.digest": self.context.artifact_digest or None,
            "deployment.environment": self.context.environment,
            "tool.manifest.digest": TOOL_MANIFEST_DIGEST,
            "harness.digest": HARNESS_DIGEST,
            **dict(telemetry_attributes or {}),
        }
        with self.spans.span(
            f"tool.{tool}",
            workflow_id=self.workflow_id,
            session_id=self.session_id,
            agent_role=agent_role,
            tool=tool,
            attributes=context_attributes,
        ):
            if (
                self.gateway_invoker is not None
                and tool in {"apply_infrastructure", "rollback_infrastructure"}
            ):
                result = self.gateway_invoker.invoke(
                    tool,
                    workflow_id=self.workflow_id,
                    trusted_context=self.context.to_dict(),
                )
                gateway = result.get("_gateway")
                if isinstance(gateway, Mapping):
                    self.gateway_invocations.append(dict(gateway))
                return result
            return invoke_tool(
                tool,
                trusted_context=self.context.to_dict(),
                arguments=dict(arguments or {}),
                repository=self.repository,
                artifact=self.artifact,
            )


def _build_artifact(repository: Mapping[str, Any], context: GovernanceContext) -> dict[str, Any]:
    service = repository.get("content", {}).get("service.yaml", {})
    return {
        "service": service.get("name", repository.get("repository", "unknown")),
        "environment": context.environment,
        "port": int(service.get("port", 8080)),
        "health_path": service.get("health_path", "/health"),
        "network": "private",
        "mutation_mode": "simulated",
    }


def reviewed_artifact_digest_for_scenario(scenario_name: str) -> str:
    """Return the digest an external review would approve for one fixture."""

    scenarios = load_scenarios()
    if scenario_name not in scenarios:
        raise ValueError(f"unknown Module 12 scenario: {scenario_name}")
    scenario = scenarios[scenario_name]
    context = _trusted_context(scenario)
    repository = load_repository_fixture(scenario)
    return canonical_digest(_build_artifact(repository, context))


def _governance_defaults(scenario: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "companion_posture": scenario.get("companion_posture", "healthy"),
        "security_review": scenario.get("security_review", "approved"),
        "financial_approval": scenario.get("financial_approval", "approved"),
        "environment": scenario.get("environment", "staging"),
        "reviewed_artifact_digest": scenario.get(
            "reviewed_artifact_digest",
            "",
        ),
    }


def _base_response(execution: _Execution) -> dict[str, Any]:
    return {
        "workflow_id": execution.workflow_id,
        "session_id": execution.session_id,
        "scenario": execution.scenario_name,
        "artifact_digest": execution.context.artifact_digest,
        "reviewed_artifact_digest": execution.context.reviewed_artifact_digest,
        "companion_posture": execution.context.companion_posture,
        "snyk_posture": execution.context.snyk_posture,
        "tool_manifest_digest": TOOL_MANIFEST_DIGEST,
        "harness_digest": HARNESS_DIGEST,
        "mutation_recorded": execution.mutation_recorded,
        "telemetry": execution.spans.status(),
        "agent_execution": {
            "mode": (
                "bedrock_agentcore_runtime"
                if execution.agent_runs
                else "deterministic_local"
            ),
            "runtime_session_id": execution.session_id,
            "handoff_mode": "independent_steps_in_one_runtime_request",
            "agents": execution.agent_runs,
        },
        "gateway_invocations": execution.gateway_invocations,
    }


def run_workflow(
    scenario_name: str,
    *,
    session_id: str | None = None,
    workflow_id: str | None = None,
    model_output: Mapping[str, Any] | None = None,
    store: WorkflowStore | None = None,
    agent_session: Any = None,
    gateway_invoker: Any = None,
) -> WorkflowOutcome:
    """Run one governed workflow and return a safe response object."""

    scenarios = load_scenarios()
    if scenario_name not in scenarios:
        raise ValueError(f"unknown Module 12 scenario: {scenario_name}")
    scenario = scenarios[scenario_name]
    workflow_id = workflow_id or _new_id("workflow")
    session_id = session_id or _new_id("session")
    store = store or store_from_environment()
    agent_session = (
        agent_session
        if agent_session is not None
        else session_from_environment()
    )
    gateway_invoker = (
        gateway_invoker
        if gateway_invoker is not None
        else invoker_from_environment()
    )
    model_proposal = _sanitize_model_output(model_output)
    governance = store.read_governance_state(
        workflow_id,
        _governance_defaults(scenario),
    )
    posture_defaults = {
        "companion_posture": governance.get(
            "companion_posture",
            scenario.get("companion_posture", "healthy"),
        ),
        "snyk_posture": scenario.get("snyk_posture", "healthy"),
    }
    postures = store.read_posture_state(
        os.environ.get("MODULE12_POSTURE_SUBJECT", POSTURE_SUBJECT),
        posture_defaults,
    )
    trusted_scenario = dict(scenario)
    trusted_scenario.update(governance)
    trusted_scenario.update(postures)
    execution = _Execution(
        workflow_id=workflow_id,
        session_id=session_id,
        scenario_name=scenario_name,
        context=_trusted_context(trusted_scenario, approvals=governance),
        events=[],
        spans=SpanCollector(),
        store=store,
        repository=load_repository_fixture(scenario),
        model_proposal=model_proposal,
        agent_session=agent_session,
        gateway_invoker=gateway_invoker,
    )

    with execution.spans.span(
        "agent.analysis",
        workflow_id=workflow_id,
        session_id=session_id,
        agent_role="Analysis",
        attributes={"workflow.scenario": scenario_name},
    ) as agent_span:
        execution.run_agent("Analysis", span=agent_span)
        execution.call_tool(
            "read_repository", stage="analysis", agent_role="Analysis"
        )
        tainted, taint_reason = detect_taint(execution.repository)
        execution.context = replace(execution.context, session_tainted=tainted)
        with execution.spans.span(
            "security.taint_classified",
            workflow_id=workflow_id,
            session_id=session_id,
            agent_role="Analysis",
            tool="read_repository",
            attributes={
                "workflow.scenario": execution.scenario_name,
                "session.tainted": tainted,
                "taint.reason": taint_reason,
                "companion.posture": execution.context.companion_posture,
                "snyk.posture": execution.context.snyk_posture,
                "tool.manifest.digest": TOOL_MANIFEST_DIGEST,
                "harness.digest": HARNESS_DIGEST,
            },
        ):
            pass
        execution.record(
            stage="analysis",
            agent_role="Analysis",
            tool="read_repository",
            status="tainted" if tainted else "clean",
            detail=taint_reason,
        )

    with execution.spans.span(
        "agent.iac",
        workflow_id=workflow_id,
        session_id=session_id,
        agent_role="IaC",
        attributes={"workflow.scenario": scenario_name},
    ) as agent_span:
        execution.run_agent("IaC", span=agent_span)
        validation = execution.call_tool(
            "validate_iac", stage="iac", agent_role="IaC"
        )
        execution.record(
            stage="iac",
            agent_role="IaC",
            tool="validate_iac",
            status="completed" if validation.get("valid") else "failed",
            detail="deterministic IaC contract validation",
        )
        execution.artifact = _build_artifact(execution.repository, execution.context)
        artifact_digest = canonical_digest(execution.artifact)
        execution.context = replace(
            execution.context,
            artifact_digest=artifact_digest,
            reviewed_artifact_digest=(
                execution.context.reviewed_artifact_digest or artifact_digest
            ),
        )
        execution.call_tool("generate_iac", stage="iac", agent_role="IaC")
        execution.record(
            stage="iac",
            agent_role="IaC",
            tool="generate_iac",
            status="completed",
            detail="simulated artifact generated",
        )
        execution.call_tool("security_review", stage="iac", agent_role="Analysis")
        execution.record(
            stage="iac",
            agent_role="Analysis",
            tool="security_review",
            status=execution.context.security_review,
            detail="approval state read from trusted workflow context",
        )

    with execution.spans.span(
        "agent.deployment",
        workflow_id=workflow_id,
        session_id=session_id,
        agent_role="Deployment",
        attributes={"workflow.scenario": scenario_name},
    ) as agent_span:
        execution.run_agent("Deployment", span=agent_span)
        execution.call_tool(
            "get_approval_state", stage="deployment", agent_role="Deployment"
        )
        execution.record(
            stage="deployment",
            agent_role="Deployment",
            tool="get_approval_state",
            status="completed",
            detail="approval state read from trusted workflow context",
        )
        execution.record(
            stage="deployment",
            agent_role="Deployment",
            tool=str(model_proposal["requested_tool"]),
            status="proposed",
            detail="model proposal accepted as untrusted intent only",
        )
        def record_intervention_decision(policy: PolicyResult) -> None:
            with execution.spans.span(
                "policy.authorize",
                workflow_id=workflow_id,
                session_id=session_id,
                agent_role="Deployment",
                tool="apply_infrastructure",
                attributes={
                    "workflow.scenario": execution.scenario_name,
                    "session.tainted": execution.context.session_tainted,
                    "companion.posture": execution.context.companion_posture,
                    "snyk.posture": execution.context.snyk_posture,
                    "policy.decision": policy.decision,
                    "policy.rule": policy.rule,
                    "policy.layer": INTERVENTION_LAYER,
                    "policy.handler": INTERVENTION_NAME,
                    "intervention.action": (
                        "proceed" if policy.decision == "ALLOW" else "deny"
                    ),
                    "security.review.status": execution.context.security_review,
                    "financial.approval.status": execution.context.financial_approval,
                    "artifact.digest": execution.context.artifact_digest,
                    "deployment.environment": execution.context.environment,
                    "tool.manifest.digest": TOOL_MANIFEST_DIGEST,
                    "harness.digest": HARNESS_DIGEST,
                },
            ):
                pass
            execution.record(
                stage="deployment",
                agent_role="Deployment",
                tool="apply_infrastructure",
                status=policy.decision.lower(),
                detail=(
                    f"Strands before_tool_call intervention: {policy.reason}"
                ),
                policy=policy,
            )

        strands_decision = run_strands_tool_call(
            context=execution.context,
            proposal=model_proposal,
            execute_tool=lambda arguments: execution.call_tool(
                "apply_infrastructure",
                stage="deployment",
                agent_role="Deployment",
                arguments={**model_proposal, **dict(arguments)},
                telemetry_attributes={
                    "policy.decision": "ALLOW",
                    "policy.rule": "allow_environment_deployment",
                    "policy.layer": INTERVENTION_LAYER,
                    "policy.handler": INTERVENTION_NAME,
                    "intervention.action": "proceed",
                },
            ),
            on_decision=record_intervention_decision,
        )
        policy = strands_decision.policy
        if policy.decision == "ALLOW":
            result = strands_decision.tool_result or {}
            execution.mutation_recorded = bool(result.get("simulated_mutation", False))
            execution.record(
                stage="deployment",
                agent_role="Deployment",
                tool="apply_infrastructure",
                status="simulated",
                detail="environment deployment invocation recorded",
            )
            smoke = execution.call_tool(
                "smoke_test", stage="deployment", agent_role="Deployment"
            )
            execution.smoke_test_status = str(smoke.get("status", "failed"))
            execution.record(
                stage="deployment",
                agent_role="Deployment",
                tool="smoke_test",
                status=execution.smoke_test_status,
                detail="post-deployment smoke test",
            )
            status = "completed"
            response = {
                "type": "workflow_success",
                **_base_response(execution),
                "policy": policy.to_dict(),
                "smoke_test": execution.smoke_test_status,
                "model_control": execution.model_proposal,
            }
        else:
            status = "denied"
            response = {
                "type": "workflow_denied",
                **_base_response(execution),
                "policy": policy.to_dict(),
                "smoke_test": "not_run",
                "model_control": execution.model_proposal,
            }

    outcome = WorkflowOutcome(
        workflow_id=workflow_id,
        session_id=session_id,
        scenario=scenario_name,
        status=status,
        events=execution.events,
        mutation_recorded=execution.mutation_recorded,
        smoke_test_status=execution.smoke_test_status,
        response=response,
        spans=execution.spans.records(),
    )
    store.record_outcome(outcome)
    return outcome


def _gateway_probe_context(
    scenario_name: str,
    workflow_id: str,
    *,
    store: WorkflowStore,
) -> GovernanceContext:
    scenarios = load_scenarios()
    if scenario_name not in scenarios:
        raise ValueError(f"unknown Module 12 scenario: {scenario_name}")
    scenario = scenarios[scenario_name]
    governance = store.read_governance_state(
        workflow_id,
        _governance_defaults(scenario),
    )
    postures = store.read_posture_state(
        os.environ.get("MODULE12_POSTURE_SUBJECT", POSTURE_SUBJECT),
        {
            "companion_posture": governance.get(
                "companion_posture",
                scenario.get("companion_posture", "healthy"),
            ),
            "snyk_posture": scenario.get("snyk_posture", "healthy"),
        },
    )
    trusted_scenario = {**scenario, **governance, **postures}
    context = _trusted_context(trusted_scenario, approvals=governance)
    repository = load_repository_fixture(scenario)
    tainted, _ = detect_taint(repository)
    artifact_digest = canonical_digest(_build_artifact(repository, context))
    return replace(
        context,
        session_tainted=tainted,
        artifact_digest=artifact_digest,
        reviewed_artifact_digest=(
            context.reviewed_artifact_digest or artifact_digest
        ),
    )


def run_gateway_probe(
    tool: str,
    scenario_name: str,
    workflow_id: str,
    *,
    store: WorkflowStore | None = None,
    gateway_invoker: Any = None,
) -> dict[str, Any]:
    """Invoke Gateway from the Runtime identity without running agent steps."""

    store = store or store_from_environment()
    gateway_invoker = (
        gateway_invoker
        if gateway_invoker is not None
        else invoker_from_environment()
    )
    if gateway_invoker is None:
        raise RuntimeError("AgentCore Gateway is not configured for this Runtime")
    context = _gateway_probe_context(
        scenario_name,
        workflow_id,
        store=store,
    )
    try:
        result = gateway_invoker.invoke(
            tool,
            workflow_id=workflow_id,
            trusted_context=context.to_dict(),
        )
    except GatewayInvocationError as error:
        return {
            "allowed": False,
            "status_code": 403,
            "source": "agentcore_gateway_authorization",
            "detail": str(error),
        }
    gateway = result.get("_gateway")
    gateway_detail = dict(gateway) if isinstance(gateway, Mapping) else {}
    return {
        "allowed": True,
        "status_code": int(gateway_detail.get("status_code") or 200),
        "source": gateway_detail.get("source")
        or "agentcore_gateway_authorization",
        "detail": gateway_detail or result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(load_scenarios()), default="normal")
    parser.add_argument("--session")
    args = parser.parse_args()

    outcome = run_workflow(args.scenario, session_id=args.session)
    print(json.dumps(outcome.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
