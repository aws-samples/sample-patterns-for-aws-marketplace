from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("module8-agent-guard-secret-probe")

POLICY_NAME = "module8-mcp-tool-allowlist-v1"
ALLOWED_ACTIONS = {"list_private_repositories"}


def _credential_metadata(env_var: str) -> dict:
    return {"present": os.environ.get(env_var) is not None}


def evaluate_guarded_action(
    action: str,
    request_id: str,
    env_var: str = "GITHUB_TOKEN",
) -> dict:
    """Apply the MCP tool's action allowlist without exposing its credential."""
    normalized_action = action.strip().lower()
    base_result = {
        "request_id": request_id,
        "action": normalized_action,
        "policy": POLICY_NAME,
    }

    if normalized_action not in ALLOWED_ACTIONS:
        return {
            **base_result,
            "credential_state": _credential_metadata(env_var),
            "decision": "blocked",
            "blocked": True,
            "executed": False,
            "reason": "Action is not on the protected MCP tool allowlist.",
        }

    credential_state = _credential_metadata(env_var)
    if not credential_state["present"]:
        return {
            **base_result,
            "credential_state": credential_state,
            "decision": "allowed",
            "blocked": False,
            "executed": False,
            "reason": "Required credential is unavailable in the protected process.",
        }

    return {
        **base_result,
        "credential_state": credential_state,
        "decision": "allowed",
        "blocked": False,
        "executed": True,
        "result": {
            "repositories": ["api-service", "frontend", "infra-cdk"],
            "count": 3,
        },
    }


@mcp.tool()
def execute_guarded_action(
    action: str,
    request_id: str,
    env_var: str = "GITHUB_TOKEN",
) -> dict:
    """Run an allowlisted operation or return a structured policy denial."""
    return evaluate_guarded_action(action, request_id, env_var)


if __name__ == "__main__":
    mcp.run("stdio")
