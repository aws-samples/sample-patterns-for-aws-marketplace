"""Cedar policy rendered for the Module 12 AgentCore Gateway tool target."""
from __future__ import annotations

import json
from collections.abc import Sequence


TOOL_TARGET_NAME = "companion-tools"
MCP_PROTOCOL_VERSION = "2026-07-28"
READ_ONLY_TOOLS = (
    "read_repository",
    "validate_iac",
    "generate_iac",
    "security_review",
    "get_approval_state",
    "smoke_test",
)
MUTATION_TOOLS = (
    "apply_infrastructure",
    "rollback_infrastructure",
)


def gateway_tool_action(tool: str, *, target_name: str = TOOL_TARGET_NAME) -> str:
    """Return the AgentCore action name generated for one Gateway tool."""

    return f"{target_name}___{tool}"


def _entity(kind: str, identifier: str) -> str:
    return f"{kind}::{json.dumps(identifier)}"


def _principal_condition(principal_ids: Sequence[str]) -> list[str]:
    identifiers = [identifier for identifier in principal_ids if identifier]
    if not identifiers:
        return []
    comparisons = [
        f"principal.id == {json.dumps(identifier)}" for identifier in identifiers
    ]
    expression = comparisons[0] if len(comparisons) == 1 else (
        "(" + " || ".join(comparisons) + ")"
    )
    return [f"  {expression} &&"]


def build_cedar_statements(
    gateway_arn: str,
    *,
    target_name: str = TOOL_TARGET_NAME,
    principal_ids: Sequence[str] = (),
) -> dict[str, str]:
    """Build one AgentCore policy statement for each concrete tool action."""

    resource = _entity("AgentCore::Gateway", gateway_arn)
    principal_condition = _principal_condition(principal_ids)
    statements = {
        tool: "\n".join(
            [
                "permit(",
                "  principal is AgentCore::IamEntity,",
                "  action == "
                + _entity(
                    "AgentCore::Action",
                    gateway_tool_action(tool, target_name=target_name),
                )
                + ",",
                f"  resource == {resource}",
                ")",
                "when {",
                *principal_condition,
                "  context has input &&",
                "  context.input has mutation &&",
                "  context.input.mutation == false",
                "};",
            ]
        )
        for tool in READ_ONLY_TOOLS
    }
    mutation_condition = "\n".join(
        [
            "when {",
            *principal_condition,
            """  context has input &&
  context.input has session_tainted &&
  context.input.session_tainted == false &&
  context.input has companion_posture &&
  context.input.companion_posture != "quarantine" &&
  context.input has snyk_posture &&
  context.input.snyk_posture != "quarantine" &&
  context.input has security_review &&
  context.input.security_review == "approved" &&
  context.input has financial_approval &&
  context.input.financial_approval == "approved" &&
  context.input has artifact_digest &&
  context.input.artifact_digest != "" &&
  context.input has reviewed_artifact_digest &&
  context.input.reviewed_artifact_digest != "" &&
  context.input.artifact_digest == context.input.reviewed_artifact_digest &&
  context.input has environment &&
  context.input.environment != "production"
};""",
        ]
    )
    for tool in MUTATION_TOOLS:
        statements[tool] = "\n".join(
            [
                "permit(",
                "  principal is AgentCore::IamEntity,",
                "  action == "
                + _entity(
                    "AgentCore::Action",
                    gateway_tool_action(tool, target_name=target_name),
                )
                + ",",
                f"  resource == {resource}",
                ")",
                mutation_condition,
            ]
        )
    return statements


def build_cedar_policy(
    gateway_arn: str,
    *,
    target_name: str = TOOL_TARGET_NAME,
    principal_ids: Sequence[str] = (),
) -> str:
    """Render all fail-closed tool policies for display and local evaluation."""

    return "\n\n".join(
        build_cedar_statements(
            gateway_arn,
            target_name=target_name,
            principal_ids=principal_ids,
        ).values()
    )
