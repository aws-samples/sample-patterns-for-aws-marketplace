#!/usr/bin/env python3
"""
demos/module4_demo.py
=====================
Live workshop demonstration for Module 4: Multi-Agent Architectures.

Walks through orchestration patterns, communication protocols (Direct HTTP and MCP),
sequential/parallel execution, and multi-agent synthesis.

The orchestrator agent runs LIVE against Amazon Bedrock (Claude Sonnet 4).
Mock mode only affects sub-agent tool data — the LLM reasoning is always real.

USAGE
-----
  # Mock mode: sub-agent data is simulated, but LLM calls are real
  # Requires AWS credentials configured for Bedrock access
  AGENT_MOCK_MODE=true python demos/module4_demo.py

  # Run specific section
  AGENT_MOCK_MODE=true python demos/module4_demo.py --section 3

SECTIONS
--------
  1  Why orchestration?       — Single agents hit limits
  2  Orchestrator architecture — Hub-and-spoke topology
  3  Direct HTTP protocol     — Agent calls agent via HTTP REST
  4  MCP protocol             — Agent exposes/consumes tools via MCP
  5  Sequential orchestration — Repo analysis → CDK generation pipeline
  6  Parallel fan-out         — Query multiple agents simultaneously
  7  Shared context & handoff — Structured data flows between agents
  8  Error handling           — What happens when a sub-agent fails
  9  Full orchestrated workflow — End-to-end with all patterns
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.columns import Columns
    from rich.syntax import Syntax
    from rich.text import Text
    _c = Console()
    _RICH = True

    def header(text: str, color: str = "cyan") -> None:
        _c.rule(f"[bold {color}]{text}[/bold {color}]", style=color)

    def concept(text: str) -> None:
        _c.print(f"\n[bold yellow]💡 Module 4 Concept:[/bold yellow] [yellow]{text}[/yellow]")

    def user_says(text: str) -> None:
        _c.print(f"\n[bold green]USER ›[/bold green] [italic]{text}[/italic]")

    def box(title: str, body: str) -> None:
        _c.print(Panel(f"[dim]{body}[/dim]", title=f"[bold]{title}[/bold]", border_style="cyan"))

    def code_block(code: str, language: str = "python") -> None:
        syntax = Syntax(code, language, theme="monokai", line_numbers=False)
        _c.print(syntax)

    def info_list(title: str, items: list[tuple[str, str]], color: str = "cyan") -> None:
        """Render a titled list of key-value items using Rich."""
        _c.print(f"\n  [bold {color}]{title}[/bold {color}]")
        for label, desc in items:
            _c.print(f"    [bold]{label}[/bold] — {desc}")
        _c.print()

except ImportError:
    _RICH = False

    def header(text: str, color: str = "cyan") -> None:  # type: ignore[misc]
        print(f"\n{'═' * 62}\n  {text}\n{'═' * 62}")

    def concept(text: str) -> None:  # type: ignore[misc]
        print(f"\n💡 Concept: {text}")

    def user_says(text: str) -> None:  # type: ignore[misc]
        print(f"\nUSER › {text}")

    def box(title: str, body: str) -> None:  # type: ignore[misc]
        print(f"\n[ {title} ]\n{body}")

    def code_block(code: str, language: str = "python") -> None:  # type: ignore[misc]
        print(f"\n{code}\n")

    def info_list(title: str, items: list[tuple[str, str]], color: str = "cyan") -> None:  # type: ignore[misc]
        print(f"\n  {title}")
        for label, desc in items:
            print(f"    {label} — {desc}")
        print()


def pause(msg: str = "  ↵  Press Enter to continue...") -> None:
    try:
        input(msg)
    except KeyboardInterrupt:
        sys.exit(0)


def run_orchestrator(agent, query: str) -> str:
    """Run the orchestrator agent and return its final response."""
    result = agent.invoke({"messages": [("user", query)]})
    messages = result.get("messages", [])
    return messages[-1].content if messages else ""


# ---------------------------------------------------------------------------
# Section 1 — Why Orchestration?
# ---------------------------------------------------------------------------

def section_1_why_orchestration() -> None:
    header("SECTION 1 — Why Multi-Agent Orchestration?", "cyan")
    box(
        "The Problem: Single-Agent Limits",
        "In Modules 1-3, each agent was a specialist:\n"
        "  • Module 1: Observes infrastructure (read-only AWS)\n"
        "  • Module 2: Analyzes repositories (code scanning)\n"
        "  • Module 3: Generates CDK code (infrastructure-as-code)\n\n"
        "But real-world tasks span multiple domains:\n"
        '  "Analyze my repo, check what\'s running in AWS, and generate\n'
        '   CDK to fix the gaps."\n\n'
        "No single agent can handle this — we need orchestration.",
    )

    code_block("""# Single agent (Modules 1-3): one agent, one domain
agent = create_react_agent(model, infrastructure_tools)
agent.invoke({"messages": [("user", "Check ECS health")]})  # only infra

# Multi-agent (Module 4): orchestrator delegates to specialists
orchestrator = create_react_agent(model, [
    call_infrastructure_agent,   # → Module 1
    call_repository_agent,       # → Module 2
    mcp_generate_cdk,            # → Module 3
    run_parallel_fanout,         # → multiple agents at once
    synthesize_results,          # → combine outputs
])
orchestrator.invoke({"messages": [("user", "Analyze repo AND check infra")]})
""")

    box(
        "Single Agent (Modules 1-3)",
        "User → Agent → Tools → Response\n\n"
        "  ✓ Good for focused, single-domain tasks\n"
        "  ✗ Cannot combine capabilities across domains\n"
        "  ✗ No coordination between agents",
    )

    box(
        "Multi-Agent Orchestration (Module 4)",
        "User → Orchestrator → Agent 1 (infra)\n"
        "                    → Agent 2 (repo)    → Synthesis\n"
        "                    → Agent 3 (CDK)\n\n"
        "  ✓ Combines specialist capabilities\n"
        "  ✓ Sequential and parallel execution\n"
        "  ✓ Cross-domain reasoning and synthesis",
    )

    concept(
        "Multi-agent orchestration lets you compose specialist agents into workflows "
        "that no single agent could handle alone. The orchestrator decides WHAT to "
        "delegate, to WHOM, and in WHAT ORDER."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 2 — Orchestrator Architecture
# ---------------------------------------------------------------------------

def section_2_architecture() -> None:
    header("SECTION 2 — Orchestrator Architecture", "cyan")
    box(
        "Hub-and-Spoke Topology",
        "The orchestrator sits at the center. It has tools for calling\n"
        "each specialist agent, but does NO domain work itself.",
    )

    code_block("""# module4/agent.py — Orchestrator construction
from langgraph.prebuilt import create_react_agent
from module4.config.models import get_chat_bedrock_model
from module4.tools.orchestration_tools import ALL_TOOLS  # HTTP tools
from module4.protocols.mcp_protocol import MCP_TOOLS     # MCP tools

model = get_chat_bedrock_model(temperature=0.1)
all_tools = list(ALL_TOOLS) + list(MCP_TOOLS)  # 5 HTTP + 3 MCP = 8 tools

orchestrator = create_react_agent(model, all_tools, prompt=ORCHESTRATOR_PROMPT)
""")

    box(
        "Orchestrator Tools (8 total)",
        "HTTP Tools (Direct REST):          MCP Tools (tool protocol):\n"
        "  • call_infrastructure_agent      • mcp_analyze_requirements\n"
        "  • call_repository_agent          • mcp_generate_cdk\n"
        "  • run_sequential_pipeline        • mcp_validate_cdk\n"
        "  • run_parallel_fanout\n"
        "  • synthesize_results",
    )

    if _RICH:
        table = Table(title="Agent Communication", show_header=True, border_style="cyan")
        table.add_column("Protocol", style="bold")
        table.add_column("Agents", style="cyan")
        table.add_column("How it works")
        table.add_row("Direct HTTP", "Module 1, Module 2", "HTTP POST to agent REST endpoints")
        table.add_row("MCP", "Module 3", "Tool invocation via MCP server")
        _c.print(table)
    else:
        print("  Direct HTTP → Module 1 (port 8080), Module 2 (port 8081)")
        print("  MCP         → Module 3 (tool-based)")

    concept(
        "Two communication protocols, one orchestrator. Direct HTTP for agents that "
        "run as separate services (REST endpoints). MCP for agents that expose tools "
        "directly (function-level integration). Both patterns are common in "
        "production multi-agent systems."
    )

    box(
        "Framework Consistency: LangGraph Across Modules",
        "The orchestrator uses the SAME LangGraph create_react_agent as Modules 2 and 3.\n"
        "Same framework, same ReAct loop, same ChatBedrock model — different tools.\n\n"
        "  Module 2: create_react_agent(model, repo_tools)      → analyzes repos\n"
        "  Module 3: create_react_agent(model, cdk_tools)       → generates CDK\n"
        "  Module 4: create_react_agent(model, orchestr_tools)  → coordinates agents\n\n"
        "The LLM decides which tools to call. In Module 4, those tools happen to call\n"
        "other agents instead of AWS APIs or file systems. The orchestrator doesn't\n"
        "need special framework support — it's just a ReAct agent with delegation tools.",
    )

    concept(
        "This is the power of the agent abstraction: swap the tools and system prompt, "
        "and the same LangGraph agent becomes a specialist OR an orchestrator."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 3 — Direct HTTP Protocol Demo (live LLM)
# ---------------------------------------------------------------------------

def section_3_direct_http(agent) -> None:
    header("SECTION 3 — Direct HTTP (Agent-to-Agent via REST)", "green")
    box(
        "Direct HTTP: Agent-to-Agent Communication",
        "The orchestrator sends HTTP POST requests to agent endpoints.\n"
        "Each agent is a standalone service with its own API.\n\n"
        "This is the same underlying concept that Google's A2A protocol\n"
        "formalizes into a full spec (Agent Cards, JSON-RPC, task lifecycle).\n"
        "Here we use a simplified Direct HTTP approach to show the pattern.\n\n"
        "Pattern: Orchestrator → HTTP POST → Agent → JSON Response",
    )

    code_block("""# The LLM sees these tools and decides which to call based on the user's request

@tool
def call_infrastructure_agent(task: str, region: str = "us-east-1") -> str:
    \"\"\"Call Module 1 via HTTP POST to observe AWS infrastructure.\"\"\"
    result = http_client.call_agent("module1", task, region=region)
    return json.dumps(result)

@tool
def call_repository_agent(task: str, repo_path: str = "/repo") -> str:
    \"\"\"Call Module 2 via HTTP POST to analyze a code repository.\"\"\"
    result = http_client.call_agent("module2", task, repo_path=repo_path)
    return json.dumps(result)

# Under the hood, each tool sends: POST http://localhost:808x/{endpoint}
""")

    concept(
        "Watch the orchestrator reason about which HTTP tool to call. "
        "The LLM decides — we don't hardcode the routing."
    )

    q = "Check the health of my AWS infrastructure in us-east-1."
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "Direct HTTP is the simplest agent-to-agent protocol: POST with JSON. "
        "Each agent is independently deployable, scalable, and replaceable. "
        "The orchestrator only needs to know the endpoint URL and the API contract. "
        "Google's A2A protocol builds on this concept with standardized discovery, "
        "task lifecycle, and interoperability across vendors."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 4 — MCP Protocol Demo (live LLM)
# ---------------------------------------------------------------------------

def section_4_mcp_protocol(agent) -> None:
    header("SECTION 4 — MCP Protocol (Model Context Protocol)", "green")
    box(
        "MCP: Tool-Based Integration",
        "Instead of HTTP calls, the agent's capabilities are exposed as tools.\n"
        "The orchestrator discovers and invokes tools served by an MCP server.\n\n"
        "Pattern: Orchestrator → tool call → MCP Server → Agent logic → Result",
    )

    code_block("""# MCP tools — the orchestrator calls these like local functions
# The MCP server handles discovery and routing to Module 3

@tool
def mcp_generate_cdk(stack_type: str, parameters: str = "{}") -> str:
    \"\"\"Generate CDK stack code via MCP (Module 3).\"\"\"
    result = mcp_registry.invoke_tool("mcp_generate_cdk", {
        "stack_type": stack_type, "parameters": parameters,
    })
    return json.dumps(result)

# MCP tool discovery — the server advertises what's available
registry = MCPToolRegistry()
tools = registry.list_tools()  # → ['mcp_analyze_requirements', 'mcp_generate_cdk', ...]
""")

    if _RICH:
        table = Table(title="Direct HTTP vs MCP — Key Differences", border_style="cyan")
        table.add_column("", style="bold")
        table.add_column("Direct HTTP", style="green")
        table.add_column("MCP", style="blue")
        table.add_row("Communication", "HTTP POST to endpoint", "Tool invocation (function call)")
        table.add_row("Discovery", "Static URLs configured in advance", "Dynamic — server advertises tools")
        table.add_row("Coupling", "Loose — separate services", "Tighter — in orchestrator's context")
        table.add_row("Best for", "Independent agents, microservices", "Shared toolchains, embedded capabilities")
        _c.print(table)
    else:
        info_list("Direct HTTP vs MCP", [
            ("Direct HTTP", "HTTP POST, static URLs, loose coupling, microservice architectures"),
            ("MCP", "Tool invocation, dynamic discovery, tighter coupling, shared toolchains"),
        ])

    concept(
        "Watch the orchestrator use MCP tools (mcp_*) instead of Direct HTTP calls. "
        "The LLM sees both HTTP and MCP tools and chooses the right protocol."
    )

    q = "Generate a VPC CDK stack with 2 availability zones."
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "MCP provides automatic tool discovery — the orchestrator doesn't need to "
        "know agent URLs or API contracts. It asks the MCP server 'what tools do you "
        "have?' and gets back schemas it can call directly. This is how tools like "
        "Claude Code integrate with external services."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 5 — Sequential Orchestration (live LLM)
# ---------------------------------------------------------------------------

def section_5_sequential(agent, repo_path: str | None = None) -> None:
    header("SECTION 5 — Sequential Orchestration (Pipeline)", "blue")
    box(
        "Sequential Pipeline: Agent A → Agent B",
        "When Agent B needs Agent A's output, tasks must run in sequence.\n\n"
        "Example: Analyze repository (Module 2) → Generate CDK (Module 3)\n"
        "Module 3 NEEDS the repository analysis to know what to generate.",
    )

    code_block("""# Sequential pipeline tool — the LLM builds the pipeline definition
@tool
def run_sequential_pipeline(pipeline_json: str) -> str:
    \"\"\"Run agent tasks in sequence. Agent B gets Agent A's output.\"\"\"
    tasks = json.loads(pipeline_json)
    # Example: [{"agent_id": "module2", "task": "analyze_repository"},
    #           {"agent_id": "module3", "task": "generate_cdk"}]
    results = http_client.call_agents_sequential(tasks)
    return json.dumps({"pipeline_type": "sequential", "results": results})
""")

    info_list("Pipeline Steps", [
        ("Step 1: Module 2", "Analyze Repository → identify apps and dependencies"),
        ("Step 2: Module 3", "Generate CDK Code → using Module 2's output"),
        ("Step 3: Synthesize", "Combine results → unified response"),
    ], color="blue")

    _c.print("  [dim]Each step's output feeds the next step's input.[/dim]\n") if _RICH else print("  Each step's output feeds the next step's input.\n")

    concept(
        "The orchestrator must decide to call Module 2 FIRST via Direct HTTP, "
        "then feed that output to Module 3 via MCP. Watch the tool call sequence."
    )

    repo_ref = f"at {repo_path}" if repo_path else ""
    q = (
        f"Analyze the repository {repo_ref} to understand "
        "what applications and dependencies it has, then use those results to generate "
        "CDK infrastructure stacks for it."
    )
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "Sequential pipelines ensure data flows correctly between agents. "
        "Notice the protocol mix: Direct HTTP for Module 2, MCP for Module 3 (tool call). "
        "The orchestrator handles the protocol translation transparently."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 6 — Parallel Fan-Out (live LLM)
# ---------------------------------------------------------------------------

def section_6_parallel(agent, repo_path: str | None = None) -> None:
    header("SECTION 6 — Parallel Fan-Out / Fan-In", "blue")
    box(
        "Parallel Execution: Agent A + Agent B simultaneously",
        "When agents work independently, run them in parallel.\n\n"
        "Example: Check infrastructure health (Module 1) WHILE analyzing\n"
        "the repository (Module 2) — neither needs the other's output.",
    )

    code_block("""# Parallel fanout tool — independent tasks run simultaneously
@tool
def run_parallel_fanout(tasks_json: str) -> str:
    \"\"\"Run multiple agent tasks in parallel (fan-out/fan-in).\"\"\"
    tasks = json.loads(tasks_json)
    # Example: [{"agent_id": "module1", "task": "health_check"},
    #           {"agent_id": "module2", "task": "analyze_repository"}]
    results = http_client.call_agents_parallel(tasks)  # concurrent execution
    return json.dumps({"pipeline_type": "parallel", "results": results})
""")

    box(
        "Fan-Out / Fan-In Pattern",
        "               ┌─ Module 1 (Health Check) ─┐\n"
        "Orchestrator ──┤                            ├──→ Synthesize\n"
        "               └─ Module 2 (Repo Scan)    ─┘\n\n"
        "  ✓ Faster than sequential — total time ≈ slowest agent\n"
        "  ✓ Independent tasks don't block each other",
    )

    concept(
        "The orchestrator has a run_parallel_fanout tool that dispatches "
        "multiple agent calls simultaneously. Watch it choose this tool."
    )

    repo_ref = f"the repository at {repo_path}" if repo_path else "my repository"
    q = (
        "I need two things done at the same time: check the health of my AWS "
        f"infrastructure in us-east-1, and also analyze {repo_ref}. "
        "These are independent — run them in parallel and give me combined results."
    )
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "Parallel fan-out is the key performance optimization in multi-agent systems. "
        "If two agents don't depend on each other, run them simultaneously. "
        "Total latency equals the SLOWEST agent, not the SUM of all agents."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 7 — Shared Context & Handoff
# ---------------------------------------------------------------------------

def section_7_context_handoff() -> None:
    header("SECTION 7 — Shared Context & Agent Handoff", "magenta")
    box(
        "How Data Flows Between Agents",
        "The biggest challenge in multi-agent systems: how does Agent B\n"
        "get the context it needs from Agent A?\n\n"
        "Three patterns:\n"
        "  1. Direct passthrough — orchestrator forwards output as input\n"
        "  2. Structured handoff — transform output to match next agent's schema\n"
        "  3. Shared state — agents read/write to a common state store",
    )

    if _RICH:
        table = Table(title="Context Handoff Patterns", border_style="magenta")
        table.add_column("Pattern", style="bold")
        table.add_column("How it works")
        table.add_column("Trade-off", style="dim")
        table.add_row(
            "1. Direct Passthrough",
            "Module 2 output → [raw JSON] → Module 3 input",
            "Simple but fragile — formats must match",
        )
        table.add_row(
            "2. Structured Handoff",
            "Module 2 output → [Orchestrator transforms] → Module 3",
            "Module 4's approach — orchestrator maps fields",
        )
        table.add_row(
            "3. Shared State Store",
            "Module 2 → writes → [State Store] → reads → Module 3",
            "Decoupled but adds infrastructure",
        )
        _c.print(table)
    else:
        info_list("Context Handoff Patterns", [
            ("Direct Passthrough", "Raw JSON forwarded — simple but fragile"),
            ("Structured Handoff", "Orchestrator transforms data — Module 4's approach"),
            ("Shared State Store", "Agents read/write to common store — decoupled"),
        ])

    code_block("""# Structured handoff — orchestrator transforms between agent formats

# Module 2 output (repository analysis)
module2_output = {"applications": [{"aws_requirements": {"compute": "ECS", ...}}]}

# Orchestrator extracts and reshapes for Module 3
module3_input = {
    "requirements": module2_output["applications"][0]["aws_requirements"],
    "region": "us-east-1",
    "environment": "production",
}

# Module 3 receives clean, structured input it can act on
mcp_registry.invoke_tool("mcp_analyze_requirements", module3_input)
""")

    print("\n  [Demo] Structured Handoff — Module 2 → Orchestrator → Module 3\n")

    # Simulate Module 2 output
    module2_output = {
        "applications": [
            {
                "name": "api-service",
                "aws_requirements": {
                    "compute": "ECS Fargate",
                    "database": "RDS PostgreSQL",
                    "cache": "ElastiCache Redis",
                },
            },
        ],
        "summary": {
            "aws_services_needed": ["ECS", "RDS", "ElastiCache", "VPC"],
        },
    }

    print("  Step 1: Module 2 produces repository analysis")
    print(f"    Output: {json.dumps(module2_output['summary'], indent=2)}")

    # Orchestrator transforms for Module 3
    module3_input = {
        "requirements": module2_output["applications"][0]["aws_requirements"],
        "region": "us-east-1",
        "environment": "production",
    }

    print(f"\n  Step 2: Orchestrator transforms for Module 3")
    print(f"    Mapped: {json.dumps(module3_input, indent=2)}")

    # Module 3 receives structured input
    print(f"\n  Step 3: Module 3 receives structured requirements")
    print(f"    Ready to generate: VpcStack, RdsStack, ElastiCacheStack, EcsStack")

    concept(
        "The orchestrator acts as a translator between agents. It understands both "
        "agents' data formats and maps between them. This is why the orchestrator "
        "needs domain awareness — not to do the work, but to connect the dots."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 8 — Error Handling & Fallbacks (live LLM)
# ---------------------------------------------------------------------------

def section_8_error_handling(agent) -> None:
    header("SECTION 8 — Error Handling & Fallbacks", "red")
    box(
        "What Happens When a Sub-Agent Fails?",
        "In multi-agent systems, individual agents can fail:\n"
        "  • Agent service is down (HTTP timeout)\n"
        "  • Agent returns an error (bad input, internal error)\n"
        "  • Agent response is low quality (confidence below threshold)\n\n"
        "The orchestrator must handle these gracefully.",
    )

    code_block("""# HTTP client catches all errors — orchestrator gets data, not exceptions
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        return {"agent": agent_id, "data": json.loads(resp.read())}
except Exception as e:
    # Connection refused, timeout, server crash — all handled
    return {"agent": agent_id, "data": {"error": str(e)}}

# The LLM sees the error in the tool response and reasons about it:
# "Module 2 returned an error. I'll report what succeeded and what failed."
""")

    info_list("Error Handling Strategies", [
        ("1. RETRY", "Transient failures (timeouts, rate limits) → exponential backoff"),
        ("2. FALLBACK", "Agent unavailable → use cached results or skip non-critical agent"),
        ("3. DEGRADE", "Partial results available → return what we have, flag missing pieces"),
        ("4. ESCALATE", "Critical failure → report error to user, suggest manual action"),
    ], color="red")

    concept(
        "Watch how the orchestrator handles a request for a task that doesn't exist "
        "on one of the sub-agents. It should report what succeeded and what failed."
    )

    q = (
        "Check the health of my infrastructure in us-east-1. Also try to run a "
        "'deployment_status' check on the repository agent — I know that task "
        "might not be available yet. Tell me what worked and what didn't."
    )
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "Graceful degradation is essential in multi-agent systems. Unlike monolithic "
        "agents, orchestrators can return partial results and clearly communicate "
        "what's missing. The user gets value immediately rather than a total failure."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 9 — Full Orchestrated Workflow (live LLM)
# ---------------------------------------------------------------------------

def section_9_full_workflow(agent, repo_path: str | None = None) -> None:
    header("SECTION 9 — Complete Orchestrated Workflow", "cyan")
    box(
        "End-to-End: All Patterns Combined",
        "USER REQUEST\n"
        "  ↓\n"
        "ORCHESTRATOR (decompose, route, execute, synthesize)\n"
        "  ├── PARALLEL: Module 1 health check + Module 2 repo analysis\n"
        "  ├── SEQUENTIAL: Module 2 output → Module 3 CDK generation\n"
        "  └── SYNTHESIS: Combine all results\n"
        "  ↓\n"
        "UNIFIED RESPONSE",
    )

    concept(
        "This is the full demo. The orchestrator receives a complex request, "
        "decomposes it, calls multiple agents via Direct HTTP and MCP, and synthesizes "
        "the results. All reasoning is live through Bedrock."
    )

    repo_ref = f"the repository at {repo_path}" if repo_path else "my repository"
    q = (
        "I need a full assessment of my environment. First, check the health of my "
        f"AWS infrastructure in us-east-1 and analyze {repo_ref} at the same time. "
        "Then, based on the repository analysis, generate CDK infrastructure stacks "
        "for any services the repo needs. Finally, synthesize all the findings into "
        "a summary with recommendations."
    )
    user_says(q)
    print()
    response = run_orchestrator(agent, q)
    print(f"\n  AGENT › {response}\n")

    concept(
        "This is the power of multi-agent orchestration: parallel execution for speed, "
        "sequential pipelines for data dependencies, protocol flexibility (HTTP + MCP), "
        "and cross-agent synthesis that no single agent could produce. The orchestrator "
        "wrote zero infrastructure code and checked zero AWS APIs — it only coordinated."
    )
    pause()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Module 4 Workshop Demo")
    parser.add_argument("--section", "-s", type=int, choices=range(1, 10), metavar="1-9")
    parser.add_argument("--repo", type=str, help="Path to repository for live analysis (e.g., ~/repos/my-app)")
    args = parser.parse_args()

    # Resolve repo path for sections that need it
    repo_path = os.path.expanduser(args.repo) if args.repo else None

    os.environ.setdefault("AGENT_MOCK_MODE", "true")
    mock_on = os.environ.get("AGENT_MOCK_MODE", "true").lower() == "true"
    if mock_on:
        print("  Mock mode ON  (sub-agent data simulated, LLM calls are live via Bedrock)\n")
    else:
        print("  Live mode ON  (calling real agent servers on localhost)\n")

    from module4.agent import create_orchestrator

    agent = create_orchestrator(verbose=True)

    header("MODULE 4 DEMO — MULTI-AGENT ARCHITECTURES", "bold cyan")
    print("""
  Use case: DevOps Engineer orchestrating multiple specialist agents
  to analyze infrastructure, scan repositories, and generate CDK code
  in a single coordinated workflow.

  This demo covers:
    • Why multi-agent orchestration matters
    • Direct HTTP protocol (agent-to-agent communication)
    • MCP protocol (tool-based integration)
    • Sequential pipelines and parallel fan-out
    • Shared context and agent handoff
    • Error handling and graceful degradation
    • Full orchestrated workflow combining all patterns
""")
    pause("  ↵  Press Enter to begin...")

    sections = {
        1: section_1_why_orchestration,
        2: section_2_architecture,
        3: lambda: section_3_direct_http(agent),
        4: lambda: section_4_mcp_protocol(agent),
        5: lambda: section_5_sequential(agent, repo_path),
        6: lambda: section_6_parallel(agent, repo_path),
        7: section_7_context_handoff,
        8: lambda: section_8_error_handling(agent),
        9: lambda: section_9_full_workflow(agent, repo_path),
    }

    if args.section:
        sections[args.section]()
    else:
        for fn in sections.values():
            fn()

    header("DEMO COMPLETE", "bold green")
    print("""
  ✅ You've seen:
     • Why single agents need orchestration for complex tasks
     • Hub-and-spoke orchestrator architecture
     • Direct HTTP — agent-to-agent communication (live LLM)
     • MCP protocol — tool-based integration via MCP servers (live LLM)
     • Sequential pipelines — data flows from Agent A to Agent B
     • Parallel fan-out — independent agents run simultaneously
     • Structured handoff — orchestrator translates between agents
     • Error handling — graceful degradation with partial results
     • Full workflow — all patterns combined end-to-end

  Key Takeaways:
     • Orchestrators delegate — they never do domain work
     • Direct HTTP for loose coupling, MCP for tool integration
     • Parallel when independent, sequential when dependent
     • Always plan for partial failure

  Thank you for completing Module 4!
""")


if __name__ == "__main__":
    main()
