"""
module4/tools/orchestration_tools.py
=====================================
Tools for the orchestrator agent to coordinate specialist agents.

These tools give the orchestrator the ability to:
1. Call specialist agents via Direct HTTP
2. Run sequential pipelines (Agent A -> Agent B)
3. Run parallel fan-out (Agent A + Agent B simultaneously)
4. Synthesize results from multiple agents

DESIGN PRINCIPLES
-----------------
- Orchestrator delegates, never does the work itself
- Tools abstract communication protocol details
- Mock mode for demos without running agent servers
- Structured JSON output for consistent parsing
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from module4.protocols.a2a_protocol import A2AClient


# Shared A2A client instance
_a2a = A2AClient(verbose=os.getenv("AGENT_MOCK_MODE", "true").lower() == "true")


def _wrap(data: Any, tool_name: str) -> str:
    """Wrap tool output in consistent JSON envelope."""
    return json.dumps(
        {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        },
        indent=2,
        default=str,
    )


# ---------------------------------------------------------------------------
# Tool 1: Call Infrastructure Agent (Module 1) via Direct HTTP
# ---------------------------------------------------------------------------

@tool
def call_infrastructure_agent(task: str, region: str = "us-east-1") -> str:
    """
    Call the Infrastructure Agent (Module 1) via Direct HTTP.

    Sends an HTTP request to Module 1 to observe and analyze AWS infrastructure.

    Supported tasks:
    - health_check: Check health of all services in a region
    - list_resources: List all AWS resources in a region

    Args:
        task: Task to execute (health_check, list_resources)
        region: AWS region to analyze (default: us-east-1)

    Returns:
        JSON string with infrastructure analysis results
    """
    result = _a2a.call_agent("module1", task, region=region)
    return _wrap(result, "call_infrastructure_agent")


# ---------------------------------------------------------------------------
# Tool 2: Call Repository Agent (Module 2) via Direct HTTP
# ---------------------------------------------------------------------------

@tool
def call_repository_agent(task: str, repo_path: str = "/mock/repo/nodejs-app") -> str:
    """
    Call the Repository Analysis Agent (Module 2) via Direct HTTP.

    Sends an HTTP request to Module 2 to analyze a code repository.

    Supported tasks:
    - analyze_repository: Full repository analysis with AWS mapping
    - scan_structure: Quick scan of file structure and languages

    Args:
        task: Task to execute (analyze_repository, scan_structure)
        repo_path: Path to the repository to analyze

    Returns:
        JSON string with repository analysis results
    """
    result = _a2a.call_agent("module2", task, repo_path=repo_path)
    return _wrap(result, "call_repository_agent")


# ---------------------------------------------------------------------------
# Tool 3: Run Sequential Pipeline via Direct HTTP
# ---------------------------------------------------------------------------

@tool
def run_sequential_pipeline(pipeline_json: str) -> str:
    """
    Run a sequential pipeline of agent tasks via Direct HTTP.

    Each task runs after the previous one completes. Use this when
    Agent B needs Agent A's output (e.g., analyze repo THEN generate CDK).

    Args:
        pipeline_json: JSON array of task definitions. Each task has:
            - agent_id: Target agent (module1, module2, module3)
            - task: Task type to execute
            Example: [{"agent_id": "module2", "task": "analyze_repository"},
                      {"agent_id": "module3", "task": "generate_cdk"}]

    Returns:
        JSON string with ordered results from each pipeline step
    """
    try:
        tasks = json.loads(pipeline_json)
    except json.JSONDecodeError:
        return _wrap({"error": "Invalid JSON in pipeline definition"}, "run_sequential_pipeline")

    results = _a2a.call_agents_sequential(tasks)

    return _wrap(
        {
            "pipeline_type": "sequential",
            "total_steps": len(tasks),
            "results": results,
        },
        "run_sequential_pipeline",
    )


# ---------------------------------------------------------------------------
# Tool 4: Run Parallel Fan-Out via Direct HTTP
# ---------------------------------------------------------------------------

@tool
def run_parallel_fanout(tasks_json: str) -> str:
    """
    Run multiple agent tasks in parallel via Direct HTTP.

    All tasks execute simultaneously (fan-out) and results are collected (fan-in).
    Use this when agents work independently (e.g., check infra health WHILE analyzing repo).

    Args:
        tasks_json: JSON array of task definitions to run concurrently.
            Each task has:
            - agent_id: Target agent (module1, module2, module3)
            - task: Task type to execute
            Example: [{"agent_id": "module1", "task": "health_check"},
                      {"agent_id": "module2", "task": "analyze_repository"}]

    Returns:
        JSON string with all agent results collected together
    """
    try:
        tasks = json.loads(tasks_json)
    except json.JSONDecodeError:
        return _wrap({"error": "Invalid JSON in task definitions"}, "run_parallel_fanout")

    results = _a2a.call_agents_parallel(tasks)

    return _wrap(
        {
            "pipeline_type": "parallel",
            "total_tasks": len(tasks),
            "results": results,
        },
        "run_parallel_fanout",
    )


# ---------------------------------------------------------------------------
# Tool 5: Synthesize Multi-Agent Results
# ---------------------------------------------------------------------------

@tool
def synthesize_results(results_json: str, original_request: str) -> str:
    """
    Synthesize results from multiple specialist agents into a unified response.

    Takes the outputs from different agents and produces a coherent summary
    that connects findings across agents.

    Args:
        results_json: JSON string with agent results to synthesize
        original_request: The original user request for context

    Returns:
        JSON string with synthesized findings, connections, and recommendations
    """
    try:
        results = json.loads(results_json)
    except json.JSONDecodeError:
        return _wrap({"error": "Invalid JSON in results"}, "synthesize_results")

    # Build synthesis from agent results
    agents_involved = []
    all_findings = []
    all_recommendations = []

    for result in results if isinstance(results, list) else [results]:
        agent = result.get("agent", "unknown")
        agents_involved.append(agent)

        data = result.get("data", {})

        # Extract findings based on agent type
        if agent == "module1":
            summary = data.get("environment_summary", {})
            all_findings.append(
                f"Infrastructure: {summary.get('healthy', 0)} healthy, "
                f"{summary.get('degraded', 0)} degraded services"
            )
            all_recommendations.extend(data.get("recommendations", []))

        elif agent == "module2":
            summary = data.get("summary", {})
            all_findings.append(
                f"Repository: {summary.get('total_applications', 0)} applications, "
                f"languages: {', '.join(summary.get('languages', []))}"
            )
            aws_services = summary.get("aws_services_needed", [])
            if aws_services:
                all_findings.append(f"AWS services needed: {', '.join(aws_services)}")

        elif agent == "module3":
            total = data.get("total_stacks", 0)
            score = data.get("evaluation_score", 0)
            all_findings.append(f"CDK Generation: {total} stacks, score {score}/100")

    synthesis = {
        "original_request": original_request,
        "agents_involved": agents_involved,
        "findings": all_findings,
        "recommendations": all_recommendations,
        "connections": _find_connections(results),
    }

    return _wrap(synthesis, "synthesize_results")


def _find_connections(results: Any) -> list[str]:
    """Find connections between agent results."""
    connections = []

    agent_ids = set()
    if isinstance(results, list):
        for r in results:
            agent_ids.add(r.get("agent", ""))

    if "module1" in agent_ids and "module2" in agent_ids:
        connections.append(
            "Infrastructure health issues may relate to repository code changes — "
            "compare degraded services with recent deployments"
        )

    if "module2" in agent_ids and "module3" in agent_ids:
        connections.append(
            "Repository analysis fed into CDK generation — "
            "generated stacks match identified AWS service requirements"
        )

    if "module1" in agent_ids and "module3" in agent_ids:
        connections.append(
            "Current infrastructure state can inform CDK improvements — "
            "fix degraded service configurations in generated code"
        )

    if not connections:
        connections.append("Single-agent task — no cross-agent connections")

    return connections


# ---------------------------------------------------------------------------
# Export all tools
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    call_infrastructure_agent,
    call_repository_agent,
    run_sequential_pipeline,
    run_parallel_fanout,
    synthesize_results,
]
