"""Stable contracts shared by the Module 12 runtime, tools, and demo driver."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Posture = Literal["healthy", "quarantine"]
PolicyDecision = Literal["ALLOW", "DENY"]
ApprovalStatus = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class GovernanceContext:
    """Trusted workflow facts used to evaluate a consequential tool call.

    These fields must be populated by the workflow/control plane. Model output
    is never allowed to write them.
    """

    session_tainted: bool = False
    companion_posture: Posture = "healthy"
    snyk_posture: Posture = "healthy"
    security_review: ApprovalStatus = "approved"
    financial_approval: ApprovalStatus = "approved"
    environment: str = "staging"
    artifact_digest: str = ""
    reviewed_artifact_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    rule: str
    reason: str
    tool: str
    context: GovernanceContext

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "rule": self.rule,
            "reason": self.reason,
            "tool": self.tool,
            "context": self.context.to_dict(),
        }


@dataclass(frozen=True)
class WorkflowEvent:
    stage: str
    agent_role: str
    tool: str
    status: str
    detail: str = ""
    policy: PolicyResult | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        if self.policy is not None:
            value["policy"] = self.policy.to_dict()
        return value


@dataclass
class WorkflowOutcome:
    workflow_id: str
    session_id: str
    scenario: str
    status: str
    events: list[WorkflowEvent] = field(default_factory=list)
    mutation_recorded: bool = False
    smoke_test_status: str = "not_started"
    response: dict[str, Any] = field(default_factory=dict)
    spans: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "scenario": self.scenario,
            "status": self.status,
            "events": [event.to_dict() for event in self.events],
            "mutation_recorded": self.mutation_recorded,
            "smoke_test_status": self.smoke_test_status,
            "response": self.response,
            "spans": self.spans,
        }
