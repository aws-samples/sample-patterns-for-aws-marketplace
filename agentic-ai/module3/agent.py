"""
module3/agent.py
================
Core CDK Infrastructure Generation Agent for Module 3.

This module implements the LangChain-based agent that generates AWS CDK
infrastructure code from repository analysis (Module 2 output) or direct
infrastructure requirements.

FRAMEWORK: LangChain + LangGraph (consistent with Module 2)
MODEL: Claude Sonnet 4 via Amazon Bedrock
PATTERN: ReAct (Reasoning + Acting) with tool calling
"""

from __future__ import annotations

import os
from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable

from module3.config.models import get_chat_bedrock_model
from module3.prompts.system_prompts import SYSTEM_PROMPT
from module3.tools.cdk_tools import ALL_TOOLS


# ---------------------------------------------------------------------------
# Agent Factory (LangGraph ReAct Agent)
# ---------------------------------------------------------------------------

def create_agent(
    *,
    verbose: bool = True,
    max_iterations: int = 20,
    region: str | None = None,
    streaming: bool = False,
) -> Runnable:
    """
    Create a Module 3 CDK Infrastructure Generation Agent using LangGraph.

    This uses LangGraph's create_react_agent which provides a ReAct
    (Reasoning + Acting) loop with automatic tool calling.

    The agent uses:
    - ChatBedrock (LangChain) for model access
    - LangGraph ReAct agent pattern
    - Automatic think-act-observe loop
    - Five CDK generation tools

    Parameters
    ----------
    verbose : bool
        Print agent steps and tool calls. Default True for demos.
    max_iterations : int
        Maximum number of agent loop iterations. Default 20 for complex CDK generation.
    region : str, optional
        AWS region override. Falls back to AWS_REGION env var.
    streaming : bool
        Enable streaming responses from the model.

    Returns
    -------
    Runnable
        Configured LangGraph agent ready to generate CDK infrastructure.

    Example
    -------
    >>> from module3.agent import create_agent
    >>> agent = create_agent()
    >>> result = agent.invoke({
    ...     "messages": [("user", "Generate CDK for a web app with PostgreSQL")]
    ... })
    >>> print(result["messages"][-1].content)
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    # ── REASONING LAYER ──────────────────────────────────────────────────────
    # Use lower temperature (0.1) for more deterministic code generation
    model = get_chat_bedrock_model(
        region=aws_region,
        streaming=streaming,
        temperature=0.1,  # Lower for code generation
        max_tokens=4096,  # Higher for CDK code
    )
    
    if verbose:
        print(f"  [Module 3 Agent] Using LangGraph ReAct Agent")
        print(f"  [Model] Claude Sonnet 4 via Amazon Bedrock")
        print(f"  [Region] {aws_region}")
        print(f"  [Tools] {len(ALL_TOOLS)} CDK generation tools")
        print(f"  [Temperature] 0.1 (deterministic code generation)")
        print()

    # ── AGENT CONSTRUCTION ───────────────────────────────────────────────────
    # LangGraph's create_react_agent provides a simple ReAct loop
    # It handles the think-act-observe pattern automatically
    agent = create_react_agent(
        model,
        ALL_TOOLS,
        state_modifier=SYSTEM_PROMPT,
    )

    return agent


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def generate_infrastructure(
    requirements: str | dict[str, Any],
    region: str = "us-east-1",
    environment: str = "dev",
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Generate CDK infrastructure from requirements.

    This is a convenience function that creates an agent, runs the generation,
    and returns the results in a structured format.

    Parameters
    ----------
    requirements : str or dict
        Infrastructure requirements (Module 2 output or plain text).
    region : str
        AWS region for deployment. Default "us-east-1".
    environment : str
        Environment name (dev/staging/prod). Default "dev".
    verbose : bool
        Print agent steps during generation.

    Returns
    -------
    dict
        Generated CDK code and metadata.

    Example
    -------
    >>> from module3.agent import generate_infrastructure
    >>> requirements = {
    ...     "compute": "ECS Fargate",
    ...     "database": "RDS PostgreSQL",
    ...     "cache": "ElastiCache Redis"
    ... }
    >>> results = generate_infrastructure(requirements, region="us-west-2")
    >>> print(results["cdk_code"])
    """
    agent = create_agent(verbose=verbose, region=region)
    
    # Format requirements
    if isinstance(requirements, dict):
        req_str = f"Infrastructure requirements: {requirements}"
    else:
        req_str = requirements
    
    query = f"""Generate AWS CDK infrastructure code for the following requirements:

{req_str}

Deployment details:
- AWS Region: {region}
- Environment: {environment}

Please:
1. Analyze the infrastructure requirements
2. Ask any necessary clarifying questions
3. Generate production-ready CDK stack code
4. Validate the generated code
5. Provide deployment instructions

Generate individual CDK stacks for each service type (VPC, ECS, RDS, etc.).
"""

    result = agent.invoke({"messages": [("user", query)]})
    
    # Extract the final message from LangGraph response
    messages = result.get("messages", [])
    final_output = messages[-1].content if messages else ""
    
    return {
        "requirements": requirements,
        "region": region,
        "environment": environment,
        "output": final_output,
        "messages": messages,
    }


def validate_cdk_code(cdk_code: str, verbose: bool = True) -> dict[str, Any]:
    """
    Validate CDK code using the agent's validation tools.

    Parameters
    ----------
    cdk_code : str
        CDK stack code to validate.
    verbose : bool
        Print validation steps.

    Returns
    -------
    dict
        Validation results.

    Example
    -------
    >>> from module3.agent import validate_cdk_code
    >>> code = "from aws_cdk import Stack\\n..."
    >>> results = validate_cdk_code(code)
    >>> print(results["status"])
    """
    agent = create_agent(verbose=verbose)
    
    query = f"""Validate the following CDK stack code:

```python
{cdk_code}
```

Check for:
1. Syntax errors
2. Missing imports
3. Best practices
4. Security configurations

Provide a detailed validation report.
"""

    result = agent.invoke({"messages": [("user", query)]})
    
    messages = result.get("messages", [])
    final_output = messages[-1].content if messages else ""
    
    return {
        "cdk_code": cdk_code,
        "validation_output": final_output,
        "messages": messages,
    }
