#!/usr/bin/env python3
"""
demos/module12_demo.py
======================
Module 12: Security and Observability for the DevOps Companion.

The demo follows three controls around an agent-proposed environment deployment:

  1. A model can propose infrastructure work, but trusted policy facts decide
     whether the environment deployment is allowed.
  2. A recorded dependency finding quarantines the Companion tool supply chain
     while read-only analysis remains available.
  3. Workflow telemetry compares behavior across executions and identifies the
     governed signal behind an individual workflow decision.

Without deployment configuration, the driver uses the deterministic local
workflow. Passing --stack or --outputs invokes the deployed AgentCore Runtime,
posture controller, and DynamoDB evidence tables.

USAGE
-----
  python demos/module12_demo.py
  python demos/module12_demo.py --section 1
  python demos/module12_demo.py --section 2
  python demos/module12_demo.py --section 3
  python demos/module12_demo.py --seed --stack module12-demo
  python demos/module12_demo.py --stack module12-demo
  python demos/module12_demo.py --no-pause  # automated smoke test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from module12.cedar_policy import (
    MCP_PROTOCOL_VERSION,
    TOOL_TARGET_NAME,
    build_cedar_policy,
)
from module12.contracts import GovernanceContext
from module12.honeycomb_local import LocalHoneycombDataset
from module12.policy_verifier import evaluate
from module12.posture import (
    SNYK_MONITOR_PROJECT_NAME,
    SNYK_MONITOR_TARGET_REFERENCE,
    build_finding_event_from_snyk_report,
    build_recovery_event,
    load_recorded_snyk_report,
    normalize_snyk_report,
    posture_from_detail,
)
from module12.telemetry_queries import (
    honeycomb_investigation_link,
    honeycomb_query_template_link,
    normalize_summary,
)
from module12.workflow import (
    InMemoryWorkflowStore,
    load_scenarios,
    reviewed_artifact_digest_for_scenario,
    run_workflow,
)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table

    CONSOLE = Console()
    RICH = True
except ImportError:
    CONSOLE = None
    RICH = False


REVIEWED_TOOL_DIGEST = "sha256:" + ("a" * 64)
CHANGED_TOOL_DIGEST = "sha256:" + ("b" * 64)
SECTION_1_COLOR = "green"
SECTION_2_COLOR = "yellow"
SECTION_3_COLOR = "magenta"
HONEYCOMB_QUERY_WIDTH = 68
MIN_AGENTCORE_SESSION_LENGTH = 33
MAX_DEMO_SESSION_LENGTH = 48
HONEYCOMB_POLICY_POPULATION_QUERY = {
    "calculations": [{"op": "COUNT"}],
    "filters": [
        {
            "column": "name",
            "op": "=",
            "value": "policy.authorize",
        }
    ],
    "breakdowns": [
        "policy.decision",
        "policy.rule",
    ],
    "time_range": 86400,
}
SESSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
CODEBUILD_TERMINAL_STATUSES = frozenset(
    {"SUCCEEDED", "FAILED", "FAULT", "STOPPED", "TIMED_OUT"}
)


class DemoError(RuntimeError):
    """A presenter-actionable failure without a Python traceback."""


def clear_screen() -> None:
    print("\033[H\033[2J", end="", flush=True)


def header(text: str, color: str = "cyan") -> None:
    if RICH:
        CONSOLE.rule(f"[bold {color}]{text}[/bold {color}]", style=color)
    else:
        print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def new_screen(title: str, color: str = "cyan") -> None:
    """Clear the presenter terminal before a new section or scenario state."""

    clear_screen()
    header(title, color)


def operation_started(
    message: str,
    *,
    cloud: bool,
    setup: bool = False,
) -> None:
    """Mark the beginning of work that may create a visible delay."""

    if setup:
        label = "LIVE AWS SETUP" if cloud else "LOCAL SETUP"
    else:
        label = "LIVE AWS CALL" if cloud else "LOCAL SIMULATION"
    print(f"\n  {label} — {message}", flush=True)


def operation_status(message: str, *, cloud: bool) -> None:
    """Report progress while an announced operation is still running."""

    label = "LIVE AWS STATUS" if cloud else "LOCAL STATUS"
    print(f"  {label} — {message}", flush=True)


def operation_completed(
    message: str,
    *,
    cloud: bool,
    setup: bool = False,
) -> None:
    """Mark completion before explanatory or static content resumes."""

    if setup:
        label = "LIVE AWS SETUP COMPLETE" if cloud else "LOCAL SETUP COMPLETE"
    else:
        label = "LIVE AWS RESULT" if cloud else "LOCAL RESULT"
    print(f"  {label} — {message}", flush=True)


def box(title: str, body: str, color: str = "cyan") -> None:
    if RICH:
        CONSOLE.print(Panel(body, title=f"[bold]{title}[/bold]", border_style=color))
    else:
        print(f"\n--- {title} ---\n{body}")


def pause(message: str, no_pause: bool) -> None:
    if no_pause:
        return
    try:
        input(message)
    except EOFError:
        return
    except KeyboardInterrupt as error:
        raise SystemExit(130) from error


def show_values(
    title: str,
    rows: Sequence[tuple[str, Any]],
    *,
    color: str = "green",
) -> None:
    rendered = [(label, _display(value)) for label, value in rows]
    if RICH:
        table = Table(title=title, show_header=False, show_lines=False)
        table.add_column("Field", style=color, no_wrap=True)
        table.add_column("Value", overflow="fold")
        for label, value in rendered:
            table.add_row(label, value)
        CONSOLE.print(table)
    else:
        print(f"\n--- {title} ---")
        for label, value in rendered:
            print(f"  {label}: {value}")


def show_table(
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
) -> None:
    if RICH:
        table = Table(title=title, show_lines=False)
        for index, column in enumerate(columns):
            table.add_column(column, style="cyan" if index == 0 else None)
        for row in rows:
            table.add_row(*(_display(value) for value in row))
        CONSOLE.print(table)
    else:
        print(f"\n--- {title} ---")
        print("  " + " | ".join(columns))
        for row in rows:
            print("  " + " | ".join(_display(value) for value in row))


def takeaway(text: str, *, title: str = "Takeaway") -> None:
    box(title, text, color="green")


def show_code(title: str, code: str) -> None:
    if RICH:
        CONSOLE.print()
        CONSOLE.print(f"[bold magenta]{title}[/bold magenta]")
        CONSOLE.print(
            Syntax(
                code,
                "json",
                background_color="default",
                word_wrap=False,
            )
        )
    else:
        print(f"\n{title}\n{code}")


def compact_json(value: Any, *, width: int = HONEYCOMB_QUERY_WIDTH) -> str:
    """Serialize compact JSON within a presentation-safe terminal width."""

    serialized = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    segments: list[str] = []
    start = 0
    in_string = False
    escaped = False

    for index, character in enumerate(serialized):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == ",":
            segments.append(serialized[start : index + 1])
            start = index + 1
    segments.append(serialized[start:])

    lines: list[str] = []
    current = ""
    for segment in segments:
        if current and len(current) + len(segment) > width:
            lines.append(current)
            current = segment
        else:
            current += segment
    if current:
        lines.append(current)
    return "\n".join(lines)


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _decode_json(value: Any) -> Any:
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _extract_cedar_statement(definition: Any) -> str:
    if not isinstance(definition, Mapping):
        return ""
    cedar = definition.get("cedar", {})
    if isinstance(cedar, Mapping):
        statement = cedar.get("statement")
        if isinstance(statement, str):
            return statement
    policy = definition.get("policy", {})
    if isinstance(policy, Mapping):
        statement = policy.get("statement")
        if isinstance(statement, str):
            return statement
    return ""


def _session_id(value: str | None = None) -> str:
    if value:
        if not SESSION_PATTERN.fullmatch(value):
            raise DemoError(
                "--session may contain only letters, numbers, hyphens, and underscores"
            )
        base = value
    else:
        base = f"module12-demo-{uuid.uuid4().hex}"
    if len(base) < MIN_AGENTCORE_SESSION_LENGTH:
        suffix = hashlib.sha256(base.encode("utf-8")).hexdigest()
        missing = MIN_AGENTCORE_SESSION_LENGTH - len(base)
        if missing > 1:
            base = f"{base}-{suffix[: missing - 1]}"
        else:
            base = f"{base}{suffix[:missing]}"
    if len(base) > MAX_DEMO_SESSION_LENGTH:
        raise DemoError(
            f"--session must be at most {MAX_DEMO_SESSION_LENGTH} characters"
        )
    return base


def _policy(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    response = outcome.get("response", {})
    if not isinstance(response, Mapping):
        return {}
    policy = response.get("policy", {})
    return policy if isinstance(policy, Mapping) else {}


def _response(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    response = outcome.get("response", {})
    return response if isinstance(response, Mapping) else {}


def _agent_execution(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    execution = _response(outcome).get("agent_execution", {})
    return execution if isinstance(execution, Mapping) else {}


def _runtime_gateway_invocation(outcome: Mapping[str, Any]) -> Mapping[str, Any]:
    invocations = _response(outcome).get("gateway_invocations", [])
    if not isinstance(invocations, Sequence) or isinstance(
        invocations, (str, bytes)
    ):
        return {}
    for invocation in reversed(invocations):
        if (
            isinstance(invocation, Mapping)
            and str(invocation.get("tool_action", "")).endswith(
                "___apply_infrastructure"
            )
        ):
            return invocation
    return {}


def _require_live_agent_execution(outcome: Mapping[str, Any]) -> None:
    execution = _agent_execution(outcome)
    agents = execution.get("agents", [])
    if (
        execution.get("mode") != "bedrock_agentcore_runtime"
        or not isinstance(agents, Sequence)
        or isinstance(agents, (str, bytes))
    ):
        raise DemoError(
            "The deployed Runtime did not report live agent execution; rebuild "
            "and redeploy Module 12 before running the AWS demo"
        )
    observed_roles = set()
    for agent in agents:
        if not isinstance(agent, Mapping):
            continue
        usage = agent.get("usage", {})
        if not isinstance(usage, Mapping) or int(
            usage.get("total_tokens", 0)
        ) <= 0:
            raise DemoError(
                f"The {agent.get('role', 'unknown')} agent did not report a "
                "real Bedrock model invocation"
            )
        observed_roles.add(str(agent.get("role") or ""))
    expected_roles = {"Analysis", "IaC", "Deployment"}
    if observed_roles != expected_roles:
        raise DemoError(
            "Expected live Analysis, IaC, and Deployment agents in the Runtime "
            f"response; observed {sorted(observed_roles)}"
        )


def _events(outcome: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    events = outcome.get("events", [])
    return [event for event in events if isinstance(event, Mapping)]


def _workflow_event(
    outcome: Mapping[str, Any],
    tool: str,
    *,
    status: str | None = None,
) -> Mapping[str, Any]:
    """Return the first matching recorded workflow event."""

    for event in _events(outcome):
        if event.get("tool") != tool:
            continue
        if status is not None and event.get("status") != status:
            continue
        return event
    return {}


def _checkpoint_status(text: str, color: str) -> str:
    if RICH:
        return f"[bold {color}]{text}[/bold {color}]"
    return text


def show_workflow_path(
    outcome: Mapping[str, Any],
    *,
    color: str,
) -> None:
    """Render the agent workflow using the same checkpoints in every scenario."""

    policy = _policy(outcome)
    decision = str(policy.get("decision") or "DENY")
    rule = str(policy.get("rule") or "unknown")
    repository_status = str(
        _workflow_event(outcome, "read_repository").get("status") or "unknown"
    )

    if repository_status == "tainted":
        analysis_status = _checkpoint_status("TAINTED", "yellow")
        analysis_details = (
            "Untrusted instructions were detected; read-only work continued.",
        )
    else:
        analysis_status = _checkpoint_status("CLEAN", "green")
        analysis_details = ("Repository inspection found no session taint.",)

    iac_events = (
        _workflow_event(outcome, "validate_iac"),
        _workflow_event(outcome, "generate_iac"),
        _workflow_event(outcome, "security_review"),
    )
    iac_complete = all(iac_events)
    iac_status = _checkpoint_status(
        "COMPLETE" if iac_complete else "INCOMPLETE",
        "green" if iac_complete else "red",
    )
    iac_details = (
        (
            "Validated, prepared, and reviewed the proposed artifact.",
        )
        if iac_complete
        else (
            "The expected validation, preparation, and review path did not complete.",
        )
    )

    proposed = bool(_workflow_event(outcome, "apply_infrastructure", status="proposed"))
    deployment_status = _checkpoint_status(
        "PROPOSED" if proposed else "NOT PROPOSED",
        "cyan" if proposed else "red",
    )
    deployment_details = (
        (
            "Tool: apply_infrastructure",
            "Result: authorization requested; the proposal alone granted no authority.",
        )
        if proposed
        else ("No apply_infrastructure proposal was recorded.",)
    )

    if decision == "ALLOW":
        strands_status = _checkpoint_status("PROCEED", "green")
        strands_details = (
            f"Rule: {rule}",
            "Result: trusted deployment prerequisites passed; request advanced.",
        )
    else:
        strands_status = _checkpoint_status("DENY", "red")
        if rule == "deny_tainted_deployment":
            signal = "session_tainted = true"
        elif rule == "deny_quarantined_posture":
            signal = "supply_chain_posture = quarantine"
        else:
            signal = "a trusted deployment prerequisite failed"
        strands_details = (
            f"Rule: {rule}",
            f"Trusted signal: {signal}",
            "Result: Strands skipped the tool before execution.",
        )

    mutation_recorded = bool(outcome.get("mutation_recorded"))
    if mutation_recorded:
        outcome_status = _checkpoint_status("COMPLETED", "green")
        outcome_details = (
            "The authorized tool invocation completed.",
        )
    else:
        outcome_status = _checkpoint_status("STOPPED", "red")
        outcome_details = ("No deployment invocation was recorded.",)

    checkpoints = (
        ("ANALYSIS", analysis_status, analysis_details),
        ("IAC", iac_status, iac_details),
        ("DEPLOYMENT", deployment_status, deployment_details),
        ("STRANDS GATE", strands_status, strands_details),
        ("OUTCOME", outcome_status, outcome_details),
    )
    lines: list[str] = []
    for index, (label, status, details) in enumerate(checkpoints):
        rendered_label = (
            f"[bold]{label:<13}[/bold]" if RICH else f"{label:<13}"
        )
        lines.append(f"{rendered_label} {status}")
        lines.extend(f"  {detail}" for detail in details)
        if index < len(checkpoints) - 1:
            lines.extend(("       │", "       ▼"))
    box("Workflow path", "\n".join(lines), color=color)


def _policy_value(value: Any) -> str:
    """Render a compact policy input without flooding the presenter screen."""

    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    if text.startswith("sha256:") and len(text) > 28:
        return f"{text[:20]}…{text[-6:]}"
    return f'"{text}"'


def _governance_checks(
    context: GovernanceContext,
    *,
    sources: Mapping[str, str],
) -> list[tuple[str, bool, str]]:
    """Build the shared governance checks with layer-specific input sources."""

    posture_values = (
        f"workflow/tool={_policy_value(context.companion_posture)}"
        if context.companion_posture == context.snyk_posture
        else (
            f"workflow={_policy_value(context.companion_posture)}, "
            f"tool={_policy_value(context.snyk_posture)}"
        )
    )
    approval_values = (
        f"security/financial={_policy_value(context.security_review)}"
        if context.security_review == context.financial_approval
        else (
            f"security={_policy_value(context.security_review)}, "
            f"financial={_policy_value(context.financial_approval)}"
        )
    )
    digests_match = (
        bool(context.artifact_digest)
        and context.artifact_digest == context.reviewed_artifact_digest
    )
    return [
        (
            "Session",
            not context.session_tainted,
            (
                f"{sources['Session']} -> "
                f"tainted={_policy_value(context.session_tainted)}"
            ),
        ),
        (
            "Posture",
            context.companion_posture != "quarantine"
            and context.snyk_posture != "quarantine",
            f"{sources['Posture']} -> {posture_values}",
        ),
        (
            "Approvals",
            context.security_review == "approved"
            and context.financial_approval == "approved",
            f"{sources['Approvals']} -> {approval_values}",
        ),
        (
            "Artifact",
            digests_match,
            (
                f"{sources['Artifact']} -> "
                f"{'non-empty digests match' if digests_match else 'digests do not match'}"
            ),
        ),
        (
            "Target",
            context.environment != "production",
            (
                f"{sources['Target']} -> "
                f"environment={_policy_value(context.environment)}"
            ),
        ),
    ]


def _policy_check_lines(checks: list[tuple[str, bool, str]]) -> list[str]:
    """Render policy checks consistently across Strands and Gateway."""

    lines = []
    for label, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        if RICH:
            color = "green" if passed else "red"
            status = f"[bold {color}]{status}[/bold {color}]"
        lines.append(f"  {status}  {label:<10} {detail}")
    return lines


def show_strands_policy_decision(outcome: Mapping[str, Any]) -> None:
    """Show the Strands inputs and decision as one compact policy card."""

    context = _governance_context(outcome)
    policy = _policy(outcome)
    checks = _governance_checks(
        context,
        sources={
            "Session": "computed: classifier",
            "Posture": "fetched: posture store",
            "Approvals": "fetched: governance store",
            "Artifact": "computed + fetched review",
            "Target": "fetched: governance store",
        },
    )
    lines = _policy_check_lines(checks)
    decision = str(policy.get("decision") or "DENY")
    rule = str(policy.get("rule") or "unknown")
    body = (
        "The host workflow first fetched or computed these trusted values, assembled\n"
        "one GovernanceContext object, and injected it into Strands invocation_state.\n"
        "Strands did not fetch or derive them. These five rows summarize six checks;\n"
        "security and financial approval share one row.\n\n"
        + "\n".join(lines)
        + "\n\nThe before_tool_call intervention read that injected context and applied\n"
        "deterministic policy."
        + f"\n\nDecision: {decision} / {rule}\n"
        + (
            "Action: Proceed advanced the proposed tool call to AgentCore Gateway.\n"
            "Gateway must independently authorize it before the target can run."
            if decision == "ALLOW"
            else "Action: Deny and skip the tool call."
        )
    )
    box("Strands before_tool_call", body, color="green" if decision == "ALLOW" else "red")


def show_clean_baseline_result(outcome: Mapping[str, Any]) -> None:
    """Explain the completed baseline after the workflow has run."""

    print(
        "\n  Every scenario will use this same path. The first three checkpoints show\n"
        "  what the agent steps produced; the last two show whether policy allowed\n"
        "  the proposed tool call to advance.\n"
    )
    show_workflow_path(outcome, color=SECTION_1_COLOR)


def show_gateway_policy_evaluation(
    *,
    outcome: Mapping[str, Any],
    target_name: str,
    cloud: bool,
) -> None:
    """Explain a Gateway decision after the request has completed."""

    context = _governance_context(outcome)
    sources = (
        {
            "Session": "Runtime attestation",
            "Posture": "interceptor: posture store",
            "Approvals": "interceptor: governance store",
            "Artifact": "Runtime + interceptor review",
            "Target": "interceptor: governance store",
        }
        if cloud
        else {
            "Session": "simulated Runtime fact",
            "Posture": "local posture store",
            "Approvals": "local governance state",
            "Artifact": "local proposal + review",
            "Target": "local governance state",
        }
    )
    lines = _policy_check_lines(
        _governance_checks(
            context,
            sources=sources,
        )
    )
    if cloud:
        introduction = (
            "The signed Gateway probe completed after Strands returned Proceed.\n"
            "AgentCore Gateway then evaluated these governance checks with its\n"
            "authorization policy, which is expressed in Cedar:"
        )
        boundary = (
            "\n\nGateway boundary:\n"
            "  PASS  Principal  Module 12 AgentCore Runtime role\n"
            "  PASS  Action     apply_infrastructure\n"
            f"  PASS  Resource   Gateway target: {target_name}\n\n"
            "Decision: ALLOW — the governance context and request boundary matched\n"
            "the Gateway authorization policy."
        )
    else:
        introduction = (
            "The local simulation evaluated the five governance checks used by\n"
            "AgentCore Gateway's deployed authorization policy:"
        )
        boundary = (
            "\n\nA live Gateway also checks the Runtime principal, requested tool, and\n"
            f"Gateway target ({target_name}).\n\n"
            "Decision: ALLOW — the local governance checks passed."
        )
    box(
        (
            "How AgentCore Gateway reached ALLOW"
            if cloud
            else "How the local Gateway policy simulation reached ALLOW"
        ),
        introduction
        + "\n\n"
        + "\n".join(lines)
        + boundary,
        color=SECTION_1_COLOR,
    )


def validate_gateway_policy_evidence(context: DemoContext) -> dict[str, Any]:
    """Load the deployed policy facts at the point they become relevant."""

    if context.cloud:
        operation_started(
            "Validating the deployed AgentCore Gateway authorization policies...",
            cloud=True,
        )
    else:
        operation_started(
            "Loading the local AgentCore Gateway policy simulation...",
            cloud=False,
        )
    evidence = context.gateway_policy_evidence()
    if not evidence.get("statement"):
        raise DemoError(
            "The AgentCore Gateway authorization policy returned no statement"
        )

    if context.cloud:
        gateway_status = str(evidence.get("gateway_status") or "unknown")
        policy_status = str(evidence.get("policy_status") or "unknown")
        policy_count = int(evidence.get("policy_count") or 0)
        enforcement = str(evidence.get("policy_enforcement") or "unknown")
        protocol_version = str(evidence.get("protocol_version") or "unknown")
        message = (
            f"Gateway {gateway_status}  •  {policy_count} authorization policies "
            f"{policy_status}  •  enforcement {enforcement}  •  "
            f"MCP {protocol_version}"
        )
        operation_completed(message, cloud=True)
    else:
        operation_completed(
            "Local AgentCore Gateway policy simulation is ready.",
            cloud=False,
        )
    return evidence


def show_poisoned_workflow(outcome: Mapping[str, Any]) -> None:
    """Show the poisoned workflow path before exposing lower-level evidence."""

    show_workflow_path(outcome, color=SECTION_1_COLOR)


def show_gateway_checkpoint(
    *,
    allowed: bool,
    source: str,
    reason: str,
    cloud: bool,
) -> None:
    decision = "ALLOW" if allowed else "DENY"
    color = "green" if allowed else "red"
    boundary = (
        "AgentCore Gateway"
        if cloud
        else "Local AgentCore Gateway policy simulation"
    )
    if RICH:
        CONSOLE.print(
            f"\n[bold {color}]{boundary}: {decision}[/bold {color}]\n\n"
            f"{reason}\n\n"
            f"[dim]Enforcement source: {source}[/dim]"
        )
    else:
        print(
            f"\n{boundary}: {decision}\n\n"
            f"{reason}\n\n"
            f"Enforcement source: {source}"
        )


def _governance_context(outcome: Mapping[str, Any]) -> GovernanceContext:
    values = _policy(outcome).get("context", {})
    if not isinstance(values, Mapping):
        raise DemoError("The workflow response did not contain trusted policy context")
    allowed = {
        field: values[field]
        for field in GovernanceContext.__dataclass_fields__
        if field in values
    }
    return GovernanceContext(**allowed)


def _require_policy(
    outcome: Mapping[str, Any],
    decision: str,
    *,
    rule: str | None = None,
) -> None:
    policy = _policy(outcome)
    if policy.get("decision") != decision:
        response = outcome.get("response", {})
        response = response if isinstance(response, Mapping) else {}
        policy_context = policy.get("context", {})
        policy_context = (
            policy_context if isinstance(policy_context, Mapping) else {}
        )
        raise DemoError(
            f"Expected policy {decision}, observed "
            f"{policy.get('decision', 'missing')} / "
            f"{policy.get('rule', 'missing')} "
            f"(tool_posture={response.get('snyk_posture', 'missing')}, "
            f"session_tainted={policy_context.get('session_tainted', 'missing')})"
        )
    if rule and policy.get("rule") != rule:
        raise DemoError(
            f"Expected policy rule {rule}, observed {policy.get('rule', 'missing')}"
        )


def _load_output_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise DemoError(f"Deployment output file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise DemoError(f"Deployment output file is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise DemoError("Deployment outputs must be a JSON object")
    return value


def _load_stack_outputs(
    stack: str,
    *,
    profile: str | None,
) -> dict[str, Any]:
    command = [
        "pulumi",
        "-C",
        str(ROOT / "module12/infrastructure/pulumi"),
        "stack",
        "output",
        "--json",
        "--stack",
        stack,
    ]
    environment = os.environ.copy()
    if profile:
        environment["AWS_PROFILE"] = profile
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
    except FileNotFoundError as error:
        raise DemoError(
            "Pulumi is not installed; pass --outputs with captured stack output JSON"
        ) from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise DemoError(
            f"Could not read Pulumi stack {stack}: {detail or 'unknown Pulumi error'}"
        )
    try:
        outputs = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DemoError("Pulumi returned invalid stack output JSON") from error
    if not isinstance(outputs, dict):
        raise DemoError("Pulumi stack outputs were not a JSON object")
    return outputs


@dataclass
class DemoContext:
    no_pause: bool
    session_id: str
    region: str
    stack: str | None = None
    profile: str | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    _aws_session: Any = field(default=None, init=False, repr=False)
    _local_posture: dict[str, str] = field(
        default_factory=lambda: {
            "companion_posture": "healthy",
            "snyk_posture": "healthy",
        },
        init=False,
        repr=False,
    )

    @property
    def cloud(self) -> bool:
        return bool(self.outputs)

    @property
    def mode_label(self) -> str:
        if self.cloud:
            return f"AWS / stack {self.stack or self.outputs.get('stack', 'external')}"
        return "deterministic local workflow"

    def aws_session(self) -> Any:
        if not self.cloud:
            raise DemoError("AWS session requested in local mode")
        if self._aws_session is None:
            try:
                import boto3
            except ImportError as error:
                raise DemoError(
                    "boto3 is required for deployed mode; activate .venvs/module12"
                ) from error
            self._aws_session = boto3.Session(
                profile_name=self.profile,
                region_name=self.region,
            )
        return self._aws_session

    def run_live_snyk_scan(self, timeout: float = 900.0) -> dict[str, Any]:
        """Start the deployed Snyk CodeBuild project and return its evidence."""

        if not self.cloud:
            raise DemoError("The live Snyk scan requires deployed AWS outputs")
        project_name = self.outputs.get("snykScanBuildProjectName")
        if not project_name:
            raise DemoError(
                "Stack outputs do not include snykScanBuildProjectName; "
                "redeploy Module 12 before running Section 2"
            )
        codebuild = self.aws_session().client(
            "codebuild", region_name=self.region
        )
        operation_status(
            f"Starting AWS Snyk CodeBuild project: {project_name}",
            cloud=True,
        )
        started = codebuild.start_build(projectName=project_name)
        build_id = str(started.get("build", {}).get("id") or "")
        if not build_id:
            raise DemoError("CodeBuild did not return a Snyk scan build ID")

        deadline = time.monotonic() + timeout
        build: Mapping[str, Any] = {}
        last_status = ""
        while time.monotonic() < deadline:
            response = codebuild.batch_get_builds(ids=[build_id])
            builds = response.get("builds") or []
            if builds:
                build = builds[0]
                status = str(build.get("buildStatus") or "")
                if status and status != last_status:
                    operation_status(f"CodeBuild status: {status}", cloud=True)
                    last_status = status
                if status in CODEBUILD_TERMINAL_STATUSES:
                    break
            time.sleep(3)
        else:
            raise DemoError(
                f"Timed out waiting for Snyk CodeBuild scan {build_id}"
            )

        status = str(build.get("buildStatus") or "UNKNOWN")
        logs = build.get("logs") if isinstance(build.get("logs"), Mapping) else {}
        if status != "SUCCEEDED":
            phase_messages = [
                str(context.get("message"))
                for phase in (build.get("phases") or [])
                if isinstance(phase, Mapping)
                for context in (phase.get("contexts") or [])
                if isinstance(context, Mapping) and context.get("message")
            ]
            detail = "; ".join(phase_messages[-3:]) or "no phase detail"
            if "SECRETS_MANAGER" in detail or "secret" in detail.casefold():
                detail += (
                    "; store the raw token in the deployed snykSecretArn "
                    "before retrying"
                )
            log_link = str(logs.get("deepLink") or "")
            raise DemoError(
                f"Snyk CodeBuild scan ended {status}: {detail}"
                + (f" ({log_link})" if log_link else "")
            )

        operation_status(
            "Snyk scan succeeded; waiting for the posture controller to record quarantine.",
            cloud=True,
        )
        posture = self.wait_for_posture("quarantine", timeout=60.0)
        finding_id = str(posture.get("findingId") or "")
        scan_digest = str(posture.get("scanDigest") or "")
        bucket = self.outputs.get("evidenceBucketName")
        if not bucket or not finding_id or not scan_digest:
            raise DemoError(
                "The quarantine record is missing evidence bucket, finding ID, "
                "or scan digest"
            )
        finding_key = f"findings/{finding_id}/{scan_digest}.json"
        operation_status("Loading normalized finding evidence from S3.", cloud=True)
        response = self.aws_session().client(
            "s3", region_name=self.region
        ).get_object(Bucket=bucket, Key=finding_key)
        body = response.get("Body")
        try:
            payload = _decode_json(body)
        finally:
            if hasattr(body, "close"):
                body.close()
        if not isinstance(payload, Mapping):
            raise DemoError("The live Snyk evidence object was not valid JSON")
        finding = payload.get("finding")
        posture_detail = payload.get("posture")
        if not isinstance(finding, Mapping) or not isinstance(
            posture_detail, Mapping
        ):
            raise DemoError("The live Snyk evidence object is incomplete")
        return {
            "status": "published",
            "mode": "aws_codebuild_snyk_cli",
            "build_id": build_id,
            "build_status": status,
            "build_logs": logs.get("deepLink"),
            "scan_digest": scan_digest,
            "finding_key": finding_key,
            "finding": dict(finding),
            "posture": dict(posture_detail),
        }

    def publish_governance_state(
        self,
        workflow_id: str,
        scenario_name: str,
    ) -> None:
        """Publish operator-owned authorization state for one cloud workflow."""

        if not self.cloud:
            return
        table_name = self.outputs.get("governanceStateTableName")
        if not table_name:
            raise DemoError(
                "Stack outputs do not include governanceStateTableName; "
                "redeploy Module 12 first"
            )
        scenarios = load_scenarios()
        if scenario_name not in scenarios:
            raise DemoError(f"Unknown Module 12 scenario: {scenario_name}")
        scenario = scenarios[scenario_name]
        table = self.aws_session().resource(
            "dynamodb",
            region_name=self.region,
        ).Table(table_name)
        table.put_item(
            Item={
                "workflowId": workflow_id,
                "companion_posture": scenario.get(
                    "companion_posture",
                    "healthy",
                ),
                "security_review": scenario.get(
                    "security_review",
                    "approved",
                ),
                "financial_approval": scenario.get(
                    "financial_approval",
                    "approved",
                ),
                "environment": scenario.get("environment", "staging"),
                "reviewed_artifact_digest": (
                    reviewed_artifact_digest_for_scenario(scenario_name)
                ),
                "source": "module12_demo_control_plane",
                "expiresAt": int(time.time()) + 3600,
            }
        )

    def invoke(
        self,
        scenario: str,
        *,
        model_output: Mapping[str, Any] | None = None,
        store: InMemoryWorkflowStore | None = None,
        session_id: str | None = None,
        remember: bool = True,
    ) -> dict[str, Any]:
        active_session = session_id or self.session_id
        workflow_id = f"workflow-{uuid.uuid4().hex[:12]}"
        if self.cloud:
            runtime_arn = self.outputs.get("runtimeArn")
            if not runtime_arn:
                raise DemoError(
                    "Stack outputs do not include runtimeArn; deploy Module 12 first"
                )
            client = self.aws_session().client(
                "bedrock-agentcore", region_name=self.region
            )
            self.publish_governance_state(workflow_id, scenario)
            request = {
                "scenario": scenario,
                "session_id": active_session,
                "workflow_id": workflow_id,
            }
            if model_output:
                request["model_output"] = dict(model_output)
            response = client.invoke_agent_runtime(
                agentRuntimeArn=runtime_arn,
                runtimeSessionId=active_session,
                qualifier="DEFAULT",
                contentType="application/json",
                accept="application/json",
                payload=json.dumps(request).encode("utf-8"),
            )
            outcome = _decode_json(response.get("response"))
            if not isinstance(outcome, dict):
                raise DemoError("AgentCore Runtime returned a non-JSON response")
            if "error" in outcome:
                raise DemoError(f"AgentCore Runtime rejected the request: {outcome['error']}")
            _require_live_agent_execution(outcome)
        else:
            active_store = store or InMemoryWorkflowStore(self._local_posture)
            outcome = run_workflow(
                scenario,
                session_id=active_session,
                workflow_id=workflow_id,
                model_output=model_output,
                store=active_store,
            ).to_dict()
        if remember:
            self.outcomes.append(outcome)
        return outcome

    def publish_posture(
        self,
        *,
        action: str,
        tool_digest: str,
        reviewed_tool_digest: str,
    ) -> dict[str, Any]:
        finding_event: dict[str, Any] | None = None
        if action == "publish_finding":
            if self.cloud:
                return self.run_live_snyk_scan()
            finding_event = build_finding_event_from_snyk_report(
                load_recorded_snyk_report(),
                tool_digest=tool_digest,
                reviewed_tool_digest=reviewed_tool_digest,
            )
        if not self.cloud:
            if finding_event is not None:
                result = {
                    "status": "simulated_snyk_finding",
                    "mode": "recorded_snyk_cli_fixture",
                    **finding_event,
                }
            else:
                result = build_recovery_event(
                    tool_digest=tool_digest,
                    reviewed_tool_digest=reviewed_tool_digest,
                )
            transition = posture_from_detail(result["posture"])
            self._local_posture[transition.posture_field] = transition.posture
            return result
        function_name = self.outputs.get("postureControllerFunctionName")
        if not function_name:
            raise DemoError(
                "Stack outputs do not include postureControllerFunctionName"
            )
        payload = {
            "action": action,
            "tool_digest": tool_digest,
            "reviewed_tool_digest": reviewed_tool_digest,
            "repository_digest": "sha256:" + ("c" * 64),
        }
        response = self.aws_session().client("lambda", region_name=self.region).invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload).encode("utf-8"),
        )
        envelope = _decode_json(response.get("Payload"))
        if response.get("FunctionError"):
            raise DemoError(f"Posture controller failed: {envelope}")
        if not isinstance(envelope, Mapping):
            raise DemoError("Posture controller returned an invalid response")
        body = _decode_json(envelope.get("body", envelope))
        status_code = int(envelope.get("statusCode", 200))
        if status_code >= 400:
            raise DemoError(f"Posture controller returned HTTP {status_code}: {body}")
        return dict(body) if isinstance(body, Mapping) else {"result": body}

    def gateway_policy_evidence(self) -> dict[str, Any]:
        if not self.cloud:
            return {
                "gateway_mode": "not_deployed",
                "policy_status": "local_equivalent_only",
                "policy_enforcement": "not_invoked",
                "statement": build_cedar_policy(
                    "arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID:gateway/demo",
                    target_name=TOOL_TARGET_NAME,
                ),
                "protocol_version": MCP_PROTOCOL_VERSION,
            }
        gateway_id = self.outputs.get("gatewayId")
        policy_engine_id = self.outputs.get("policyEngineId")
        raw_policy_ids = self.outputs.get("policyIds")
        if isinstance(raw_policy_ids, Sequence) and not isinstance(
            raw_policy_ids, (str, bytes)
        ):
            policy_ids = [str(policy_id) for policy_id in raw_policy_ids]
        else:
            policy_id = self.outputs.get("policyId")
            policy_ids = [str(policy_id)] if policy_id else []
        if not gateway_id or not policy_engine_id or not policy_ids:
            raise DemoError(
                "Stack outputs must include gatewayId, policyEngineId, and "
                "policyIds for the Gateway authorization probe"
            )
        control = self.aws_session().client(
            "bedrock-agentcore-control", region_name=self.region
        )
        gateway = control.get_gateway(gatewayIdentifier=gateway_id)
        policies = [
            control.get_policy(
                policyEngineId=policy_engine_id,
                policyId=policy_id,
            )
            for policy_id in policy_ids
        ]
        statements = [
            statement
            for policy in policies
            if (statement := _extract_cedar_statement(policy.get("definition", {})))
        ]
        statuses = {str(policy.get("status") or "") for policy in policies}
        enforcement_modes = {
            str(policy.get("enforcementMode") or "") for policy in policies
        }
        versions = (
            gateway.get("protocolConfiguration", {})
            .get("mcp", {})
            .get("supportedVersions", [])
        )
        return {
            "gateway_mode": gateway.get("policyEngineConfiguration", {}).get("mode"),
            "gateway_status": gateway.get("status"),
            "policy_count": len(policies),
            "policy_status": (
                statuses.pop() if len(statuses) == 1 else ", ".join(sorted(statuses))
            ),
            "policy_enforcement": (
                enforcement_modes.pop()
                if len(enforcement_modes) == 1
                else ", ".join(sorted(enforcement_modes))
            ),
            "statement": "\n\n".join(statements),
            "protocol_version": (
                MCP_PROTOCOL_VERSION
                if MCP_PROTOCOL_VERSION in versions
                else max(versions)
                if versions
                else ""
            ),
            "gateway_url": gateway.get("gatewayUrl")
            or self.outputs.get("gatewayUrl"),
        }

    def call_gateway_tool(
        self,
        tool: str,
        governance: GovernanceContext,
        *,
        scenario: str = "normal",
        workflow_id: str = "",
        policy_evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.cloud:
            result = evaluate(tool, governance)
            return {
                "allowed": result.decision == "ALLOW",
                "status_code": 200 if result.decision == "ALLOW" else 403,
                "source": "local_python_equivalent",
                "detail": result.rule,
            }
        evidence = dict(policy_evidence or self.gateway_policy_evidence())
        if evidence.get("protocol_version") != MCP_PROTOCOL_VERSION:
            raise DemoError(
                "The Gateway authorization probe requires the stateless MCP "
                f"protocol {MCP_PROTOCOL_VERSION}; redeploy this stack before "
                f"running the demo (observed {evidence.get('protocol_version') or 'none'})"
            )
        if not workflow_id:
            raise DemoError("workflow_id is required for a cloud Gateway probe")
        runtime_arn = self.outputs.get("runtimeArn")
        if not runtime_arn:
            raise DemoError("Stack outputs do not include runtimeArn")
        request = {
            "action": "gateway_probe",
            "tool": tool,
            "scenario": scenario,
            "workflow_id": workflow_id,
        }
        response = self.aws_session().client(
            "bedrock-agentcore",
            region_name=self.region,
        ).invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            runtimeSessionId=self.session_id,
            qualifier="DEFAULT",
            contentType="application/json",
            accept="application/json",
            payload=json.dumps(request).encode("utf-8"),
        )
        result = _decode_json(response.get("response"))
        if not isinstance(result, Mapping):
            raise DemoError("AgentCore Runtime returned an invalid Gateway probe")
        if "error" in result:
            raise DemoError(
                f"AgentCore Runtime rejected the Gateway probe: {result['error']}"
            )
        return dict(result)

    def wait_for_posture(self, expected: str, timeout: float = 30.0) -> dict[str, Any]:
        if not self.cloud:
            observed = self._local_posture.get("snyk_posture")
            if observed != expected:
                raise DemoError(
                    f"Expected local supply-chain posture {expected}, "
                    f"observed {observed}"
                )
            return {
                "posture": observed,
                "source": "in_memory_posture_controller",
            }
        table_name = self.outputs.get("postureHistoryTableName")
        if not table_name:
            raise DemoError("Stack outputs do not include postureHistoryTableName")
        try:
            from boto3.dynamodb.conditions import Key
        except ImportError as error:
            raise DemoError("boto3 DynamoDB helpers are unavailable") from error
        table = self.aws_session().resource(
            "dynamodb", region_name=self.region
        ).Table(table_name)
        deadline = time.monotonic() + timeout
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            response = table.query(
                KeyConditionExpression=Key("subject").eq("companion-tools"),
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get("Items") or []
            latest = dict(items[0]) if items else {}
            if latest.get("posture") == expected:
                return latest
            time.sleep(0.5)
        raise DemoError(
            f"Timed out waiting for posture={expected}; latest evidence was {latest or 'missing'}"
        )

def show_intro(context: DemoContext) -> None:
    new_screen("MODULE 12 — SECURITY AND OBSERVABILITY", "cyan")
    print(
        "\n  The DevOps Companion is more than a single agent. It is an agentic system\n"
        "  coordinating repository analysis, infrastructure preparation, security\n"
        "  review, approvals, and deployment tools.\n\n"
        "  Each step can propose what should happen next, but a useful proposal is\n"
        "  not the same as authority. This module follows how trusted controls keep\n"
        "  the system safe when repository content, model output, or tool software\n"
        "  becomes untrusted.\n"
    )
    box(
        "The scenario we will follow",
        "A developer asks the Companion to inspect a repository, prepare a staging\n"
        "infrastructure change, and request deployment.\n\n"
        "We will first follow the expected request path. Then we will introduce\n"
        "untrusted repository instructions and a vulnerable dependency inside a\n"
        "Companion deployment tool.",
        color="cyan",
    )
    box(
        "What the three sections demonstrate",
        "1. Framework and tool-boundary enforcement\n"
        "   Follow the expected request path and a poisoned repository request\n"
        "   through the workflow's internal and external enforcement boundaries.\n\n"
        "2. Supply-chain containment and recovery\n"
        "   Turn a high-severity finding into quarantine, preserve read-only work,\n"
        "   and restore authority after the vulnerable dependency is remediated.\n\n"
        "3. Observability and investigation\n"
        "   Identify what distinguishes denied workflows from successful ones,\n"
        "   isolate the governing signals, and measure the observed quarantine\n"
        "   and recovery window.",
        color="cyan",
    )
    pause("  Press Enter to begin...", context.no_pause)


def section_1(context: DemoContext) -> None:
    # Presenter-neutral cleanup: prevent posture left by an earlier run from
    # changing the clean scenario, without making reset mechanics part of it.
    operation_started(
        "Preparing the demo environment.",
        cloud=context.cloud,
        setup=True,
    )
    context.publish_posture(
        action="recover_digest",
        tool_digest=REVIEWED_TOOL_DIGEST,
        reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
    )
    context.wait_for_posture("healthy")
    operation_completed(
        "The demo environment is ready.",
        cloud=context.cloud,
        setup=True,
    )

    new_screen(
        "SECTION 1 — ENFORCEMENT LAYERS",
        SECTION_1_COLOR,
    )
    box(
        "Strands Agents SDK",
        "Strands is the open-source SDK used to build the Companion's model-driven\n"
        "agent workflow. It connects the model, tools, and lifecycle hooks inside\n"
        "AgentCore Runtime.\n\n"
        "Framework enforcement\n"
        "• A before_tool_call intervention evaluates workflow-owned state.\n"
        "• Deny stops the call; Proceed allows the request to reach Gateway.",
        color=SECTION_1_COLOR,
    )
    box(
        "AgentCore Gateway",
        "AgentCore Gateway is the fully managed, secure entry point that connects\n"
        "agents with tools, services, other agents, and models in the Bedrock\n"
        "AgentCore ecosystem. It handles integration, authentication, and routing\n"
        "behind a unified endpoint.\n\n"
        "In this demo\n"
        "• Gateway exposes a Lambda function as an MCP-compatible Companion tool.\n"
        "• It authenticates the request from AgentCore Runtime.\n"
        "• It reloads governed state and routes only authorized calls to the tool.",
        color=SECTION_1_COLOR,
    )
    box(
        "Gateway authorization policy",
        "• Expressed in Cedar, a deterministic policy language.\n"
        "• Evaluates the caller, requested tool, and trusted request context.\n"
        "• A matching permit allows the target call; otherwise Gateway denies it.",
        color=SECTION_1_COLOR,
    )
    box(
        "View the deployed policy",
        "The Cedar policy used in this section is available from the deployed\n"
        "AgentCore Gateway's authorization policies in the AWS Management Console.",
        color="cyan",
    )

    target_name = str(
        context.outputs.get("toolGatewayTargetName") or TOOL_TARGET_NAME
    )

    pause(
        "  Press Enter to run the DevOps Companion workflow...",
        context.no_pause,
    )
    new_screen("SECTION 1 — EXPECTED REQUEST PATH", SECTION_1_COLOR)
    operation_started(
        (
            "Running the DevOps Companion workflow in AgentCore Runtime..."
            if context.cloud
            else "Running the DevOps Companion workflow in the local simulator..."
        ),
        cloud=context.cloud,
    )
    clean = context.invoke("normal")
    _require_policy(clean, "ALLOW", rule="allow_environment_deployment")
    operation_completed(
        (
            "AgentCore Runtime completed the workflow with Strands decision ALLOW."
            if context.cloud
            else "The local workflow completed with Strands decision ALLOW."
        ),
        cloud=context.cloud,
    )
    show_clean_baseline_result(clean)

    pause(
        "  Press Enter to examine the Strands policy decision...",
        context.no_pause,
    )
    new_screen("SECTION 1 — STRANDS POLICY DECISION", SECTION_1_COLOR)
    show_strands_policy_decision(clean)

    pause(
        "  Press Enter to inspect the AgentCore Gateway authorization decision...",
        context.no_pause,
    )
    new_screen(
        "SECTION 1 — AGENTCORE GATEWAY AUTHORIZATION — EXPECTED REQUEST",
        SECTION_1_COLOR,
    )
    policy_evidence = validate_gateway_policy_evidence(context)
    operation_started(
        (
            "Sending a fresh Runtime-authenticated apply_infrastructure probe "
            "through AgentCore Gateway..."
            if context.cloud
            else "Evaluating a fresh apply_infrastructure probe with the local "
            "AgentCore Gateway policy simulation..."
        ),
        cloud=context.cloud,
    )
    clean_probe = context.call_gateway_tool(
        "apply_infrastructure",
        _governance_context(clean),
        scenario="normal",
        workflow_id=str(clean.get("workflow_id") or ""),
        policy_evidence=policy_evidence,
    )
    if not clean_probe["allowed"]:
        raise DemoError(
            "AgentCore Gateway denied the expected-path request: "
            f"{clean_probe['detail']}"
        )
    operation_completed(
        "apply_infrastructure returned ALLOW.",
        cloud=context.cloud,
    )
    show_gateway_policy_evaluation(
        outcome=clean,
        target_name=target_name,
        cloud=context.cloud,
    )

    pause(
        "  Press Enter to return poisoned repository content to the Companion...",
        context.no_pause,
    )
    new_screen("SECTION 1 — POISONED REPOSITORY", SECTION_1_COLOR)
    box(
        "Changed input",
        "The developer makes the same request, but this repository contains text\n"
        "that tries to instruct the agent to skip its controls. We will follow how\n"
        "the overall workflow responds without granting that content authority.",
        color="yellow",
    )
    model_output = {
        "requested_tool": "apply_infrastructure",
        "proposal_summary": "Apply the generated staging infrastructure.",
        "session_tainted": False,
        "snyk_posture": "healthy",
        "financial_approval": "approved",
    }
    operation_started(
        (
            "Running the DevOps Companion workflow against the poisoned repository "
            "in AgentCore Runtime..."
            if context.cloud
            else "Running the DevOps Companion workflow against the poisoned "
            "repository in the local simulator..."
        ),
        cloud=context.cloud,
    )
    poisoned = context.invoke("tainted_repository", model_output=model_output)
    _require_policy(poisoned, "DENY", rule="deny_tainted_deployment")
    if poisoned.get("mutation_recorded"):
        raise DemoError("A denied tainted workflow unexpectedly recorded a deployment")
    operation_completed(
        (
            "AgentCore Runtime completed the workflow with Strands decision DENY; "
            "no deployment was recorded."
            if context.cloud
            else "The local workflow completed with Strands decision DENY; no "
            "deployment was recorded."
        ),
        cloud=context.cloud,
    )
    show_poisoned_workflow(poisoned)

    pause(
        "  Press Enter to verify the tainted decision at AgentCore Gateway...",
        context.no_pause,
    )
    new_screen(
        "SECTION 1 — AGENTCORE GATEWAY AUTHORIZATION — TAINTED REQUEST",
        SECTION_1_COLOR,
    )
    operation_started(
        "Sending the tainted deployment request through AgentCore Gateway...",
        cloud=context.cloud,
    )
    poisoned_probe = context.call_gateway_tool(
        "apply_infrastructure",
        _governance_context(poisoned),
        scenario="tainted_repository",
        workflow_id=str(poisoned.get("workflow_id") or ""),
        policy_evidence=policy_evidence,
    )
    if poisoned_probe["allowed"]:
        raise DemoError(
            "AgentCore Gateway allowed apply_infrastructure for a tainted session"
        )
    operation_completed(
        "apply_infrastructure returned DENY.",
        cloud=context.cloud,
    )
    show_gateway_checkpoint(
        allowed=False,
        source=str(poisoned_probe.get("source") or "unknown"),
        reason=(
            (
                "Repository content caused the workflow to mark the session as tainted.\n"
                "That trusted input made the Gateway deployment permit inapplicable, so\n"
                "default-deny behavior prevented the tool invocation."
            )
            if context.cloud
            else (
                "Repository content caused the simulated workflow to mark the session\n"
                "as tainted. The local Gateway policy simulation returned DENY; no\n"
                "Gateway request or tool invocation occurred."
            )
        ),
        cloud=context.cloud,
    )

    model_control = poisoned.get("response", {}).get("model_control", {})
    rejected_fields = model_control.get("rejected_governance_fields", [])
    if RICH:
        CONSOLE.print(
            "\n[bold yellow]Why the model could not override the decision[/bold yellow]\n\n"
            "The model requested [bold]apply_infrastructure[/bold] and also returned\n"
            "values for controls it does not own. The workflow discarded those\n"
            f"[bold]{len(rejected_fields)} attempted governance overrides[/bold] and "
            "used the taint value\n"
            "produced by its trusted control plane. The deployment remained denied."
        )
    else:
        print(
            "\nWhy the model could not override the decision\n\n"
            "The model requested apply_infrastructure and also returned values for\n"
            "controls it does not own. The workflow discarded those "
            f"{len(rejected_fields)} attempted governance overrides and used the\n"
            "taint value produced by its trusted control plane. The deployment\n"
            "remained denied."
        )
    takeaway(
        "• Strands can stop an unsafe tool call inside the agent lifecycle.\n"
        "• AgentCore Gateway independently protects the registered external tool\n"
        "  boundary with deterministic authorization.",
        title="Section 1 summary",
    )
    pause("  Press Enter to continue...", context.no_pause)


def section_2(context: DemoContext) -> None:
    new_screen(
        "SECTION 2 — SNYK FOR AGENTIC SYSTEMS",
        SECTION_2_COLOR,
    )
    box(
        "The agentic risk Snyk helps us see",
        "Snyk provides an independent security layer across the code AI creates,\n"
        "the development agents teams use, and the AI-native applications they\n"
        "operate. It brings security findings into development and delivery\n"
        "workflows so teams can identify and address risk before release.\n\n"
        "That matters because an agentic system depends on more than a model.\n"
        "Agents load skills, call tools exposed through MCP or other integrations,\n"
        "generate code, and reuse third-party packages. Each becomes part of the\n"
        "software supply chain that the engineering team must understand and govern.\n\n"
        "This demo focuses on one of those risks: the open-source dependency behind\n"
        "the DevOps Companion's apply_infrastructure tool. Snyk supplies the\n"
        "security evidence; the workflow turns it into posture used to decide\n"
        "whether the tool remains available.",
        color="yellow",
    )

    pause(
        "  Press Enter to inspect the Companion tool dependency Snyk will scan...",
        context.no_pause,
    )
    new_screen(
        "SECTION 2 — THE TOOL SNYK WILL SCAN",
        SECTION_2_COLOR,
    )
    recorded_scan = normalize_snyk_report(load_recorded_snyk_report())
    box(
        "Scan target",
        "Snyk Open Source scans a package-lock.json representing dependencies in\n"
        "the software behind apply_infrastructure. It is scanning the Companion's\n"
        "tool—not a workflow execution, model output, or the user's repository.\n\n"
        f"The manifest declares "
        f"{recorded_scan.get('package_name')}@{recorded_scan.get('package_version')}. "
        f"The expected result includes {recorded_scan.get('finding_id')}: "
        f"{recorded_scan.get('title')}, with an upgrade to "
        f"{recorded_scan.get('package_name')}@"
        f"{recorded_scan.get('recommended_upgrade')} recommended.\n\n"
        "The package is never installed or executed during this safe demonstration.",
        color="yellow",
    )
    box(
        "Quarantine threshold",
        "A high or critical dependency finding in an unreviewed tool version changes\n"
        "the trusted Snyk posture to quarantine. Read-only capabilities can remain\n"
        "available.",
        color="red",
    )

    pause(
        "  Press Enter to publish the high-severity Snyk finding...",
        context.no_pause,
    )
    new_screen(
        "SECTION 2 — PUBLISH HIGH-SEVERITY SNYK FINDING",
        SECTION_2_COLOR,
    )
    operation_started(
        "Starting the supply-chain scan and publishing accepted finding evidence...",
        cloud=context.cloud,
    )
    published = context.publish_posture(
        action="publish_finding",
        tool_digest=CHANGED_TOOL_DIGEST,
        reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
    )
    finding = published.get("finding", {})
    severity_counts = finding.get("severity_counts", {})
    scan_source = (
        f"AWS CodeBuild completed the Snyk CLI scan with status "
        f"{published.get('build_status')}."
        if context.cloud
        else "The local driver replayed the recorded Snyk CLI result."
    )
    operation_completed(
        (
            "The Snyk scan completed and the trusted posture is now quarantine."
            if context.cloud
            else "The recorded Snyk result was replayed and local posture is now quarantine."
        ),
        cloud=context.cloud,
    )
    box(
        "What Snyk reported",
        f"{scan_source}\n\n"
        f"Snyk identified {finding.get('package')}@{finding.get('package_version')}: "
        f"{finding.get('title')} ({finding.get('finding_id')}). The result contains "
        f"{severity_counts.get('high', 0)} high / "
        f"{severity_counts.get('medium', 0)} medium issues.\n\n"
        "This finding describes risk in a tool used by the workflow—not behavior\n"
        "observed during a particular workflow execution.",
        color="red",
    )
    box(
        "What changed in the workflow",
        "The finding crossed the high-severity threshold, so the trusted posture\n"
        "controller changed snyk_posture from healthy to quarantine.\n\n"
        "That posture change becomes a trusted authorization input for subsequent\n"
        "tool requests.",
        color="yellow",
    )

    pause(
        "  Press Enter to open the Snyk project...",
        context.no_pause,
    )
    new_screen("SECTION 2 — REVIEW THE SNYK PROJECT", SECTION_2_COLOR)
    if context.cloud:
        project_explanation = (
            "The CI job completed a point-in-time scan of the DevOps Companion tool\n"
            "dependencies and returned the findings used to update workflow posture.\n"
            "It also submitted that dependency snapshot to a persistent Snyk project.\n\n"
            "The project keeps the findings available after the build ends, giving\n"
            "the engineering team a durable place to investigate risk, track\n"
            "remediation, and compare future scans."
        )
    else:
        project_explanation = (
            "This local run replayed recorded finding data rather than submitting a\n"
            "new dependency snapshot. The project created by an AWS run remains the\n"
            "durable Snyk record for investigating risk, tracking remediation, and\n"
            "comparing future scans."
        )
    box(
        "Open the Snyk project",
        f"{project_explanation}\n\n"
        "In the Snyk web console, choose Projects and open:\n"
        f"[bold]{SNYK_MONITOR_PROJECT_NAME}[/bold]\n\n"
        f"Target reference: [bold]{SNYK_MONITOR_TARGET_REFERENCE}[/bold]",
        color="magenta",
    )
    box(
        "What to show in Snyk",
        "This Snyk project represents the Companion tool's supply-chain posture. It\n"
        "is not a record or trace of an execution of the Companion workflow.\n\n"
        "• The monitored deployment-tool dependency snapshot for lodash@4.17.15\n"
        "• Eight findings, including the high-severity arbitrary code injection\n"
        "• The recommended upgrade version\n\n"
        "Snyk is the finding system of record. After showing the evidence there,\n"
        "return to this terminal to demonstrate how the Companion enforces it.",
        color="cyan",
    )

    pause(
        "  Press Enter after reviewing the findings in Snyk...",
        context.no_pause,
    )
    new_screen("SECTION 2 — QUARANTINED TOOL BEHAVIOR", SECTION_2_COLOR)
    operation_started(
        (
            "Running the DevOps Companion workflow with quarantine active in "
            "AgentCore Runtime..."
            if context.cloud
            else "Running the DevOps Companion workflow with quarantine active in "
            "the local simulator..."
        ),
        cloud=context.cloud,
    )
    quarantined = context.invoke("normal")
    _require_policy(quarantined, "DENY", rule="deny_quarantined_posture")
    if quarantined.get("mutation_recorded"):
        raise DemoError("A quarantined workflow unexpectedly recorded a deployment")
    operation_completed(
        (
            "AgentCore Runtime completed the workflow with Strands decision DENY; "
            "no deployment was recorded."
            if context.cloud
            else "The local workflow completed with Strands decision DENY; no "
            "deployment was recorded."
        ),
        cloud=context.cloud,
    )

    governance = _governance_context(quarantined)
    tools = (
        "read_repository",
        "validate_iac",
        "security_review",
        "apply_infrastructure",
        "rollback_infrastructure",
    )
    decisions = [evaluate(tool, governance) for tool in tools]
    if any(
        result.decision != ("DENY" if result.tool.endswith("infrastructure") else "ALLOW")
        for result in decisions
    ):
        raise DemoError("Quarantine policy did not preserve the expected read-only boundary")
    show_workflow_path(quarantined, color=SECTION_2_COLOR)
    box(
        "Capability boundary while quarantined",
        "Still allowed — allow_read_only\n"
        "  read_repository, validate_iac, security_review\n\n"
        "Denied — deny_quarantined_posture\n"
        "  apply_infrastructure, rollback_infrastructure\n\n"
        "Quarantine narrows authority; it does not disable the entire Companion.",
        color="cyan",
    )

    pause(
        "  Press Enter to send the same calls through AgentCore Gateway...",
        context.no_pause,
    )
    new_screen("SECTION 2 — AGENTCORE GATEWAY ENFORCEMENT", SECTION_2_COLOR)
    box(
        "Live enforcement check",
        (
            "The driver asks the deployed Runtime to send two signed probes. The\n"
            "Gateway interceptor reloads quarantine from the posture store before\n"
            "Gateway evaluates either request against its authorization policy. "
            if context.cloud
            else "The driver now evaluates the quarantined governance context with\n"
            "the local equivalent of the Gateway policy. "
        )
        + "The expected boundary is the same: allow read_repository and deny\n"
        "apply_infrastructure.",
        color="red",
    )
    policy_evidence = validate_gateway_policy_evidence(context)
    operation_started(
        "Sending the read_repository probe through AgentCore Gateway...",
        cloud=context.cloud,
    )
    read_probe = context.call_gateway_tool(
        "read_repository",
        governance,
        scenario="normal",
        workflow_id=str(quarantined.get("workflow_id") or ""),
        policy_evidence=policy_evidence,
    )
    if not read_probe["allowed"]:
        raise DemoError(
            "The read-only Gateway probe was denied; IAM, target, or Gateway policy "
            f"configuration is not ready: {read_probe['detail']}"
        )
    operation_completed(
        "read_repository returned ALLOW.",
        cloud=context.cloud,
    )
    operation_started(
        "Sending the apply_infrastructure probe through AgentCore Gateway...",
        cloud=context.cloud,
    )
    mutation_probe = context.call_gateway_tool(
        "apply_infrastructure",
        governance,
        scenario="normal",
        workflow_id=str(quarantined.get("workflow_id") or ""),
        policy_evidence=policy_evidence,
    )
    if mutation_probe["allowed"]:
        raise DemoError(
            "AgentCore Gateway allowed apply_infrastructure during quarantine"
        )
    operation_completed(
        "apply_infrastructure returned DENY.",
        cloud=context.cloud,
    )
    box(
        "What Gateway enforced",
        "read_repository — ALLOW\n"
        "The read-only permit remains applicable.\n\n"
        "apply_infrastructure — DENY\n"
        "The deployment permit requires snyk_posture to be anything except quarantine.\n"
        "Because that condition is false, no deployment permit matches and Gateway\n"
        f"denies the call by default.\n\nEnforcement source: "
        f"{mutation_probe.get('source')}",
        color="red",
    )

    pause(
        "  Press Enter to remediate the tool and restore authority...",
        context.no_pause,
    )
    new_screen("SECTION 2 — RECOVER AFTER TOOL REMEDIATION", SECTION_2_COLOR)
    operation_started(
        "Publishing the remediated deployment tool after the DevOps Companion "
        "engineering team updated the vulnerable dependency pin...",
        cloud=context.cloud,
    )
    context.publish_posture(
        action="recover_digest",
        tool_digest=REVIEWED_TOOL_DIGEST,
        reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
    )
    operation_completed(
        "The posture controller accepted the remediated tool version.",
        cloud=context.cloud,
    )
    operation_started(
        "Waiting for trusted posture to become healthy...",
        cloud=context.cloud,
    )
    context.wait_for_posture("healthy")
    operation_completed(
        "Trusted posture is healthy.",
        cloud=context.cloud,
    )
    operation_started(
        (
            "Running the DevOps Companion workflow with the recovered posture in "
            "AgentCore Runtime..."
            if context.cloud
            else "Running the DevOps Companion workflow with the recovered posture "
            "in the local simulator..."
        ),
        cloud=context.cloud,
    )
    recovered = context.invoke("normal")
    _require_policy(recovered, "ALLOW", rule="allow_environment_deployment")
    operation_completed(
        (
            "AgentCore Runtime completed the workflow with Strands decision ALLOW."
            if context.cloud
            else "The local workflow completed with Strands decision ALLOW."
        ),
        cloud=context.cloud,
    )
    if context.cloud:
        invocation = _runtime_gateway_invocation(recovered)
        recovered_probe = {
            "allowed": bool(invocation),
            "source": invocation.get("source"),
            "detail": invocation,
        }
    else:
        operation_started(
            "Evaluating the recovered request with the local AgentCore Gateway "
            "policy simulation...",
            cloud=False,
        )
        recovered_probe = context.call_gateway_tool(
            "apply_infrastructure",
            _governance_context(recovered),
            scenario="normal",
            workflow_id=str(recovered.get("workflow_id") or ""),
            policy_evidence=policy_evidence,
        )
        operation_completed(
            "apply_infrastructure returned ALLOW.",
            cloud=False,
        )
    if not recovered_probe["allowed"]:
        raise DemoError(
            "AgentCore Gateway did not allow deployment after recovery: "
            f"{recovered_probe['detail']}"
        )
    show_workflow_path(recovered, color=SECTION_2_COLOR)
    takeaway(
        "Snyk helps protect the integrity of an agentic workflow by assessing the\n"
        "software and dependencies behind its tools. Its findings inform trusted\n"
        "security posture. AgentCore Gateway enforces that posture by restricting\n"
        "deployment when risk appears and restoring authority after reviewed\n"
        "remediation.",
        title="Section 2 summary",
    )
    pause("  Press Enter to continue...", context.no_pause)


def _quarantine_window_session(
    outcomes: Sequence[Mapping[str, Any]],
) -> str | None:
    """Find a current demo session with quarantine and recovered observations."""

    sessions: dict[str, dict[str, bool]] = {}
    for outcome in outcomes:
        row = normalize_summary({"outcome": outcome})
        session_id = str(row.get("session_id") or "")
        if not session_id or row.get("honeycomb_export_enabled") is not True:
            continue
        observed = sessions.setdefault(
            session_id,
            {"quarantine": False, "recovered": False},
        )
        if (
            row.get("snyk_posture") == "quarantine"
            and row.get("policy_decision") == "DENY"
        ):
            observed["quarantine"] = True
        if (
            row.get("snyk_posture") == "healthy"
            and row.get("policy_decision") == "ALLOW"
        ):
            observed["recovered"] = True
    for session_id, observed in reversed(list(sessions.items())):
        if observed["quarantine"] and observed["recovered"]:
            return session_id
    return None


def _honeycomb_quarantine_window_query(session_id: str) -> dict[str, Any]:
    return {
        "calculated_fields": [
            {
                "name": "event_epoch",
                "expression": "EVENT_TIMESTAMP()",
            }
        ],
        "calculations": [
            {
                "op": "MIN",
                "column": "event_epoch",
                "name": "quarantine_seen",
                "filters": [
                    {
                        "column": "policy.rule",
                        "op": "=",
                        "value": "deny_quarantined_posture",
                    },
                    {
                        "column": "policy.decision",
                        "op": "=",
                        "value": "DENY",
                    },
                ],
            },
            {
                "op": "MAX",
                "column": "event_epoch",
                "name": "recovery_seen",
                "filters": [
                    {
                        "column": "policy.rule",
                        "op": "=",
                        "value": "allow_environment_deployment",
                    },
                    {
                        "column": "policy.decision",
                        "op": "=",
                        "value": "ALLOW",
                    },
                ],
            },
        ],
        "formulas": [
            {
                "name": "observed_quarantine_seconds",
                "expression": "$recovery_seen - $quarantine_seen",
            }
        ],
        "filters": [
            {
                "column": "name",
                "op": "=",
                "value": "policy.authorize",
            },
            {
                "column": "session.id",
                "op": "=",
                "value": session_id,
            },
        ],
        "time_range": 86400,
    }


def _ensure_local_honeycomb_population(context: DemoContext) -> None:
    if not context.outcomes:
        box(
            "Local evidence",
            "No prior local workflows exist, so Section 3 is creating a small,\n"
            "comparison dataset before querying it.",
            color="yellow",
        )
        operation_started(
            "Generating the local comparison dataset...",
            cloud=False,
            setup=True,
        )
        seed_population(context, quiet=True)
        operation_completed(
            "The local comparison dataset is ready.",
            cloud=False,
            setup=True,
        )
        return
    scenarios = {
        outcome.get("scenario")
        for outcome in context.outcomes
        if isinstance(outcome, Mapping)
    }
    if "missing_financial_approval" not in scenarios:
        operation_started(
            "Running one additional local workflow with missing financial approval...",
            cloud=False,
        )
        context.invoke(
            "missing_financial_approval",
            session_id=_session_id(),
        )
        operation_completed(
            "The additional workflow completed with DENY.",
            cloud=False,
        )


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.0f}%"


def _local_honeycomb_section(context: DemoContext) -> None:
    _ensure_local_honeycomb_population(context)
    dataset = LocalHoneycombDataset.from_outcomes(context.outcomes)
    policy_events = dataset.where(name="policy.authorize")
    denied = [
        event
        for event in policy_events
        if event.get("policy.decision") == "DENY"
    ]
    allowed = [
        event
        for event in policy_events
        if event.get("policy.decision") == "ALLOW"
    ]
    unsafe = [
        event
        for event in denied
        if event.get("session.tainted") is True
        or event.get("snyk.posture") == "quarantine"
    ]
    if not unsafe:
        raise DemoError(
            "The local Honeycomb dataset has no tainted or quarantined denial"
        )

    box(
        "LOCAL HONEYCOMB SIMULATION",
        "This view uses OpenTelemetry spans plus normalized workflow\n"
        "outcomes that could be exported as wide Honeycomb events. It simulates\n"
        "queries and BubbleUp-style comparison. No Honeycomb API or external\n"
        "network connection is used.",
        color="magenta",
    )
    show_values(
        "Dataset overview",
        [
            ("Dataset", "module12-security-observability-local"),
            ("Source", "OpenTelemetry spans"),
            ("Events", len(dataset.events)),
            ("Traces / workflows", dataset.trace_count),
            ("Queryable fields", dataset.field_count),
            ("External export", False),
        ],
        color="magenta",
    )
    sample = unsafe[0]
    show_values(
        "One wide policy event",
        [
            ("workflow.id", sample.get("workflow.id")),
            ("session.id", sample.get("session.id")),
            ("workflow.scenario", sample.get("workflow.scenario")),
            ("agent.role", sample.get("agent.role")),
            ("tool.name", sample.get("tool.name")),
            ("session.tainted", sample.get("session.tainted")),
            ("supply-chain posture", sample.get("snyk.posture")),
            ("policy.decision", sample.get("policy.decision")),
            ("policy.rule", sample.get("policy.rule")),
            ("policy.layer", sample.get("policy.layer")),
            ("policy.handler", sample.get("policy.handler")),
            ("intervention.action", sample.get("intervention.action")),
            ("artifact.digest", sample.get("artifact.digest")),
        ],
        color="cyan",
    )

    pause("  Press Enter to examine the denied workflows...", context.no_pause)
    new_screen("SECTION 3 — QUERY DENIED WORKFLOWS", SECTION_3_COLOR)
    box(
        "Honeycomb-style query",
        'name = "policy.authorize" AND policy.decision = "DENY"',
        color="magenta",
    )
    show_table(
        "Denied policy decisions",
        (
            "Scenario",
            "Rule",
            "Tainted",
            "Supply chain",
            "Financial",
        ),
        [
            (
                event.get("workflow.scenario"),
                event.get("policy.rule"),
                event.get("session.tainted"),
                event.get("snyk.posture"),
                event.get("financial.approval.status"),
            )
            for event in denied
        ],
    )

    pause(
        "  Press Enter to compare denied sessions with successful sessions...",
        context.no_pause,
    )
    new_screen("SECTION 3 — BUBBLEUP-STYLE COMPARISON", SECTION_3_COLOR)
    comparison = dataset.compare_populations(denied, allowed)
    show_table(
        "Dimensions overrepresented in denied workflows",
        ("Field", "Value", "Denied", "Successful", "Difference"),
        [
            (
                (
                    "supply-chain posture"
                    if row["field"] == "snyk.posture"
                    else row["field"]
                ),
                row["value"],
                _percent(row["focus_share"]),
                _percent(row["baseline_share"]),
                f"+{_percent(row['delta'])}",
            )
            for row in comparison
        ],
    )
    box(
        "What the comparison found",
        "Three signals distinguish denied workflows from successful ones:\n"
        "repository taint, quarantined supply-chain posture, and missing financial\n"
        "approval.",
        color="magenta",
    )

    takeaway(
        "The local simulation shows what Honeycomb tracks for this demo: wide\n"
        "events, cross-workflow patterns, and distinguishing dimensions. It does\n"
        "not claim that Honeycomb itself stored or queried these events.",
        title="Section 3 summary",
    )
    pause("  Press Enter to continue...", context.no_pause)


def section_3(context: DemoContext) -> None:
    new_screen(
        "SECTION 3 — INVESTIGATE WORKFLOW BEHAVIOR",
        SECTION_3_COLOR,
    )
    if not context.cloud:
        _local_honeycomb_section(context)
        return
    box(
        "What Honeycomb adds",
        "Honeycomb is an AI-ready observability platform for understanding complex\n"
        "production systems. Its event-based approach gives engineers and agents a\n"
        "shared view of what is happening and supports questions they did not know\n"
        "to anticipate.\n\n"
        "Each live Runtime invocation sends an OpenTelemetry trace that connects\n"
        "the agent request, model activity, workflow checks, and tools. AWS-managed\n"
        "Gateway spans are joined to that same trace, adding the authoritative\n"
        "authorization decision when a request reaches the external tool boundary.\n\n"
        "• End-to-end traceability — follow one request through the agentic system.\n"
        "• Cross-workflow analysis — compare denied workflows with successful ones\n"
        "  and use BubbleUp to surface the fields that distinguish them.\n"
        "• Security investigation — identify the posture, taint, or approval signal\n"
        "  behind a denial and follow how it changed the workflow path.\n\n"
        "Honeycomb observes and explains these decisions; Strands and AgentCore\n"
        "Gateway remain responsible for enforcing them.",
        color="magenta",
    )

    pause(
        "  Press Enter to compare workflow outcomes in Honeycomb...",
        context.no_pause,
    )
    new_screen(
        "SECTION 3 — HONEYCOMB WORKFLOW OUTCOMES",
        SECTION_3_COLOR,
    )
    deployed_outputs = getattr(context, "outputs", {}) or {}
    dataset = str(
        deployed_outputs.get("honeycombDataset")
        or os.environ.get(
            "MODULE12_HONEYCOMB_DATASET",
            "module12-security-observability",
        )
    )
    link = honeycomb_investigation_link(
        dataset=dataset,
        base_url=os.environ.get("MODULE12_HONEYCOMB_UI_URL"),
    )
    honeycomb_instructions = (
        f"Open the Honeycomb environment and select service/dataset:\n"
        f"  {dataset}\n\n"
        "Open Query Builder, choose Paste Query, and paste the JSON shown below.\n"
        "It counts Strands authorization events and separates them by decision\n"
        "and the framework rule that produced that decision."
    )
    if link:
        honeycomb_instructions = (
            f"{honeycomb_instructions}\n\nHoneycomb environment:\n  {link}"
        )
    box("Open Honeycomb Query Builder", honeycomb_instructions, color="magenta")
    show_code(
        "Paste-ready Honeycomb Query JSON",
        compact_json(HONEYCOMB_POLICY_POPULATION_QUERY),
    )

    pause(
        "  Press Enter to investigate why workflows were denied with BubbleUp...",
        context.no_pause,
    )
    new_screen(
        "SECTION 3 — BUBBLEUP DENIED WORKFLOWS",
        SECTION_3_COLOR,
    )
    box(
        "Run BubbleUp",
        "In the Overview table, find a DENY row. Under policy.decision, click the\n"
        "three-dot menu beside DENY and choose BubbleUp outliers.\n\n"
        "On the BubbleUp tab, confirm:\n"
        "  selection — policy.decision = DENY\n"
        "  baseline  — all other events in the query\n\n"
        "Honeycomb then ranks the fields that best distinguish denied workflows\n"
        "from successful ones.",
        color="magenta",
    )
    show_values(
        "Expected distinguishing dimensions",
        [
            (
                "Supply-chain containment",
                "policy.rule = deny_quarantined_posture",
            ),
            ("Repository-content containment", "session.tainted = true"),
            (
                "Approval containment",
                "financial.approval.status = pending",
            ),
            ("Enforced outcome", "policy.decision = DENY"),
            ("Explaining control", "policy.rule"),
        ],
        color="magenta",
    )
    box(
        "How to read the result",
        "The comparison should independently surface repository taint, pending\n"
        "financial approval, and quarantined supply-chain posture as explanations\n"
        "for denied workflows. Honeycomb's High and Medium labels describe how\n"
        "strongly a field distinguishes denied workflows from successful ones;\n"
        "they are not security severity ratings.\n\n"
        "For a focused containment investigation, return to Overview. Under\n"
        "policy.rule,\n"
        "open the three-dot menu beside deny_quarantined_posture and choose\n"
        "BubbleUp outliers.",
        color="cyan",
    )

    quarantine_session = _quarantine_window_session(
        getattr(context, "outcomes", ())
    )
    if quarantine_session:
        pause(
            "  Press Enter to measure the observed quarantine window...",
            context.no_pause,
        )
        new_screen(
            "SECTION 3 — OBSERVED QUARANTINE WINDOW",
            SECTION_3_COLOR,
        )
        box(
            "What this query measures",
            "Section 2 produced two workflow observations in the same Runtime\n"
            "session: a denied request that observed quarantine and a later\n"
            "allowed request that observed healthy posture after recovery.\n\n"
            "Honeycomb Query Math subtracts those event timestamps. The result is\n"
            "the observed enforcement window in seconds—not the exact control-plane\n"
            "transition duration.",
            color="magenta",
        )
        quarantine_query = _honeycomb_quarantine_window_query(
            quarantine_session
        )
        duration_link = honeycomb_query_template_link(
            dataset=dataset,
            query=quarantine_query,
            base_url=os.environ.get("MODULE12_HONEYCOMB_UI_URL"),
        )
        if duration_link:
            if RICH:
                link_body = (
                    f"[link={duration_link}]"
                    "[bold underline]Open the pre-filled duration query in Honeycomb"
                    "[/bold underline][/link]\n\n"
                    "The query loads and runs automatically. Compact JSON remains "
                    "available below as a fallback."
                )
            else:
                link_body = (
                    "Open the pre-filled duration query in Honeycomb:\n"
                    f"{duration_link}\n\n"
                    "The query loads and runs automatically. Compact JSON remains "
                    "available below as a fallback."
                )
            box("Open the duration query", link_body, color="magenta")
        show_code(
            "Paste-ready Honeycomb duration query JSON",
            compact_json(quarantine_query),
        )
        box(
            "How to read the result",
            "observed_quarantine_seconds is the time between the first quarantined\n"
            "denial and the final healthy allowed workflow in this demo session.",
            color="cyan",
        )

    takeaway(
        "Honeycomb observes the agentic workflow without controlling infrastructure.\n"
        "It makes posture changes, framework decisions, agent activity, and workflow\n"
        "outcomes queryable across executions. Teams can compare successful and\n"
        "denied workflows, identify the signals that distinguish them, and measure\n"
        "the observed containment and recovery window. Strands and AgentCore Gateway\n"
        "enforce; Honeycomb explains how the system behaved and why.",
        title="Section 3 summary",
    )
    pause("  Press Enter to continue...", context.no_pause)


def seed_population(context: DemoContext, *, quiet: bool = False) -> list[dict[str, Any]]:
    if not quiet:
        new_screen("SEED MODULE 12 WORKFLOWS", "cyan")
    seeded: list[dict[str, Any]] = []

    def activity(message: str) -> None:
        if not quiet:
            operation_started(message, cloud=context.cloud)

    def completed(message: str) -> None:
        if not quiet:
            operation_completed(message, cloud=context.cloud)

    def invoke(
        scenario: str,
        *,
        store: InMemoryWorkflowStore | None = None,
        model_output: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        activity(f"Running seed workflow scenario {scenario}...")
        outcome = context.invoke(
            scenario,
            store=store,
            model_output=model_output,
            session_id=_session_id(),
        )
        completed(
            f"Seed workflow {scenario} completed with "
            f"{_policy(outcome).get('decision', 'unknown')}."
        )
        seeded.append(outcome)
        return outcome

    if context.cloud:
        activity("Publishing the remediated tool baseline before seeding...")
        context.publish_posture(
            action="recover_digest",
            tool_digest=REVIEWED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("The remediated tool baseline was published.")
        activity("Waiting for trusted posture to become healthy...")
        context.wait_for_posture("healthy")
        completed("Trusted posture is healthy.")
        invoke("normal")
        invoke(
            "tainted_repository",
            model_output={
                "requested_tool": "apply_infrastructure",
                "session_tainted": False,
            },
        )
        invoke("missing_financial_approval")
        activity("Publishing the supply-chain finding for the quarantine seed...")
        context.publish_posture(
            action="publish_finding",
            tool_digest=CHANGED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("The supply-chain finding was published and quarantine is active.")
        invoke("normal")
        activity("Publishing the remediated tool version after the quarantine seed...")
        context.publish_posture(
            action="recover_digest",
            tool_digest=REVIEWED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("The remediated tool version was published.")
        activity("Waiting for trusted posture to become healthy...")
        context.wait_for_posture("healthy")
        completed("Trusted posture is healthy.")
        invoke("normal")
    else:
        activity("Setting local trusted posture to the reviewed baseline...")
        context.publish_posture(
            action="recover_digest",
            tool_digest=REVIEWED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("Local trusted posture was reset.")
        activity("Confirming local trusted posture is healthy...")
        context.wait_for_posture("healthy")
        completed("Local trusted posture is healthy.")
        invoke("normal")
        invoke(
            "tainted_repository",
            model_output={
                "requested_tool": "apply_infrastructure",
                "session_tainted": False,
            },
        )
        invoke("missing_financial_approval")
        activity("Publishing the recorded finding for the quarantine seed...")
        context.publish_posture(
            action="publish_finding",
            tool_digest=CHANGED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("The recorded finding was published and quarantine is active.")
        invoke("normal")
        activity("Publishing the remediated local tool version...")
        context.publish_posture(
            action="recover_digest",
            tool_digest=REVIEWED_TOOL_DIGEST,
            reviewed_tool_digest=REVIEWED_TOOL_DIGEST,
        )
        completed("The remediated local tool version was published.")
        activity("Confirming local trusted posture is healthy...")
        context.wait_for_posture("healthy")
        completed("Local trusted posture is healthy.")
    if not quiet:
        show_table(
            "Seed results",
            ("Scenario", "Status", "Policy", "Session"),
            [
                (
                    outcome.get("scenario"),
                    outcome.get("status"),
                    _policy(outcome).get("decision"),
                    outcome.get("session_id"),
                )
                for outcome in seeded
            ],
        )
        print(f"\n  Seeded {len(seeded)} workflow sessions.")
    return seeded


def show_wrap_up(context: DemoContext) -> None:
    new_screen("MODULE 12 COMPLETE", "green")
    print(
        "\n  What we proved:\n\n"
        "   • Section 1 — Enforce two authority boundaries\n"
        "     A model proposed infrastructure work but could not rewrite trusted\n"
        "     workflow facts. Strands stopped unsafe calls inside the agent lifecycle;\n"
        "     AgentCore Gateway independently protected the external tool boundary.\n\n"
        "   • Section 2 — Snyk: turn supply-chain risk into containment\n"
        "     A Snyk finding changed trusted tool posture to quarantine. Read-only\n"
        "     work continued and deployment remained denied until the engineering team\n"
        "     updated the vulnerable dependency pin and published the remediated tool.\n\n"
        "   • Section 3 — Honeycomb: investigate behavior across workflows\n"
        "     Honeycomb showed what distinguished denied workflows from successful\n"
        "     ones and measured the observed quarantine and recovery window across\n"
        "     workflow events.\n"
    )
    pause("  Demo complete. Press Enter to finish...", context.no_pause)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Module 12: Security and Observability for agent workflows"
    )
    parser.add_argument(
        "--section",
        type=int,
        choices=(1, 2, 3),
        help="run one independently runnable demo section",
    )
    parser.add_argument(
        "--session",
        help="session identifier; short values are extended for AgentCore compatibility",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="run without waiting for Enter between presenter beats",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="seed a comparison dataset; exits unless --section is also set",
    )
    parser.add_argument(
        "--seed-repetitions",
        type=int,
        default=1,
        help=(
            "repeat the five-scenario seed sequence to create a larger "
            "comparison dataset (default: 1)"
        ),
    )
    parser.add_argument(
        "--stack",
        help="Pulumi stack to use for the deployed AWS demo, for example module12-demo",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        help="read deployed Pulumi outputs from JSON instead of invoking Pulumi",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("AWS_PROFILE"),
        help="AWS profile for deployed mode",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("AWS_REGION", "us-east-1"),
        help="AWS region for deployed mode (default: us-east-1)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="show a traceback instead of presenter-friendly error handling",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outputs: dict[str, Any] = {}
        if args.outputs:
            outputs = _load_output_file(args.outputs)
        elif args.stack:
            new_screen("MODULE 12 — CONNECTING TO AWS", "cyan")
            operation_started(
                f"Loading deployed outputs for Pulumi stack {args.stack}...",
                cloud=True,
                setup=True,
            )
            outputs = _load_stack_outputs(args.stack, profile=args.profile)
            operation_completed(
                "Deployed stack outputs loaded.",
                cloud=True,
                setup=True,
            )
        stack = args.stack or (str(outputs.get("stack")) if outputs.get("stack") else None)
        context = DemoContext(
            no_pause=args.no_pause,
            session_id=_session_id(args.session),
            region=str(outputs.get("region") or args.region),
            stack=stack,
            profile=args.profile,
            outputs=outputs,
        )

        if args.seed:
            if args.seed_repetitions < 1 or args.seed_repetitions > 20:
                parser.error("--seed-repetitions must be between 1 and 20")
            for repetition in range(args.seed_repetitions):
                if repetition:
                    operation_started(
                        "Running another five-workflow investigation seed sequence "
                        f"({repetition + 1}/{args.seed_repetitions})...",
                        cloud=context.cloud,
                        setup=True,
                    )
                seeded = seed_population(context, quiet=repetition > 0)
                if repetition:
                    operation_completed(
                        f"Seed sequence completed with {len(seeded)} workflows.",
                        cloud=context.cloud,
                        setup=True,
                    )
            if args.section is None:
                return 0

        if args.section is None:
            show_intro(context)
            for section in (section_1, section_2, section_3):
                section(context)
            show_wrap_up(context)
        else:
            (section_1, section_2, section_3)[args.section - 1](context)
        return 0
    except KeyboardInterrupt:
        print("\nDemo interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        if args.debug:
            raise
        print(f"\nModule 12 demo stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
