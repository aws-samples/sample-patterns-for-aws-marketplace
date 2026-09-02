"""
config/models.py
================
Model provider configuration for the AWS Infrastructure Agent.

PROVIDERS USED IN THIS PROJECT
--------------------------------
Both are available with free trials through AWS Marketplace / Bedrock:

  1. ANTHROPIC — Claude Sonnet 4 via Amazon Bedrock
     Access : Amazon Bedrock → Model Access → Enable Anthropic models
     Free   : Pay-per-token, no subscription fee; enable in AWS Console
     Model  : us.anthropic.claude-sonnet-4-6 (cross-region)
     Why    : Primary reasoning engine — best instruction-following,
              tool use, and multi-step reasoning for infra tasks.

  2. HUGGING FACE — Open models via Bedrock Marketplace
     Access : Amazon Bedrock → Model Catalog → Filter by "Hugging Face"
              Deploy a model (e.g. Mistral-7B-Instruct) as a SageMaker
              JumpStart endpoint, then use the endpoint ARN as the modelId.
     Free   : No subscription needed for public HF models; you only pay
              for SageMaker instance compute during deployment.
     Why    : Demonstrates model-agnostic architecture — the same Strands
              agent and tools work unchanged with a different reasoning engine.

SWITCHING MODELS (what to highlight in the workshop)
------------------------------------------------------
The model is the ONLY thing that changes. Tools, system prompt, orchestration
layer, and AgentCore wrapper are all identical regardless of which model runs.

    # Anthropic (default — best for the use case)
    model = get_bedrock_model()

    # Hugging Face via Bedrock Marketplace (open-source alternative)
    model = get_hf_bedrock_model(endpoint_arn="arn:aws:sagemaker:...")
"""

from __future__ import annotations

import os

from strands.models import BedrockModel


# ---------------------------------------------------------------------------
# Anthropic — Claude Sonnet 4 via Amazon Bedrock
# ---------------------------------------------------------------------------

# Cross-region inference profile (recommended — auto-routes for availability)
CLAUDE_SONNET_4_CRI = "us.anthropic.claude-sonnet-4-6"

# Single-region model ID. Note that on-demand invocation requires an
# inference profile, so this form needs provisioned throughput.
# Prefer the cross-region profile above.
CLAUDE_SONNET_4_DIRECT = "anthropic.claude-sonnet-4-6"


def get_bedrock_model(
    model_id: str = CLAUDE_SONNET_4_CRI,
    region: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> BedrockModel:
    """
    Return a Strands BedrockModel configured for Claude Sonnet 4.

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
        Low temperature (0.1) = more deterministic — appropriate for infra tasks.
    max_tokens : int
        Max response tokens. 4096 is sufficient for analysis and plans.
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
    return BedrockModel(
        model_id=model_id,
        region_name=aws_region,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ---------------------------------------------------------------------------
# Hugging Face — Open models via Amazon Bedrock Marketplace
# ---------------------------------------------------------------------------

def get_hf_bedrock_model(
    endpoint_arn: str,
    region: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.1,
) -> BedrockModel:
    """
    Return a Strands BedrockModel backed by a Hugging Face model deployed
    through Amazon Bedrock Marketplace (SageMaker JumpStart endpoint).

    This demonstrates that the Strands agent is fully model-agnostic.
    The same tools, system prompt, and AgentCore wrapper work unchanged.

    HOW TO SET UP A HUGGING FACE BEDROCK MARKETPLACE ENDPOINT
    ----------------------------------------------------------
    1. Open AWS Console → Amazon Bedrock → Model Catalog
    2. Filter by Provider: "Hugging Face"
    3. Choose a model — recommended for this workshop:
         • Mistral-7B-Instruct-v0.3   (capable, fast, no subscription needed)
         • Meta Llama 3.1 8B Instruct (strong instruction following)
    4. Click "Deploy" → select instance (ml.g5.2xlarge is a good starting point)
    5. Wait for status "In service" in Bedrock → Foundation Models →
       Marketplace deployments
    6. Copy the SageMaker endpoint ARN from the deployment details page
    7. Set env var:  export HF_ENDPOINT_ARN="arn:aws:sagemaker:..."
    8. Call this function or use: agent = create_agent(use_hf=True)

    Note: Public HF models have NO subscription fee. You pay only for the
    SageMaker instance compute while the endpoint is running.

    Parameters
    ----------
    endpoint_arn : str
        SageMaker endpoint ARN from step 6 above.
        Format: arn:aws:sagemaker:<region>:<account>:endpoint/<name>
    region : str, optional
        AWS region where the endpoint is deployed.
    max_tokens : int
        Smaller HF models may need a lower max_tokens ceiling.
    temperature : float
        Controls output randomness. Keep low for deterministic infra tasks.
    """
    aws_region = region or os.getenv("AWS_REGION") or "us-east-1"

    # Bedrock Marketplace endpoints use the SageMaker endpoint ARN directly
    # as the modelId — this is the standard Bedrock Marketplace invocation pattern.
    return BedrockModel(
        model_id=endpoint_arn,
        region_name=aws_region,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ---------------------------------------------------------------------------
# Convenience: model info for demo output
# ---------------------------------------------------------------------------

PROVIDER_INFO = {
    "anthropic": {
        "name": "Claude Sonnet 4",
        "vendor": "Anthropic",
        "access": "Amazon Bedrock (enable model access in Console)",
        "model_id": CLAUDE_SONNET_4_CRI,
        "free_trial": "No subscription — pay per token after enabling model access",
        "context_window": "200,000 tokens",
        "strengths": "Best-in-class tool use, instruction following, multi-step reasoning",
    },
    "huggingface": {
        "name": "Hugging Face model (e.g. Mistral-7B-Instruct)",
        "vendor": "Hugging Face via Bedrock Marketplace",
        "access": "Bedrock → Model Catalog → Filter by Hugging Face → Deploy",
        "model_id": "SageMaker endpoint ARN (from deployment)",
        "free_trial": "Public HF models: no subscription fee — pay only for compute",
        "context_window": "Varies by model (4K–32K typically)",
        "strengths": "Open source, data stays in your VPC, no vendor lock-in",
        "setup_url": "https://huggingface.co/blog/bedrock-marketplace",
    },
}


def print_provider_info(provider: str = "anthropic") -> None:
    """Print provider information for workshop demonstrations."""
    info = PROVIDER_INFO.get(provider, {})
    if not info:
        print(f"Unknown provider: {provider}")
        return
    print(f"\n  Model Provider: {info['vendor']}")
    print(f"  Model         : {info['name']}")
    print(f"  Access        : {info['access']}")
    print(f"  Model ID      : {info['model_id']}")
    print(f"  Free trial    : {info['free_trial']}")
    print(f"  Context window: {info['context_window']}")
    print(f"  Strengths     : {info['strengths']}")
    if "setup_url" in info:
        print(f"  Setup guide   : {info['setup_url']}")
    print()


class ModelConfig:
    """Simple namespace for model configuration constants."""
    CLAUDE_SONNET_4 = CLAUDE_SONNET_4_CRI
    CLAUDE_SONNET_4_DIRECT = CLAUDE_SONNET_4_DIRECT
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_MAX_TOKENS = 4096
