"""
routing-agent/config/models.py
===============================
Model configuration for routing agent.

Uses the same ChatBedrock configuration as other modules.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_aws import ChatBedrock


def get_chat_bedrock_model(
    region: str | None = None,
    model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0",
    temperature: float = 0.0,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> ChatBedrock:
    """
    Get a configured ChatBedrock model for intent classification.

    Uses temperature=0.0 for deterministic classification.

    Parameters
    ----------
    region : str, optional
        AWS region for Bedrock.
    model_id : str
        Bedrock model ID.
    temperature : float
        Sampling temperature. Default 0.0 for deterministic classification.
    max_tokens : int
        Maximum tokens in response. Default 1024 (classification is short).
    **kwargs
        Additional ChatBedrock parameters.

    Returns
    -------
    ChatBedrock
        Configured LangChain ChatBedrock model.
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
    )

    return model
