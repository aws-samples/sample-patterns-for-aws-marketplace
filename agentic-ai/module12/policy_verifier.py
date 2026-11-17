"""Deterministic local proof of the Module 12 deployment policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .contracts import GovernanceContext, PolicyResult


READ_ONLY_TOOLS = {
    "read_repository",
    "validate_iac",
    "generate_iac",
    "security_review",
    "get_approval_state",
    "smoke_test",
}
MUTATION_TOOLS = {"apply_infrastructure", "rollback_infrastructure"}
SCENARIOS = Path(__file__).parent / "fixtures" / "scenarios.json"


def evaluate(tool: str, context: GovernanceContext) -> PolicyResult:
    if tool in MUTATION_TOOLS:
        checks = (
            (
                context.session_tainted,
                "deny_tainted_deployment",
                "environment deployment is denied after untrusted repository content taints the session",
            ),
            (
                context.companion_posture == "quarantine"
                or context.snyk_posture == "quarantine",
                "deny_quarantined_posture",
                "environment deployment is denied while the Companion or Snyk posture is quarantined",
            ),
            (
                context.security_review != "approved",
                "deny_security_review",
                "a security review must be approved before deployment",
            ),
            (
                context.financial_approval != "approved",
                "deny_financial_approval",
                "financial approval must be approved before deployment",
            ),
            (
                not context.artifact_digest
                or context.artifact_digest != context.reviewed_artifact_digest,
                "deny_artifact_digest",
                "the proposed artifact digest must match the reviewed artifact digest",
            ),
            (
                context.environment == "production",
                "deny_production_deployment",
                "production deployment is disabled for this demo",
            ),
        )
        for matched, rule, reason in checks:
            if matched:
                return PolicyResult("DENY", rule, reason, tool, context)
        return PolicyResult(
            "ALLOW",
            "allow_environment_deployment",
            "all trusted deployment prerequisites are satisfied",
            tool,
            context,
        )

    if tool in READ_ONLY_TOOLS:
        return PolicyResult(
            "ALLOW",
            "allow_read_only",
            "read-only tools remain available",
            tool,
            context,
        )

    return PolicyResult(
        "DENY",
        "deny_unknown_tool",
        "the tool is not part of the Module 12 demo contract",
        tool,
        context,
    )


def _context(values: dict[str, Any]) -> GovernanceContext:
    # The fixtures intentionally omit digests for readability. The normal
    # scenario represents a matching, reviewed artifact.
    return GovernanceContext(
        session_tainted=bool(values.get("session_tainted", False)),
        companion_posture=values.get("companion_posture", "healthy"),
        snyk_posture=values.get("snyk_posture", "healthy"),
        security_review=values.get("security_review", "approved"),
        financial_approval=values.get("financial_approval", "approved"),
        environment=values.get("environment", "staging"),
        artifact_digest=values.get("artifact_digest", "sha256:approved"),
        reviewed_artifact_digest=values.get(
            "reviewed_artifact_digest", "sha256:approved"
        ),
    )


def load_scenarios() -> dict[str, dict[str, Any]]:
    return json.loads(SCENARIOS.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(load_scenarios()))
    parser.add_argument("--tool", default="apply_infrastructure")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    scenarios = load_scenarios()
    rows: list[dict[str, Any]] = []
    names = sorted(scenarios) if args.all else [args.scenario]
    if names == [None]:
        parser.error("--scenario is required unless --all is used")
    for name in names:
        scenario = scenarios[name]
        context_values = dict(scenario)
        if name == "tainted_repository":
            context_values["session_tainted"] = True
        result = evaluate(args.tool, _context(context_values))
        row = {
            "scenario": name,
            "tool": args.tool,
            "expected": scenario["expected_policy"],
            "actual": result.to_dict(),
        }
        rows.append(row)
        print(json.dumps(row, sort_keys=True))
    return int(any(row["expected"] != row["actual"]["decision"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
