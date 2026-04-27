"""
module4/agent.py
================
Multi-Agent Orchestrator for Module 4.

This module implements a LangGraph-based orchestrator that coordinates
specialist agents (Modules 1-3) using two communication protocols:
- Direct HTTP: REST calls for Modules 1 and 2
- MCP (Model Context Protocol): Tool-based integration for Module 3

FRAMEWORK: LangChain + LangGraph (consistent with Modules 2 and 3)
MODEL: Claude Sonnet 4 via Amazon Bedrock
PATTERN: Orchestrator with tool-based delegation
"""

from __future__ import annotations

import os
from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import Runnable

from module4.config.models import get_chat_bedrock_model
from module4.prompts.system_prompts import ORCHESTRATOR_PROMPT
from module4.tools.orchestration_tools import ALL_TOOLS as A2A_TOOLS
from module4.protocols.mcp_protocol import MCP_TOOLS


# ---------------------------------------------------------------------------
# Agent Factory (LangGraph ReAct Agent)
# ---------------------------------------------------------------------------

def create_orchestrator(
    *,
    verbose: bool = True,
    max_iterations: int = 25,
    region: str | None = None,
    streaming: bool = False,
    include_mcp: bool = True,
) -> Runnable:
    """
    Create a Module 4 Multi-Agent Orchestrator using LangGraph.

    The orchestrator has two sets of tools:
    - Direct HTTP tools: For calling Modules 1 and 2 via HTTP (call_infrastructure_agent,
      call_repository_agent, run_sequential_pipeline, run_parallel_fanout, synthesize_results)
    - MCP tools: For calling Module 3 via MCP protocol (mcp_analyze_requirements,
      mcp_generate_cdk, mcp_validate_cdk)

    Parameters
    ----------
    verbose : bool
        Print agent steps and tool calls. Default True for demos.
    max_iterations : int
        Maximum number of agent loop iterations. Default 25 for complex orchestration.
    region : str, optional
        AWS region override. Falls back to AWS_REGION env var.
    streaming : bool
        Enable streaming responses from the model.
    include_mcp : bool
        Include MCP tools for Module 3. Default True.

    Returns
    -------
    Runnable
        Configured LangGraph orchestrator agent.

    Example
    -------
    >>> from module4.agent import create_orchestrator
    >>> orchestrator = create_orchestrator()
    >>> result = orchestrator.invoke({
    ...     "messages": [("user", "Analyze my repo and generate infrastructure")]
    ... })
    >>> print(result["messages"][-1].content)
    """
    aws_region = region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    # ── REASONING LAYER ──────────────────────────────────────────────────────
    model = get_chat_bedrock_model(
        region=aws_region,
        streaming=streaming,
        temperature=0.1,
        max_tokens=4096,
    )

    # ── TOOLS ────────────────────────────────────────────────────────────────
    # Combine A2A tools (Modules 1 & 2) with MCP tools (Module 3)
    all_tools = list(A2A_TOOLS)
    if include_mcp:
        all_tools.extend(MCP_TOOLS)

    if verbose:
        a2a_names = [t.name for t in A2A_TOOLS]
        mcp_names = [t.name for t in MCP_TOOLS] if include_mcp else []
        print(f"  [Module 4 Orchestrator] Using LangGraph ReAct Agent")
        print(f"  [Model] Claude Sonnet 4 via Amazon Bedrock")
        print(f"  [Region] {aws_region}")
        print(f"  [HTTP Tools] {len(a2a_names)}: {', '.join(a2a_names)}")
        print(f"  [MCP Tools] {len(mcp_names)}: {', '.join(mcp_names)}")
        print(f"  [Total Tools] {len(all_tools)}")
        print()

    # ── AGENT CONSTRUCTION ───────────────────────────────────────────────────
    agent = create_react_agent(
        model,
        all_tools,
        prompt=ORCHESTRATOR_PROMPT,
    )

    return agent


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def orchestrate_request(
    request: str,
    region: str = "us-east-1",
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Orchestrate a multi-agent request end-to-end.

    Parameters
    ----------
    request : str
        User's request to orchestrate across specialist agents.
    region : str
        AWS region. Default "us-east-1".
    verbose : bool
        Print orchestration steps.

    Returns
    -------
    dict
        Orchestration results with agent outputs and synthesis.

    Example
    -------
    >>> from module4.agent import orchestrate_request
    >>> results = orchestrate_request(
    ...     "Check my infrastructure health and analyze my repository"
    ... )
    >>> print(results["output"])
    """
    orchestrator = create_orchestrator(verbose=verbose, region=region)

    result = orchestrator.invoke({"messages": [("user", request)]})

    messages = result.get("messages", [])
    final_output = messages[-1].content if messages else ""

    return {
        "request": request,
        "region": region,
        "output": final_output,
        "messages": messages,
    }
