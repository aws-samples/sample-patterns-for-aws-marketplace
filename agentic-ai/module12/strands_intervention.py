"""Strands framework enforcement for consequential Module 12 tool calls.

The workflow owns the trusted governance context. A Strands
``before_tool_call`` intervention evaluates that context and returns a typed
``Proceed`` or ``Deny`` action before the framework can execute the tool.
AgentCore Gateway remains a separate, external enforcement boundary.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from strands import Agent, tool
from strands.interventions import Deny, InterventionHandler, Proceed
from strands.models.model import Model
from strands.types.tools import ToolContext

try:  # Package imports when executed from the repository.
    from .contracts import GovernanceContext, PolicyResult
    from .policy_verifier import evaluate
except ImportError:  # Top-level imports inside a flattened Runtime image.
    from contracts import GovernanceContext, PolicyResult
    from policy_verifier import evaluate


INTERVENTION_NAME = "companion-governance"
INTERVENTION_LAYER = "strands_before_tool_call"


class CompanionGovernanceIntervention(InterventionHandler):
    """Fail-closed Strands policy intervention for every proposed tool call."""

    def __init__(
        self,
        *,
        on_decision: Callable[[PolicyResult], None] | None = None,
    ) -> None:
        self.last_policy: PolicyResult | None = None
        self._on_decision = on_decision

    @property
    def name(self) -> str:
        return INTERVENTION_NAME

    @property
    def on_error(self) -> str:
        return "deny"

    def before_tool_call(self, event: Any) -> Proceed | Deny:
        """Evaluate workflow-owned facts before Strands executes the tool."""

        context = event.invocation_state.get("governance_context")
        if not isinstance(context, GovernanceContext):
            raise TypeError(
                "trusted GovernanceContext is required in Strands invocation_state"
            )
        tool_name = str(event.tool_use.get("name") or "")
        if tool_name != "apply_infrastructure":
            policy = PolicyResult(
                "DENY",
                "deny_unexpected_deployment_tool",
                "the Deployment agent may propose only apply_infrastructure",
                tool_name,
                context,
            )
        else:
            policy = evaluate(tool_name, context)
        self.last_policy = policy
        if self._on_decision is not None:
            self._on_decision(policy)
        reason = f"{policy.rule}: {policy.reason}"
        if policy.decision == "DENY":
            return Deny(reason=reason)
        return Proceed(reason=reason)


class ScriptedToolProposalModel(Model):
    """Deterministically emit the supplied proposal through the Strands loop.

    Module 12 demonstrates enforcement rather than model quality. This adapter
    turns the host-validated proposal into a real Strands tool-use event so
    the intervention and tool executor run through the framework lifecycle
    without adding model variability to the security scenarios.
    """

    def __init__(self, proposal: Mapping[str, Any]) -> None:
        self._proposal = dict(proposal)
        self._calls = 0
        self._config: dict[str, Any] = {
            "model_id": "module12-scripted-tool-proposal",
        }

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return dict(self._config)

    def structured_output(
        self,
        output_model: type[Any],
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        del output_model, prompt, system_prompt, kwargs

        async def unsupported() -> AsyncGenerator[dict[str, Any], None]:
            raise NotImplementedError(
                "Module 12 uses a deterministic normal tool-use response"
            )
            yield {}

        return unsupported()

    async def stream(
        self,
        messages: Any,
        tool_specs: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        del messages, tool_specs, system_prompt, kwargs
        self._calls += 1
        yield {"messageStart": {"role": "assistant"}}
        if self._calls == 1:
            tool_name = str(
                self._proposal.get("requested_tool") or "apply_infrastructure"
            )
            tool_input = json.dumps(
                {
                    "proposal_summary": str(
                        self._proposal.get("proposal_summary")
                        or "Apply the reviewed staging infrastructure."
                    )
                },
                separators=(",", ":"),
            )
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "toolUseId": "module12-proposed-deployment",
                            "name": tool_name,
                        }
                    }
                }
            }
            yield {
                "contentBlockDelta": {
                    "delta": {"toolUse": {"input": tool_input}}
                }
            }
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {
                "contentBlockDelta": {
                    "delta": {
                        "text": (
                            "The proposed tool call completed its Strands "
                            "intervention and execution lifecycle."
                        )
                    }
                }
            }
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "totalTokens": 0,
                },
                "metrics": {"latencyMs": 0},
            }
        }


@dataclass(frozen=True)
class StrandsToolDecision:
    """Result of one proposed tool call through the Strands agent lifecycle."""

    policy: PolicyResult
    intervention_action: str
    tool_executed: bool
    tool_result: dict[str, Any] | None


def run_strands_tool_call(
    *,
    context: GovernanceContext,
    proposal: Mapping[str, Any],
    execute_tool: Callable[[Mapping[str, Any]], dict[str, Any]],
    on_decision: Callable[[PolicyResult], None] | None = None,
) -> StrandsToolDecision:
    """Run a proposed deployment through Strands intervention and tool execution."""

    execution: dict[str, Any] = {
        "tool_executed": False,
        "tool_result": None,
    }

    @tool(
        name="apply_infrastructure",
        description="Submit the environment deployment after authorization.",
        context=True,
    )
    def apply_infrastructure(
        proposal_summary: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        invocation_context = tool_context.invocation_state.get(
            "governance_context"
        )
        if invocation_context is not context:
            raise RuntimeError("Strands tool received unexpected governance context")
        result = execute_tool({"proposal_summary": proposal_summary})
        execution["tool_executed"] = True
        execution["tool_result"] = result
        return result

    intervention = CompanionGovernanceIntervention(on_decision=on_decision)
    agent = Agent(
        model=ScriptedToolProposalModel(proposal),
        system_prompt=(
            "Submit the supplied infrastructure proposal through the registered "
            "tool. Governance context is host-owned and must not be invented."
        ),
        tools=[apply_infrastructure],
        interventions=[intervention],
        callback_handler=None,
    )
    agent(
        "Evaluate the prepared infrastructure proposal.",
        invocation_state={"governance_context": context},
    )
    policy = intervention.last_policy
    if policy is None:
        policy = PolicyResult(
            "DENY",
            "deny_intervention_failure",
            "the Strands governance intervention failed closed",
            str(proposal.get("requested_tool") or "apply_infrastructure"),
            context,
        )
        if on_decision is not None:
            on_decision(policy)
    tool_executed = bool(execution["tool_executed"])
    if policy.decision == "DENY" and tool_executed:
        raise RuntimeError("Strands executed a tool after a DENY intervention")
    if policy.decision == "ALLOW" and not tool_executed:
        raise RuntimeError("Strands did not execute an allowed tool call")
    return StrandsToolDecision(
        policy=policy,
        intervention_action=(
            "proceed" if policy.decision == "ALLOW" else "deny"
        ),
        tool_executed=tool_executed,
        tool_result=execution["tool_result"],
    )
