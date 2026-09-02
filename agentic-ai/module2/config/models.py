"""
module2/config/models.py
========================
Model provider configuration for Module 2 Repository Analysis Agent.

This module uses LangChain's ChatBedrock for model access, demonstrating
the Module 2 framework approach compared to Module 1's Strands BedrockModel.

FRAMEWORK COMPARISON
--------------------
Module 1 (Strands):
    from strands.models import BedrockModel
    model = BedrockModel(model_id="...", region_name="...")

Module 2 (LangChain):
    from langchain_aws import ChatBedrock
    model = ChatBedrock(model_id="...", region_name="...")

Both use the same underlying Amazon Bedrock API, but LangChain provides
additional features like streaming, callbacks, and integration with the
broader LangChain ecosystem.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_aws import ChatBedrock

# Cross-region inference profile (recommended)
CLAUDE_SONNET_4_CRI = "us.anthropic.claude-sonnet-4-6"

# Single-region model ID (fallback)
CLAUDE_SONNET_4_DIRECT = "anthropic.claude-sonnet-4-6"


def get_chat_bedrock_model(
    model_id: str = CLAUDE_SONNET_4_CRI,
    region: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    streaming: bool = False,
    **kwargs: Any,
) -> ChatBedrock:
    """
    Return a LangChain ChatBedrock model configured for Claude Sonnet 4.

    This is the Module 2 equivalent of Module 1's get_bedrock_model().
    The key difference is that ChatBedrock integrates with LangChain's
    LCEL (LangChain Expression Language) and supports streaming responses.

    Prerequisites
    -------------
    1. AWS credentials configured (aws configure or AWS_* env vars)
    2. Bedrock model access enabled for Anthropic in your region:
       AWS Console → Amazon Bedrock → Model Access → Request Access

    Parameters
    ----------
    model_id : str
        Bedrock model ID. Default uses cross-region inference profile.
    region : str, optional
        AWS region. Falls back to AWS_REGION / AWS_DEFAULT_REGION env vars.
    temperature : float
        Low temperature (0.1) = more deterministic — appropriate for analysis tasks.
    max_tokens : int
        Max response tokens. 4096 is sufficient for structured analysis.
    streaming : bool
        Enable streaming responses. Useful for long-running analysis.
    **kwargs : Any
        Additional ChatBedrock parameters (e.g., model_kwargs).

    Returns
    -------
    ChatBedrock
        Configured LangChain ChatBedrock model instance.

    Example
    -------
    >>> from module2.config.models import get_chat_bedrock_model
    >>> model = get_chat_bedrock_model()
    >>> response = model.invoke("Analyze this repository...")
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    # LangChain ChatBedrock configuration
    return ChatBedrock(
        model_id=model_id,
        region_name=aws_region,
        model_kwargs={
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        streaming=streaming,
        **kwargs,
    )


class ModelConfig:
    """Configuration constants for Module 2 models."""

    CLAUDE_SONNET_4 = CLAUDE_SONNET_4_CRI
    CLAUDE_SONNET_4_DIRECT = CLAUDE_SONNET_4_DIRECT
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_STREAMING = False
