"""
module3/config/models.py
========================
Model configuration for Module 3 CDK Generation Agent.

Uses LangChain's ChatBedrock interface for Amazon Bedrock access.
Follows the same pattern as Module 2 for consistency.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_aws import ChatBedrock


def get_chat_bedrock_model(
    region: str | None = None,
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    streaming: bool = False,
    **kwargs: Any,
) -> ChatBedrock:
    """
    Get a configured ChatBedrock model for CDK generation.

    Module 3 uses a lower temperature (0.1) for more deterministic code generation
    compared to Module 2's analysis tasks.

    Parameters
    ----------
    region : str, optional
        AWS region for Bedrock. Defaults to AWS_REGION env var or us-east-1.
    model_id : str
        Bedrock model ID. Default is Claude Sonnet 4.
    temperature : float
        Sampling temperature (0.0-1.0). Lower = more deterministic.
        Default 0.1 for code generation.
    max_tokens : int
        Maximum tokens in response. Default 4096 for CDK code.
    streaming : bool
        Enable streaming responses.
    **kwargs
        Additional ChatBedrock parameters.

    Returns
    -------
    ChatBedrock
        Configured LangChain ChatBedrock model.

    Example
    -------
    >>> model = get_chat_bedrock_model(temperature=0.0)
    >>> response = model.invoke("Generate a VPC CDK stack")
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    model = ChatBedrock(
        model_id=model_id,
        region_name=aws_region,
        model_kwargs={
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        },
        streaming=streaming,
    )

    return model


def get_judge_model(
    region: str | None = None,
    model_id: str = "us.anthropic.claude-opus-4-20250514-v1:0",
    temperature: float = 0.0,
) -> ChatBedrock:
    """
    Get a configured ChatBedrock model for LLM-as-judge evaluation.

    Uses Claude Opus (different from the agent's Sonnet) to avoid bias.
    Temperature set to 0.0 for consistent evaluation.

    Parameters
    ----------
    region : str, optional
        AWS region for Bedrock.
    model_id : str
        Bedrock model ID. Default is Claude Opus 4 for evaluation.
    temperature : float
        Sampling temperature. Default 0.0 for deterministic evaluation.

    Returns
    -------
    ChatBedrock
        Configured judge model.
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    model = ChatBedrock(
        model_id=model_id,
        region_name=aws_region,
        model_kwargs={
            "temperature": temperature,
            "max_tokens": 2048,
        },
    )

    return model
