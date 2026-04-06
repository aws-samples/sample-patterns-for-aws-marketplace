"""
module4/config/models.py
========================
Model configuration for Module 4 Multi-Agent Orchestration.

Uses LangChain's ChatBedrock interface for Amazon Bedrock access.
Follows the same pattern as Modules 2 and 3 for consistency.
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
    Get a configured ChatBedrock model for orchestration.

    Module 4 uses temperature=0.1 for deterministic orchestration decisions
    (routing, sequencing, aggregation).

    Parameters
    ----------
    region : str, optional
        AWS region for Bedrock. Defaults to AWS_REGION env var or us-east-1.
    model_id : str
        Bedrock model ID. Default is Claude Sonnet 4.
    temperature : float
        Sampling temperature (0.0-1.0). Default 0.1 for orchestration.
    max_tokens : int
        Maximum tokens in response. Default 4096.
    streaming : bool
        Enable streaming responses.
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
        streaming=streaming,
    )

    return model
