from __future__ import annotations

import uuid
from typing import Any

from module8.identity.context import UserAuthorizationContext

POLICY_VERSION = "devops-companion-agent-authz-v1"
APPROVAL_ID = "approval-deploy-staging-001"
REQUIRED_WORKFLOW_SCOPES = frozenset(
    {"devops:analyze", "devops:iac", "devops:deploy:staging"}
)

ORCHESTRATOR_PRINCIPAL = "a2a://devops-companion/orchestrator"
ANALYSIS_PRINCIPAL = "a2a://devops-companion/analysis"
IAC_PRINCIPAL = "a2a://devops-companion/iac"
DEPLOY_PRINCIPAL = "a2a://devops-companion/deploy"
ANALYSIS_GITHUB_PRINCIPAL = (
    "github-app-installation://devops-companion-analysis/481516"
)
IAC_GITHUB_PRINCIPAL = "github-app-installation://devops-companion-iac/481517"
DEPLOY_ROLE = (
    "arn:aws:iam::123456789012:role/DevOpsCompanion-Deploy-EKS"
)
STACK_ARN = (
    "arn:aws:cloudformation:us-east-1:123456789012:"
    "stack/DevOpsCompanion-Staging/51af3dc0-4d8f-11ef-9a12-0afff73b2c71"
)


def _evidence_record(
    workflow_execution_id: str,
    trace_point: str,
    answer: str,
    evidence_source: str,
    *,
    actor: str,
    action: str,
    required_scope: str | None = None,
    decision: str | None = None,
    target_principal: str | None = None,
    external_event_id: str | None = None,
    approval_id: str | None = None,
    token_fingerprint: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "workflow_execution_id": workflow_execution_id,
        "trace_point": trace_point,
        "answer": answer,
        "evidence_source": evidence_source,
        "actor": actor,
        "action": action,
        "required_scope": required_scope,
        "decision": decision,
        "target_principal": target_principal,
        "external_event_id": external_event_id,
        "approval_id": approval_id,
        "token_fingerprint": token_fingerprint,
        "details": details or {},
    }


def _cloudtrail_event(workflow_execution_id: str) -> dict[str, Any]:
    session_arn = (
        "arn:aws:sts::123456789012:assumed-role/"
        f"DevOpsCompanion-Deploy-EKS/deploy-phase-{workflow_execution_id}"
    )
    event_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{workflow_execution_id}|ExecuteChangeSet|{STACK_ARN}",
        )
    )
    return {
        "eventID": event_id,
        "eventName": "ExecuteChangeSet",
        "userIdentity": {
            "type": "AssumedRole",
            "arn": session_arn,
            "sessionContext": {
                "sessionIssuer": {"arn": DEPLOY_ROLE},
                "sourceIdentity": workflow_execution_id,
            },
        },
        "resources": [{"ARN": STACK_ARN}],
        "eventSource": "cloudformation.amazonaws.com",
    }


def generate_identity_trace(
    workflow_execution_id: str,
    authorization_context: UserAuthorizationContext,
) -> dict[str, Any]:
    """Build the compact evidence chain displayed by Section 3."""
    missing_scopes = REQUIRED_WORKFLOW_SCOPES - authorization_context.delegated_scopes
    if missing_scopes:
        raise ValueError(
            "Cannot build the deployment trace because the user did not delegate: "
            + ", ".join(sorted(missing_scopes))
        )

    cloudtrail_event = _cloudtrail_event(workflow_execution_id)
    deploy_session = cloudtrail_event["userIdentity"]["arn"]
    delegated_scopes = sorted(authorization_context.delegated_scopes)
    repository = "github://example-org/payments-api"

    evidence_records = [
        _evidence_record(
            workflow_execution_id,
            "Original delegation",
            authorization_context.email,
            "Auth0 token and DevOps Companion application record",
            actor=authorization_context.subject,
            action="user_delegation_accepted",
            target_principal=ORCHESTRATOR_PRINCIPAL,
            token_fingerprint=authorization_context.token_fingerprint,
            details={
                "issuer": authorization_context.issuer,
                "audience": authorization_context.audience,
                "delegated_scopes": delegated_scopes,
                "user_identity_hash": authorization_context.user_identity_hash,
            },
        ),
        _evidence_record(
            workflow_execution_id,
            "Repository analysis",
            "repository contents read",
            "Representative GitHub audit/API record",
            actor=ANALYSIS_PRINCIPAL,
            action="github_repository_read",
            required_scope="devops:analyze",
            decision="ALLOW",
            target_principal=ANALYSIS_GITHUB_PRINCIPAL,
            external_event_id="github-request-analysis-9301",
            token_fingerprint=authorization_context.token_fingerprint,
            details={"resource": repository, "policy_version": POLICY_VERSION},
        ),
        _evidence_record(
            workflow_execution_id,
            "Generated IaC",
            "pull request 184",
            "Representative GitHub audit/API record",
            actor=IAC_PRINCIPAL,
            action="github_pull_request_opened",
            required_scope="devops:iac",
            decision="ALLOW",
            target_principal=IAC_GITHUB_PRINCIPAL,
            external_event_id="github-request-iac-9304",
            token_fingerprint=authorization_context.token_fingerprint,
            details={
                "resource": f"{repository}/pull/184",
                "policy_version": POLICY_VERSION,
            },
        ),
        _evidence_record(
            workflow_execution_id,
            "Human approval",
            APPROVAL_ID,
            "Representative DevOps Companion approval record",
            actor="auth0|reviewer-jordan-blake",
            action="deployment_approved",
            required_scope="devops:deploy:staging",
            decision="APPROVED",
            approval_id=APPROVAL_ID,
            details={"approved_by": "jordan.blake@example.com"},
        ),
        _evidence_record(
            workflow_execution_id,
            "Deploy authorization",
            "ALLOW devops:deploy:staging",
            "DevOps Companion application policy",
            actor=DEPLOY_PRINCIPAL,
            action="deploy_agent_action_authorized",
            required_scope="devops:deploy:staging",
            decision="ALLOW",
            target_principal=DEPLOY_ROLE,
            approval_id=APPROVAL_ID,
            token_fingerprint=authorization_context.token_fingerprint,
            details={"policy_version": POLICY_VERSION},
        ),
        _evidence_record(
            workflow_execution_id,
            "STS role session",
            workflow_execution_id,
            "Representative STS AssumeRole record",
            actor=DEPLOY_PRINCIPAL,
            action="deployment_role_assumed",
            target_principal=deploy_session,
            external_event_id="cloudtrail-assume-role-9305",
            approval_id=APPROVAL_ID,
            details={"role": DEPLOY_ROLE, "source_identity": workflow_execution_id},
        ),
        _evidence_record(
            workflow_execution_id,
            "CloudTrail deployment",
            cloudtrail_event["eventName"],
            "Representative CloudTrail record",
            actor=deploy_session,
            action="aws_deployment_action_recorded",
            target_principal=deploy_session,
            external_event_id=cloudtrail_event["eventID"],
            approval_id=APPROVAL_ID,
            details={"resource": STACK_ARN},
        ),
    ]

    reverse_investigation = [
        {
            "trace_point": record["trace_point"],
            "answer": record["answer"],
            "evidence": (
                f"source={record['evidence_source']}; "
                f"actor={record['actor']}"
            ),
        }
        for record in reversed(evidence_records)
    ]

    return {
        "workflow_execution_id": workflow_execution_id,
        "evidence_records": evidence_records,
        "representative_cloudtrail_event": cloudtrail_event,
        "reverse_investigation": reverse_investigation,
    }
