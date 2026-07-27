from __future__ import annotations


def generate_boundary_evidence() -> dict:
    """Return deterministic sanitized evidence matching the live Agent Guard probe."""
    return {
        "agent_process": {
            "credential_present_before": False,
            "credential_present_after": False,
        },
        "secret_source": "aws://devops-companion-github-token/GITHUB_TOKEN",
        "operation": {
            "request_id": "repository-list-mock-001",
            "action": "list_private_repositories",
            "policy": "module8-mcp-tool-allowlist-v1",
            "decision": "allowed",
            "blocked": False,
            "executed": True,
            "credential_present_in_protected_process": True,
            "target_result": "representative",
            "result": {
                "repositories": ["api-service", "frontend", "infra-cdk"],
                "count": 3,
            },
        },
        "operation_audit": {
            "request_recorded": True,
            "response_recorded": True,
        },
    }
