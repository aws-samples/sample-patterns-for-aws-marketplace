#!/usr/bin/env python3
"""
demos/module8_demo.py
=====================
Live workshop demo for Module 8: Agent Identity & Access Management.

Demonstrates user delegation, deterministic agent authorization,
cross-system correlation, and credential isolation with Auth0 and
CyberArk Agent Guard.

USAGE
-----
  AGENT_MOCK_MODE=true python demos/module8_demo.py
  AGENT_MOCK_MODE=true python demos/module8_demo.py --section 3

SECTIONS
--------
  1  The Identity Problem             — Why service accounts fail for agents
  2  Delegation & Scope Narrowing     — OAuth, permission boundaries, A2A auth
  3  Tracing Delegation Chain         — Auth0, approval, STS tags, CloudTrail
  4  Credential Isolation             — Agent Guard at the tool boundary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from module8.identity.context import UserAuthorizationContext
from module8.config.models import Auth0Config

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

os.environ.setdefault("AGENT_MOCK_MODE", "true")

AUTH0_DISPLAY_DOMAIN = "tenant.example.auth0.com"
AUTH0_DISPLAY_ISSUER = f"https://{AUTH0_DISPLAY_DOMAIN}/"


@dataclass(frozen=True)
class _AuthenticatedUserSession:
    authorization_context: UserAuthorizationContext
    access_token: str
    config: Auth0Config
    claims: dict
    scopes: set[str]
    discovery: dict | None
    jwks: dict | None

# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    _c = Console()
    _RICH = True

    def header(text: str, color: str = "cyan") -> None:
        _c.rule(f"[bold {color}]{text}[/bold {color}]", style=color)

    def concept(text: str) -> None:
        normalized = " ".join(text.split())
        layout = Table.grid(padding=(0, 1), expand=True)
        layout.add_column(style="bold yellow", no_wrap=True)
        layout.add_column(style="yellow", ratio=1, overflow="fold")
        layout.add_row("💡 Module 8 Concept:", normalized)
        _c.print()
        _c.print(layout)

    def box(title: str, body: str) -> None:
        _c.print(Panel(f"[dim]{body}[/dim]", title=f"[bold]{title}[/bold]", border_style="cyan"))

    def result_box(title: str, data: dict) -> None:
        formatted = json.dumps(data, indent=2, default=str)
        _c.print(Panel(Syntax(formatted, "json", theme="monokai", line_numbers=False),
                       title=f"[bold green]{title}[/bold green]", border_style="green"))

    def step_indicator(step: str, status: str = "completed", detail: str = "") -> None:
        icons = {"completed": "✓", "running": "⟳", "blocked": "✗", "info": "ℹ"}
        colors = {"completed": "green", "running": "yellow", "blocked": "red", "info": "blue"}
        icon = icons.get(status, "•")
        color = colors.get(status, "dim")
        msg = f"  [{color}]{icon}[/{color}] [bold]{step}[/bold]"
        if detail:
            msg += f" [dim]— {detail}[/dim]"
        _c.print(msg)

    def boundary_indicator(
        boundary: str,
        step: str,
        status: str = "completed",
        detail: str = "",
    ) -> None:
        boundaries = {
            "agent": ("AGENT", "cyan"),
            "agent_guard": ("AGENT GUARD", "magenta"),
            "protected_tool": ("PROTECTED TOOL", "green"),
        }
        icons = {"completed": "✓", "running": "⟳", "blocked": "✗", "info": "ℹ"}
        status_colors = {
            "completed": "green",
            "running": "yellow",
            "blocked": "red",
            "info": "blue",
        }
        label, boundary_color = boundaries[boundary]
        icon = icons.get(status, "•")
        status_color = status_colors.get(status, "dim")
        msg = (
            f"  [{status_color}]{icon}[/{status_color}] "
            f"[bold {boundary_color}]{label:<14}[/bold {boundary_color}] "
            f"[{boundary_color}]{step}[/{boundary_color}]"
        )
        if detail:
            msg += f" [dim]· {detail}[/dim]"
        _c.print(msg)

    def boundary_box(boundary: str, title: str, body: str) -> None:
        colors = {
            "agent": "cyan",
            "agent_guard": "magenta",
            "protected_tool": "green",
        }
        color = colors[boundary]
        _c.print(
            Panel(
                f"[dim]{body}[/dim]",
                title=f"[bold {color}]{title}[/bold {color}]",
                border_style=color,
            )
        )

except ImportError:
    _RICH = False

    def header(text: str, color: str = "cyan") -> None:
        print(f"\n{'═' * 62}\n  {text}\n{'═' * 62}")

    def concept(text: str) -> None:
        print(f"\n💡 Module 8 Concept: {' '.join(text.split())}")

    def box(title: str, body: str) -> None:
        print(f"\n┌─ {title} ─{'─' * max(0, 56 - len(title))}")
        for line in body.split("\n"):
            print(f"│ {line}")
        print(f"└{'─' * 60}")

    def result_box(title: str, data: dict) -> None:
        print(f"\n  [{title}]")
        print(json.dumps(data, indent=2, default=str))

    def step_indicator(step: str, status: str = "completed", detail: str = "") -> None:
        icons = {"completed": "✓", "running": "⟳", "blocked": "✗", "info": "ℹ"}
        icon = icons.get(status, "•")
        msg = f"  {icon} {step}"
        if detail:
            msg += f" — {detail}"
        print(msg)

    def boundary_indicator(
        boundary: str,
        step: str,
        status: str = "completed",
        detail: str = "",
    ) -> None:
        boundaries = {
            "agent": "AGENT",
            "agent_guard": "AGENT GUARD",
            "protected_tool": "PROTECTED TOOL",
        }
        icons = {"completed": "✓", "running": "⟳", "blocked": "✗", "info": "ℹ"}
        icon = icons.get(status, "•")
        msg = f"  {icon} {boundaries[boundary]:<14} {step}"
        if detail:
            msg += f" · {detail}"
        print(msg)

    def boundary_box(boundary: str, title: str, body: str) -> None:
        box(f"{boundary.replace('_', ' ').upper()}: {title}", body)


def pause(msg: str = "  ↵  Press Enter to continue...") -> None:
    try:
        input(msg)
    except KeyboardInterrupt:
        sys.exit(0)


def clear_screen() -> None:
    print("\033[H\033[2J", end="")


def is_mock_mode() -> bool:
    return os.getenv("AGENT_MOCK_MODE", "true").lower() not in {"false", "0", "no"}


# ---------------------------------------------------------------------------
# Section 1 — The Identity Problem
# ---------------------------------------------------------------------------

def section_1_identity_problem() -> None:
    clear_screen()
    header("SECTION 1 — The Identity Problem", "cyan")

    box(
        "The DevOps Companion Pipeline (Modules 2-6)",
        "1.  analyze_repository      — LLM examines repo structure\n"
        "2.  map_dependencies        — LLM maps services to AWS resources\n"
        "3.  generate_cdk            — LLM produces CDK infrastructure code\n"
        "4.  verify (parallel)       — Security scan + compliance check\n"
        "5.  approve_deployment      — Human reviews CDK + verification results\n"
        "6.  deploy                  — Deploy to EKS/ECS\n"
        "7.  smoke_tests             — Validate deployment\n"
        "8.  setup_observability     — Configure monitoring\n\n"
        "Question: At each step — whose identity is acting?\n"
        "          What permissions does it have? For how long?",
    )
    pause()

    clear_screen()
    box(
        "The Four Identity Principals",
        "              ┌────────────────────┐\n"
        "              │ End User           │\n"
        "              │ human principal    │\n"
        "              └─────────┬──────────┘\n"
        "                        │ delegates scoped JWT\n"
        "                        ▼\n"
        "              ┌────────────────────┐\n"
        "              │ Orchestrator Agent │\n"
        "              │ workflow identity  │\n"
        "              └─────────┬──────────┘\n"
        "                        │ narrows scope\n"
        "                        ▼\n"
        "              ┌────────────────────┐\n"
        "              │ Specialist Agents  │\n"
        "              │ analyze / iac /    │\n"
        "              │ deploy             │\n"
        "              └─────────┬──────────┘\n"
        "                        │ invokes authorized tool\n"
        "                        │ with operation parameters\n"
        "                        ▼\n"
        "              ┌────────────────────┐\n"
        "              │ Tool Boundary      │\n"
        "              │ GitHub MCP / AWS   │\n"
        "              │ checks policy and  │\n"
        "              │ gets credential    │\n"
        "              └────────────────────┘\n\n"
        "Each level acts under its OWN identity with DELEGATED authority.\n"
        "The tool boundary obtains the target credential; the agent never sees it.",
    )

    concept(
        "Agents are a third generation of identity — neither human users nor service accounts.\n"
        "  They act on behalf of users with delegated authority, their required permissions vary\n"
        "  dynamically per task, and their workflows can outlast credential lifetimes."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 2 — Delegation & Scope Narrowing
# ---------------------------------------------------------------------------

def _authenticate_user_for_workflow() -> _AuthenticatedUserSession | None:
    from module8.config.models import Auth0Config
    from module8.identity.auth0_client import (
        Auth0Error,
        decode_access_token,
        fetch_jwks,
        fetch_openid_config,
        poll_device_token,
        request_device_code,
        token_fingerprint,
        token_scopes,
        validate_user_token_claims,
    )

    config = Auth0Config()
    try:
        config.validate_for_live()
        step_indicator(
            "Generating Auth0 device sign-in URL",
            "running",
            "requesting a one-time device authorization response",
        )
        device = request_device_code(config)
    except (ValueError, Auth0Error) as exc:
        result_box("Auth0 Live Configuration Error", {"error": str(exc)})
        return None

    step_indicator(
        "Auth0 device sign-in URL generated",
        "completed",
        f"tenant: {AUTH0_DISPLAY_DOMAIN}",
    )
    if not config.mock_mode:
        box(
            "Complete Auth0 Login",
            "Open this one-time Auth0 Device Authorization URL in a browser:\n\n"
            f"{device.verification_uri_complete}\n\n"
            f"User code: {device.user_code}\n"
            "The demo will continue after Auth0 returns the user token.",
        )

    try:
        user_token = poll_device_token(config, device.device_code, device.interval)
        discovery = None
        jwks = None
        if not config.mock_mode:
            discovery = fetch_openid_config(config)
            jwks = fetch_jwks(discovery["jwks_uri"])
        user_claims = decode_access_token(
            user_token,
            config,
            discovery=discovery,
            jwks=jwks,
        )
        validate_user_token_claims(user_claims, config)
        user_scopes = token_scopes(user_claims)
    except Auth0Error as exc:
        result_box("Auth0 User Delegation Failed", {"error": str(exc)})
        return None

    fingerprint = token_fingerprint(user_token)
    authorization_context = UserAuthorizationContext.from_claims(
        user_claims,
        user_scopes,
        fingerprint,
    )
    box(
        "User Delegation Token",
        "This token is created by the Auth0 Device Authorization Flow.\n\n"
        "A real user signed in and approved the requested scopes. The token answers:\n"
        "\"What did this user delegate to the demo application for this run?\"\n\n"
        "The scope claim can contain fewer entries than the user's full Auth0\n"
        "permissions because this Native Application requested only the scopes\n"
        "listed in AUTH0_REQUIRED_SCOPES.\n\n"
        "The token is authorization context, not a downstream credential. It\n"
        "cannot authenticate to target tools or integrations. Agents keep their\n"
        "own IAM and A2A identities while target tools obtain separate, narrowly\n"
        "scoped credentials after authorization succeeds.",
    )
    result_box("Decoded JWT — User Delegation Token", {
        "auth0_domain": AUTH0_DISPLAY_DOMAIN,
        "issuer": AUTH0_DISPLAY_ISSUER,
        "subject": user_claims.get("sub"),
        "email": user_claims.get("email"),
        "audience": user_claims.get("aud"),
        "delegated_scopes_from_scope_claim": sorted(user_scopes),
        "user_permissions_claim": sorted(user_claims.get("permissions", [])) or "not present",
        "grant_type": user_claims.get("gty", "device-code"),
        "token_fingerprint": fingerprint,
    })
    pause()

    return _AuthenticatedUserSession(
        authorization_context=authorization_context,
        access_token=user_token,
        config=config,
        claims=user_claims,
        scopes=user_scopes,
        discovery=discovery,
        jwks=jwks,
    )


def section_2_delegation() -> UserAuthorizationContext | None:
    clear_screen()
    header("SECTION 2 — Delegation & Scope Narrowing", "green")

    box(
        "Auth0 as an Authorization Server",
        "This demo uses Auth0 as its OAuth 2.0 authorization server. Auth0\n"
        "authenticates the user through the tenant's configured identity\n"
        "connection, then issues an access token containing the scopes the user\n"
        "authorizes for this workflow.\n\n"
        "In a federated deployment, Auth0 can broker sign-in to an upstream\n"
        "enterprise identity provider while remaining the token issuer the\n"
        "workflow validates.",
    )
    pause()

    clear_screen()
    box(
        "Where Scope Narrowing Is Enforced",
        "1. This demo asks Auth0 for the scopes in AUTH0_REQUIRED_SCOPES.\n"
        "   The issued token records what the user delegated for this run.\n\n"
        "2. Auth0 checks whether the Native Application can request those scopes\n"
        "   for the API audience. If it cannot, the token request fails.\n\n"
        "3. The layered enforcement points shown above validate the token and\n"
        "   required scope before a protected tool can run. The agent or LLM does\n"
        "   not make that authorization decision.\n\n"
        "4. The token is not exchanged or rewritten at each hop. It carries the\n"
        "   user's delegated authority, while the orchestrator and specialist\n"
        "   agents identify themselves with their own IAM and A2A principals.",
    )
    box(
        "How the Workflow Enforces Authorization",
        "The Auth0 token is authorization context, not a downstream credential.\n\n"
        "Before an agent or tool runs:\n"
        "  validated token -> required scope + agent policy -> ALLOW or DENY\n\n"
        "Defense in depth checks the request at two boundaries:\n"
        "  Application or SDK: code blocks unauthorized dispatches and tool calls.\n"
        "  Managed service: AgentCore Gateway + Policy checks again before forwarding.\n\n"
        "Both checks are deterministic; the LLM never makes the decision.\n"
        "These controls are described, not configured by this demo.",
    )
    pause()
    clear_screen()

    from module8.identity.auth0_client import Auth0Error
    from module8.identity.delegation import AGENT_POLICIES, authorize_agent_call

    session = _authenticate_user_for_workflow()
    if session is None:
        return None

    user_token = session.access_token
    config = session.config
    user_scopes = session.scopes
    discovery = session.discovery
    jwks = session.jwks

    clear_screen()
    workflow_calls = (
        (AGENT_POLICIES[0], "coordinate_analysis", "devops:analyze"),
        (AGENT_POLICIES[1], "analyze_repository", "devops:analyze"),
        (AGENT_POLICIES[2], "generate_iac", "devops:iac"),
        (AGENT_POLICIES[3], "deploy_staging", "devops:deploy:staging"),
    )
    decisions = []
    try:
        for policy, operation, required_scope in workflow_calls:
            decisions.append(authorize_agent_call(
                user_token,
                config,
                policy,
                operation,
                required_scope,
                discovery=discovery,
                jwks=jwks,
            ))
    except Auth0Error as exc:
        result_box("Agent Authorization Failed", {"error": str(exc)})
        return

    header("Independent Authorization Checks — Same User Token", "green")
    if _RICH:
        table = Table(expand=True, show_lines=True)
        table.add_column("Agent", style="cyan", ratio=2)
        table.add_column("Authorized workflow scopes", style="green", ratio=3)
        table.add_column("Target access after allow", ratio=4)
        for decision in decisions:
            table.add_row(
                decision.agent.removeprefix("DevOps Companion "),
                "\n".join(sorted(decision.effective_scopes)),
                decision.downstream_access,
            )
        _c.print(table)
    else:
        for decision in decisions:
            box(
                decision.agent.removeprefix("DevOps Companion "),
                f"Authorized workflow scopes:\n"
                f"  {', '.join(sorted(decision.effective_scopes))}\n\n"
                f"Target access after allow:\n"
                f"  {decision.downstream_access}",
            )
    pause()

    box(
        "Scope Narrowing Is a Decision, Not a New Token",
        f"User-delegated scopes:\n  {', '.join(sorted(user_scopes))}\n\n"
        "The access token remains unchanged. This is another layer of enforcement:\n"
        "the authorization layer evaluates the intersection of the token, agent\n"
        "policy, and target access policy.\n\n"
        "Preconfigured permission ceilings stop an agent from expanding its\n"
        "authority when it operates tools. No agent can add a missing user scope.\n\n"
        "Target credentials, service policies, and workload permissions place\n"
        "hard limits on the operations available after authorization succeeds.",
    )

    concept(
        "Auth0 records what the user delegated. Agent policy decides whether the\n"
        "  requested operation fits that delegation. IAM roles and authenticated\n"
        "  A2A calls identify the workload. IAM, agent, and target-system policies\n"
        "  constrain what it can do."
    )
    pause()
    return session.authorization_context


# ---------------------------------------------------------------------------
# Section 4 — Credential Isolation at the Tool Boundary
# ---------------------------------------------------------------------------

def _render_agent_guard_boundary_evidence(evidence: dict) -> None:
    process = evidence["agent_process"]
    operation = evidence["operation"]
    operation_audit = evidence["operation_audit"]

    before_present = bool(process["credential_present_before"])
    boundary_indicator(
        "agent",
        "Requests list_private_repositories",
        "blocked" if before_present else "completed",
        "GITHUB_TOKEN absent" if not before_present else "GITHUB_TOKEN already present",
    )
    boundary_indicator(
        "agent_guard",
        "Secret reference",
        "info",
        evidence["secret_source"],
    )
    boundary_indicator(
        "agent_guard",
        "Credential injection",
        "completed"
        if operation["credential_present_in_protected_process"]
        else "blocked",
        "secret injected when the protected process started; value not returned",
    )

    policy_allowed = (
        operation["decision"] == "allowed"
        and not operation["blocked"]
    )
    boundary_indicator(
        "protected_tool",
        "Policy decision",
        "completed" if policy_allowed else "blocked",
        f"ALLOW {operation['action']}"
        if policy_allowed
        else f"DENY {operation['action']}",
    )
    credential_available = (
        policy_allowed
        and operation["credential_present_in_protected_process"]
        and operation["executed"]
    )
    boundary_indicator(
        "protected_tool",
        "Authorized credential use",
        "completed" if credential_available else "blocked",
        "injected credential available for the allowed operation"
        if credential_available
        else "operation not executed with a protected credential",
    )
    repositories = operation["result"]["repositories"]
    boundary_box(
        "protected_tool",
        "Protected MCP Operation Result (Representative)",
        f"operation: {operation['action']}\n"
        f"repositories: {', '.join(repositories)}\n"
        "credential returned to agent: no",
    )
    operation_audited = (
        operation_audit["request_recorded"] and operation_audit["response_recorded"]
    )
    boundary_indicator(
        "agent_guard",
        "Operation audit",
        "completed" if operation_audited else "blocked",
        "request and response recorded"
        if operation_audited
        else "matching request and response not found",
    )
    after_present = bool(process["credential_present_after"])
    boundary_indicator(
        "agent",
        "Receives operation result",
        "blocked" if after_present else "completed",
        "repository result returned; GITHUB_TOKEN absent"
        if not after_present
        else "GITHUB_TOKEN remained present",
    )


def show_module_summary() -> None:
    clear_screen()
    header("MODULE 8 COMPLETE", "green")
    print("""
  What we covered:

     • User delegation
       Auth0 records the user identity and delegated scopes. Deterministic
       policy gates decide whether each operation fits that authority.

     • Workload identity and least privilege
       Each agent acts through its own principal. Agent policy and target-system
       permissions prevent the workload from expanding the user's authority.

     • Traceability
       workflow_execution_id connects delegation, authorization decisions,
       approval, repository evidence, and AWS activity without storing secrets.

     • Credentials at the tool boundary
       CyberArk Agent Guard injects the secret only into the protected MCP
       process. The agent receives the operation result, never the credential.

  Together, these controls show who delegated the work, which workload acted,
  what policy allowed it, and which target principal performed the action.
""")
    pause()


def section_4_credential_isolation() -> None:
    clear_screen()
    header("SECTION 4 — Credential Isolation at the Tool Boundary", "magenta")

    box(
        "⚠️  The Anti-Pattern: Static Credentials",
        "$ env | grep GITHUB\n"
        "GITHUB_TOKEN=ghp_example_long_lived_personal_access_token\n\n"
        "Created:   247 days ago\n"
        "Rotated:   Never\n"
        "Policy:    Read and write across the organization\n"
        "Expires:   Never\n"
        "Location:  Analysis Agent environment variable\n\n"
        "If this credential leaks — through a log, a prompt injection, a repo\n"
        "commit — the attacker inherits broad GitHub access with no expiry.",
    )
    pause()

    box(
        "CyberArk Agent Guard at the Tool Boundary",
        "The agent requests an MCP operation, not a credential. CyberArk Agent\n"
        "Guard resolves its configured secret reference and launches the\n"
        "protected MCP process with the secret injected only there.\n\n"
        "The protected MCP server applies an application-side, deterministic\n"
        "policy before executing the operation. This demo uses a Python\n"
        "allowlist: list_private_repositories is allowed; unlisted actions are\n"
        "denied. Agent Guard injects and audits. The protected tool makes the\n"
        "authorization decision.\n\n"
        "The next screen proves the boundary. In live mode, the Agent Guard\n"
        "proxy, secret injection, and audit records are real. The repository\n"
        "operation result is representative and does not call GitHub. This\n"
        "demonstrates isolation and audit, not token rotation or expiration.",
    )
    pause("  ↵  Press Enter to run the credential-boundary demonstration...")

    clear_screen()
    mock_mode = is_mock_mode()
    if mock_mode:
        from module8.mock.cyberark_mock import generate_boundary_evidence

        header("CyberArk Agent Guard Credential Injection: Mock Evidence", "magenta")
        evidence = generate_boundary_evidence()
    else:
        from module8.agent_guard_live import (
            AgentGuardProbeError,
            load_config,
            probe_mcp,
        )

        header("Live CyberArk Agent Guard Credential Injection", "magenta")
        config = load_config()
        boundary_indicator(
            "agent_guard",
            "Boundary startup",
            "running",
            "starting the MCP proxy and protected tool process",
        )
        try:
            evidence = probe_mcp(config).to_dict()
        except AgentGuardProbeError as exc:
            boundary_indicator("agent_guard", "Boundary startup", "blocked", str(exc))
            result_box(
                "Credential Boundary Failure",
                {
                    "status": "failed",
                    "error": str(exc),
                    "captured_process_output": (
                        exc.captured_stderr or "No process output captured."
                    ),
                },
            )
            pause()
            show_module_summary()
            return
        except Exception as exc:
            boundary_indicator("agent_guard", "Boundary startup", "blocked", str(exc))
            result_box(
                "Credential Boundary Failure",
                {
                    "status": "failed",
                    "error": str(exc),
                    "captured_process_output": "No process output captured.",
                },
            )
            pause()
            show_module_summary()
            return

    _render_agent_guard_boundary_evidence(evidence)

    concept(
        "CyberArk Agent Guard injects the configured secret only into the\n"
        "  protected MCP process and audits the exchange. The protected tool\n"
        "  policy authorizes the operation. The agent receives only the result."
    )
    pause()
    show_module_summary()


# ---------------------------------------------------------------------------
# Section 3 — Tracing Delegation Chain
# ---------------------------------------------------------------------------

def section_3_trace_delegation(
    authorization_context: UserAuthorizationContext | None = None,
) -> None:
    clear_screen()
    header("SECTION 3 — Tracing Delegation Chain", "yellow")

    box(
        "A deployment went out wrong. Who allowed the agent to continue?",
        "A bad staging deployment went out.\n\n"
        "CloudTrail can show that the deploy agent made the AWS call. The\n"
        "important question is: who approved that agent to continue after the\n"
        "security and compliance review?",
    )
    pause()

    from module8.audit.trail import generate_identity_trace

    if authorization_context is None:
        box(
            "Load the User Delegation Context",
            "Section 3 needs the validated Auth0 identity and delegated scopes.\n"
            "A standalone run signs the user in now. The raw access token stays\n"
            "inside the authentication step and is not stored in the audit record.",
        )
        session = _authenticate_user_for_workflow()
        if session is None:
            return
        authorization_context = session.authorization_context

    try:
        trace = generate_identity_trace("wf-7a3b9c", authorization_context)
    except ValueError as exc:
        result_box(
            "Workflow Authorization Denied",
            {
                "workflow_execution_id": "wf-7a3b9c",
                "decision": "DENY",
                "reason": str(exc),
            },
        )
        return
    cloudtrail_event = trace["representative_cloudtrail_event"]

    clear_screen()
    box(
        "Representative CloudTrail Deployment Event",
        f"event_id: {cloudtrail_event['eventID']}\n"
        f"event_name: {cloudtrail_event['eventName']}\n"
        "calling_role: "
        f"{cloudtrail_event['userIdentity']['sessionContext']['sessionIssuer']['arn']}\n"
        f"resource: {cloudtrail_event['resources'][0]['ARN']}\n"
        "source_identity: "
        f"{cloudtrail_event['userIdentity']['sessionContext']['sourceIdentity']}",
    )

    box(
        "One Correlation Key Connects the Evidence",
        "workflow_execution_id is the join key across the DevOps Companion record,\n"
        "GitHub evidence, STS role session, and CloudTrail event. The deployment\n"
        "role uses it as STS SourceIdentity, which CloudTrail carries into later\n"
        "AWS API events made with that role session.\n\n"
        "approval_id, user_identity_hash, external event IDs, and principals are\n"
        "evidence attributes. They explain what happened, but they are not\n"
        "alternate workflow correlation keys.",
    )
    pause()

    clear_screen()
    if _RICH:
        table = Table(
            title="Reverse Investigation From AWS Action to User Delegation",
            expand=True,
            show_lines=True,
        )
        table.add_column("Trace point", style="cyan", no_wrap=True)
        table.add_column("What it tells us", style="green", overflow="fold")
        for entry in trace["reverse_investigation"]:
            table.add_row(
                entry["trace_point"],
                f"{entry['answer']}\n[dim]{entry['evidence']}[/dim]",
            )
        _c.print(table)
    else:
        print("\n  Reverse Investigation From AWS Action to User Delegation")
        for entry in trace["reverse_investigation"]:
            print(f"  {entry['trace_point']:<28} | {entry['answer']}")
            print(f"  {'':<28} | {entry['evidence']}")

    pause()

    concept(
        "workflow_execution_id connects the evidence without making CloudTrail\n"
        "  responsible for the whole story. The application record shows who\n"
        "  delegated and approved work, GitHub shows repository operations, and\n"
        "  CloudTrail shows what the assumed deployment role did in AWS."
    )
    pause()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

SECTIONS = {
    1: ("The Identity Problem", section_1_identity_problem),
    2: ("Delegation & Scope Narrowing", section_2_delegation),
    3: ("Tracing Delegation Chain", section_3_trace_delegation),
    4: ("Credential Isolation", section_4_credential_isolation),
}


def show_module_intro() -> None:
    clear_screen()
    header("MODULE 8: AGENT IDENTITY & ACCESS MANAGEMENT", "cyan")

    if is_mock_mode():
        print("  Mock mode ON  (external identity and credential calls are simulated)\n")
    else:
        print("  Live mode ON  (using configured Auth0 and CyberArk Agent Guard services)\n")

    print("""  The DevOps Companion can analyze repositories, generate infrastructure
  code, and deploy workloads. Once agents act for a user, every step needs
  clear identity, authorization, credential, and audit boundaries.

  This module follows one user-initiated workflow through delegated authority,
  workload identity, cross-system evidence, and credentials isolated at the
  protected tool boundary.

  Auth0 supplies user authorization context. Agent and target-system policies
  constrain each action. CyberArk Agent Guard injects a vaulted secret only
  into the protected MCP process.

  In live mode, Auth0 sign-in and Agent Guard credential injection are live.
  GitHub, approval, STS, and CloudTrail records remain representative.

  Sections:
    1. The Identity Problem
    2. Delegation & Scope Narrowing
    3. Tracing Delegation Chain
    4. Credential Isolation at the Tool Boundary
""")
    pause("  ↵  Press Enter to begin...")


def run_all() -> None:
    authorization_context = None
    for num, (title, func) in SECTIONS.items():
        if num == 2:
            authorization_context = func()
            if authorization_context is None:
                return
        elif num == 3:
            func(authorization_context)
        else:
            func()


def main() -> None:
    parser = argparse.ArgumentParser(description="Module 8: Agent Identity & Access Management Demo")
    parser.add_argument("--section", type=str, default="all",
                        help="Section to run (1-4 or 'all')")
    args = parser.parse_args()

    show_module_intro()

    if args.section == "all":
        run_all()
    else:
        num = int(args.section)
        if num not in SECTIONS:
            print(f"Invalid section: {num}. Choose 1-4 or 'all'.")
            sys.exit(1)
        SECTIONS[num][1]()

    if _RICH:
        _c.print("\n[bold green]✓ Demo complete.[/bold green]\n")
    else:
        print("\n✓ Demo complete.\n")


if __name__ == "__main__":
    main()
