"""Small real-model agent steps for the deployed Module 12 Runtime.

The agents intentionally perform no substantive engineering work. Each one
makes a genuine Bedrock model call and returns a short fictional status message.
Trusted workflow facts and authorization decisions remain deterministic host
responsibilities.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config
from strands import Agent
from strands.models import BedrockModel

try:
    from .telemetry import configure_runtime_telemetry
except ImportError:
    from telemetry import configure_runtime_telemetry


DEFAULT_MODELS = {
    "Analysis": "us.openai.gpt-5.6-luna",
    "IaC": "us.openai.gpt-5.6-terra",
    "Deployment": "us.openai.gpt-5.6-sol",
}
MODEL_ENVIRONMENT = {
    "Analysis": "MODULE12_ANALYSIS_MODEL_ID",
    "IaC": "MODULE12_IAC_MODEL_ID",
    "Deployment": "MODULE12_DEPLOYMENT_MODEL_ID",
}
ROLE_PROMPTS = {
    "Analysis": (
        "This is a controlled security-demo simulation. Do not inspect files, call "
        "tools, generate code, or claim real findings. Reply with one short sentence "
        "saying that the fictional repository review is ready for trusted workflow "
        "checks."
    ),
    "IaC": (
        "This is a controlled security-demo simulation. Do not generate code, "
        "templates, commands, or real infrastructure results. Reply with one short "
        "sentence saying that a fictional staging proposal is ready for trusted "
        "workflow checks."
    ),
    "Deployment": (
        "This is a controlled security-demo simulation. Do not call tools or change "
        "infrastructure. Reply with one short sentence saying that a fictional "
        "deployment request is ready for authorization."
    ),
}


@dataclass(frozen=True)
class AgentRun:
    """Evidence that one real Strands agent invoked a Bedrock model."""

    role: str
    model_id: str
    reply: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "model_id": self.model_id,
            "reply": self.reply,
            "stop_reason": self.stop_reason,
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
            },
        }


class BedrockAgentSession:
    """Run independent Strands agents inside one AgentCore Runtime request."""

    def __init__(
        self,
        *,
        region_name: str | None = None,
        boto_session: boto3.Session | None = None,
    ) -> None:
        self.region_name = (
            region_name
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.boto_session = boto_session or boto3.Session(
            region_name=self.region_name
        )
        self.client_config = Config(
            connect_timeout=5,
            read_timeout=90,
            retries={"mode": "adaptive", "total_max_attempts": 4},
            user_agent_extra="module12-agentcore-runtime",
        )

    def invoke(self, role: str, *, scenario: str) -> dict[str, Any]:
        """Invoke one real model while keeping the task deliberately trivial."""

        if role not in DEFAULT_MODELS:
            raise ValueError(f"unknown Module 12 agent role: {role}")
        model_id = os.environ.get(
            MODEL_ENVIRONMENT[role],
            DEFAULT_MODELS[role],
        )
        model = BedrockModel(
            boto_session=self.boto_session,
            boto_client_config=self.client_config,
            model_id=model_id,
            max_tokens=96,
            streaming=False,
        )
        agent = Agent(
            name=f"module12-{role.casefold()}",
            description=(
                f"Module 12 {role} demo agent. Produces only a fictional status "
                "message; deterministic workflow code owns all trusted decisions."
            ),
            model=model,
            system_prompt=(
                "You are participating in an AWS security workshop demo. Follow the "
                "requested response format exactly. Never invent security posture, "
                "approval, digest, authorization, or execution results."
            ),
            callback_handler=None,
        )
        result = agent(
            f"Scenario label: {scenario}. {ROLE_PROMPTS[role]}"
        )
        usage = dict(result.metrics.accumulated_usage or {})
        reply = " ".join(str(result).split())[:240]
        record = AgentRun(
            role=role,
            model_id=model_id,
            reply=reply,
            stop_reason=str(result.stop_reason),
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            total_tokens=int(usage.get("totalTokens", 0)),
        )
        if record.total_tokens <= 0:
            raise RuntimeError(
                f"{role} agent returned no Bedrock token usage evidence"
            )
        return record.to_dict()


def session_from_environment() -> BedrockAgentSession | None:
    """Enable live agents only in the deployed Runtime."""

    enabled = os.environ.get("MODULE12_LIVE_AGENTS", "").casefold()
    if enabled not in {"1", "true", "yes"}:
        return None
    configure_runtime_telemetry()
    return BedrockAgentSession()
