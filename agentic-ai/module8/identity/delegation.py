from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module8.config.models import Auth0Config
from module8.identity.auth0_client import (
    Auth0Error,
    decode_access_token,
    token_fingerprint,
    token_scopes,
    validate_user_token_claims,
)


@dataclass(frozen=True)
class AgentAuthorizationPolicy:
    name: str
    a2a_principal: str
    iam_role_arn: str
    allowed_operations: frozenset[str]
    required_scopes: frozenset[str]
    permission_ceiling_scopes: frozenset[str]
    downstream_access: str


@dataclass(frozen=True)
class AgentAuthorizationDecision:
    agent: str
    a2a_principal: str
    iam_role_arn: str
    downstream_access: str
    operation: str
    required_scope: str
    subject: str
    delegated_scopes: frozenset[str]
    effective_scopes: frozenset[str]
    token_fingerprint: str


AGENT_POLICIES = (
    AgentAuthorizationPolicy(
        "DevOps Companion Orchestrator",
        "a2a://devops-companion/orchestrator",
        "arn:aws:iam::123456789012:role/DevOpsCompanion-Orchestrator",
        frozenset({"coordinate_analysis", "coordinate_iac", "coordinate_deploy"}),
        frozenset({"devops:analyze", "devops:iac", "devops:deploy:staging"}),
        frozenset({"devops:analyze", "devops:iac", "devops:deploy:staging"}),
        "No downstream credential; coordinates authenticated A2A calls",
    ),
    AgentAuthorizationPolicy(
        "DevOps Companion Analysis Agent",
        "a2a://devops-companion/analysis",
        "arn:aws:iam::123456789012:role/DevOpsCompanion-Analysis",
        frozenset({"analyze_repository"}),
        frozenset({"devops:analyze"}),
        frozenset({"devops:analyze"}),
        "GitHub App installation token: repository metadata and contents read",
    ),
    AgentAuthorizationPolicy(
        "DevOps Companion IaC Agent",
        "a2a://devops-companion/iac",
        "arn:aws:iam::123456789012:role/DevOpsCompanion-IaC",
        frozenset({"generate_iac"}),
        frozenset({"devops:iac"}),
        frozenset({"devops:iac"}),
        "Separate GitHub App installation token: branch contents and pull requests write",
    ),
    AgentAuthorizationPolicy(
        "DevOps Companion Deploy Agent",
        "a2a://devops-companion/deploy",
        "arn:aws:iam::123456789012:role/DevOpsCompanion-Deploy",
        frozenset({"deploy_staging", "deploy_production"}),
        frozenset({"devops:deploy:staging", "devops:deploy:production"}),
        frozenset({"devops:deploy:staging"}),
        "Assume the AWS account IAM role for staging deployment",
    ),
)


def authorize_agent_call(
    token: str,
    config: Auth0Config,
    policy: AgentAuthorizationPolicy,
    operation: str,
    required_scope: str,
    http_client: Any | None = None,
    discovery: dict | None = None,
    jwks: dict | None = None,
    now: int | None = None,
) -> AgentAuthorizationDecision:
    """Validate user authorization and agent policy at an agent boundary."""
    claims = decode_access_token(
        token,
        config,
        http_client=http_client,
        discovery=discovery,
        jwks=jwks,
    )
    validate_user_token_claims(claims, config, now=now)

    if operation not in policy.allowed_operations:
        raise Auth0Error(f"{policy.name} is not allowed to perform operation {operation}")
    if required_scope not in policy.required_scopes:
        raise Auth0Error(f"{policy.name} policy does not allow scope {required_scope}")

    delegated = token_scopes(claims)
    if required_scope not in delegated:
        raise Auth0Error(
            f"User did not delegate required scope {required_scope} to {policy.name}"
        )
    if required_scope not in policy.permission_ceiling_scopes:
        raise Auth0Error(
            f"{policy.downstream_access} does not permit scope {required_scope}"
        )

    return AgentAuthorizationDecision(
        agent=policy.name,
        a2a_principal=policy.a2a_principal,
        iam_role_arn=policy.iam_role_arn,
        downstream_access=policy.downstream_access,
        operation=operation,
        required_scope=required_scope,
        subject=str(claims["sub"]),
        delegated_scopes=frozenset(delegated),
        effective_scopes=frozenset(
            delegated
            & set(policy.required_scopes)
            & set(policy.permission_ceiling_scopes)
        ),
        token_fingerprint=token_fingerprint(token),
    )
