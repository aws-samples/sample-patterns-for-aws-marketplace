# Module 4: Multi-Agent Architectures

Orchestrator agent that coordinates specialist agents (Modules 1-3) using Direct HTTP and MCP communication protocols.

## Overview

Module 4 demonstrates **multi-agent orchestration** — how to compose specialist agents into workflows that no single agent could handle alone. The orchestrator delegates tasks, manages execution order, and synthesizes results across agents.

## What This Module Covers

1. **Orchestrator Pattern** — Hub-and-spoke topology where a central agent coordinates specialists
2. **Direct HTTP Protocol** — Agent-to-agent communication via HTTP REST (Modules 1 & 2). This is the same underlying concept that Google's A2A protocol formalizes into a full specification.
3. **MCP Protocol** — Model Context Protocol tool-based integration (Module 3)
4. **Sequential Pipelines** — Agent A output feeds Agent B input
5. **Parallel Fan-Out** — Independent agents run simultaneously
6. **Context Handoff** — Structured data transformation between agents
7. **Error Handling** — Graceful degradation when sub-agents fail

## Quick Start

### Setup

```bash
cd agentic-ai/module4
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run in Mock Mode (sub-agent data simulated, LLM calls are live)

```bash
cd agentic-ai
source module4/.venv/bin/activate
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
AGENT_MOCK_MODE=true python demos/module4_demo.py

# Or run a specific section (1-9)
AGENT_MOCK_MODE=true python demos/module4_demo.py --section 3
```

### Run in Live Mode (all agents running as servers)

```bash
# Terminal 1 — Module 1 (Infrastructure Agent)
cd agentic-ai
source module4/.venv/bin/activate
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
AGENT_MOCK_AWS=true python -m module1.app

# Terminal 2 — Module 2 (Repository Agent)
source module4/.venv/bin/activate
AGENT_MOCK_REPO=true python -m module2.app

# Terminal 3 — Module 3 (CDK Generation Agent)
source module4/.venv/bin/activate
AGENT_MOCK_REPO=true python -m module3.app

# Terminal 4 — Module 4 (Orchestrator)
source module4/.venv/bin/activate
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
python demos/module4_demo.py
```

> **Note:** `AGENT_MOCK_AWS` and `AGENT_MOCK_REPO` mock the tool data (AWS resources,
> repo contents) but all modules still make real LLM calls to Amazon Bedrock.
> Remove these flags to query real AWS infrastructure and scan real repositories.

## Architecture

### Hub-and-Spoke Orchestrator

```
                    ┌────────────────────────────────┐
                    │  ORCHESTRATOR (Module 4)        │
                    │                                  │
                    │  LangGraph ReAct Agent           │
                    │  Claude Sonnet 4 via Bedrock     │
                    │                                  │
                    │  HTTP Tools:       MCP Tools:    │
                    │   • call_infra      • mcp_analyze│
                    │   • call_repo       • mcp_gen_cdk│
                    │   • sequential      • mcp_valid  │
                    │   • parallel                     │
                    │   • synthesize                   │
                    └──────────┬───────────┬───────────┘
                               │           │
                  Direct HTTP  │           │ MCP (tools)
                 ┌─────────────┤           │
                 │             │           │
          ┌──────┴──┐   ┌─────┴───┐   ┌───┴───────┐
          │Module 1  │   │Module 2  │   │ Module 3   │
          │Infra     │   │Repo      │   │ CDK Gen    │
          │Agent     │   │Agent     │   │ Agent      │
          │port 8080 │   │port 8081 │   │ MCP Server │
          └──────────┘   └──────────┘   └────────────┘
```

### Communication Protocols

| Protocol | Used For | How It Works | Best For |
|----------|----------|-------------|----------|
| **Direct HTTP** | Modules 1 & 2 | HTTP POST to agent endpoints | Independent services, loose coupling |
| **MCP** | Module 3 | Tool invocation via MCP server | Shared toolchains, tight integration |

> **Note on Google A2A:** Our Direct HTTP approach uses the same underlying concept as
> Google's Agent-to-Agent (A2A) protocol — agents communicate over HTTP with structured
> JSON. The full A2A spec adds standardized Agent Cards (capability discovery), JSON-RPC
> message format, task lifecycle management, and cross-vendor interoperability.

## Usage

### Python API

```python
from module4.agent import create_orchestrator, orchestrate_request

# Create orchestrator
orchestrator = create_orchestrator(verbose=True)
result = orchestrator.invoke({
    "messages": [("user", "Analyze my repo and generate infrastructure")]
})
print(result["messages"][-1].content)

# Convenience function
results = orchestrate_request(
    "Check infrastructure health and analyze my repository"
)
print(results["output"])
```

### Direct HTTP Protocol

```python
from module4.protocols.a2a_protocol import A2AClient

client = A2AClient(verbose=True)

# Call individual agents
infra = client.call_agent("module1", "health_check", region="us-east-1")
repo = client.call_agent("module2", "analyze_repository")

# Sequential pipeline
results = client.call_agents_sequential([
    {"agent_id": "module2", "task": "analyze_repository"},
    {"agent_id": "module3", "task": "generate_cdk"},
])

# Parallel fan-out
results = client.call_agents_parallel([
    {"agent_id": "module1", "task": "health_check"},
    {"agent_id": "module2", "task": "analyze_repository"},
])
```

### MCP Protocol

```python
from module4.protocols.mcp_protocol import MCPToolRegistry

registry = MCPToolRegistry(verbose=True)

# Discover available tools
tools = registry.list_tools()
for t in tools:
    print(f"{t['name']}: {t['description']}")

# Invoke a tool
result = registry.invoke_tool("mcp_generate_cdk", {
    "stack_type": "vpc",
    "parameters": '{"max_azs": 2}',
})
```

### HTTP Server

```bash
# Start orchestrator server
python module4/app.py

# Orchestrate a request
curl -X POST http://localhost:8084/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"request": "Analyze my repo and check infrastructure health"}'
```

## Project Structure

```
module4/
├── agent.py              # Orchestrator agent factory
├── app.py                # HTTP server (port 8084)
├── .venv/                # Self-contained Python virtual environment
├── config/
│   └── models.py         # ChatBedrock configuration
├── tools/
│   └── orchestration_tools.py  # HTTP tools for agent coordination
├── protocols/
│   ├── a2a_protocol.py   # Direct HTTP agent-to-agent communication
│   └── mcp_protocol.py   # MCP tool-based integration
├── prompts/
│   └── system_prompts.py # Orchestrator system prompt
├── mock/
│   └── agent_mocks.py    # Mock responses from Modules 1-3
└── README.md
```

## Demo Sections

Run `AGENT_MOCK_MODE=true python demos/module4_demo.py --section N`:

| # | Title | Key Concept |
|---|-------|-------------|
| 1 | Why orchestration? | Single agents hit limits |
| 2 | Orchestrator architecture | Hub-and-spoke topology |
| 3 | Direct HTTP protocol | HTTP-based agent-to-agent |
| 4 | MCP protocol | Tool-based integration |
| 5 | Sequential orchestration | Pipeline: Agent A → Agent B |
| 6 | Parallel fan-out | Independent agents run simultaneously |
| 7 | Shared context & handoff | Data transformation between agents |
| 8 | Error handling | Graceful degradation |
| 9 | Full workflow | All patterns combined end-to-end |

## Key Concepts

### Direct HTTP vs MCP

**Direct HTTP (agent-to-agent):**
- Communication via HTTP POST
- Agents are standalone services with their own URLs
- Loose coupling — agents can be replaced independently
- Discovery is static (configured URLs)
- Same concept as Google A2A, without the full spec

**MCP (Model Context Protocol):**
- Communication via tool invocation
- Agent capabilities exposed as callable tools
- Tighter integration — tools run in orchestrator's context
- Dynamic discovery — MCP server advertises available tools

### Orchestration Patterns

**Sequential:** When Agent B needs Agent A's output
```
Module 2 (analyze repo) → Module 3 (generate CDK)
```

**Parallel:** When agents work independently
```
Module 1 (health check) ‖ Module 2 (analyze repo)
```

**Mixed:** Combine both in a single workflow
```
Phase 1 (parallel): Module 1 + Module 2
Phase 2 (sequential): Module 2 output → Module 3
Phase 3: Synthesize all results
```

## Next Steps

- **Google A2A**: Implement the full A2A specification (Agent Cards, JSON-RPC, task lifecycle) for production cross-vendor interoperability
- **Module 7**: Long-term memory with DynamoDB and vector stores
- **Module 12**: Production monitoring with CloudWatch and X-Ray

## License

Part of the AI Agent Learning Series on AWS.
