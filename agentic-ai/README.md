# AI Agent Learning Series on AWS

Hands-on demonstration code for the **AI Agent Learning Series** workshop sessions.

**Use case:** An AWS Infrastructure Engineer is building an agentic system that can provision infrastructure, deploy and build microservices, and observe those services running in AWS.

This repository contains multiple modules demonstrating different agent frameworks and patterns:
- **Module 1**: AWS Strands-based Infrastructure Agent (observe and analyze AWS resources)
- **Module 2**: LangChain-based Repository Analysis Agent (analyze git repos for deployment planning)
- **Module 3**: CDK Generation Agent with Evaluation & Routing (generate infrastructure code with quality assurance)

Future modules will add multi-agent orchestration, long-term memory, and full autonomy.

---

## Modules Overview

### Module 1: AWS Infrastructure Agent (Strands Framework)

Observes and analyzes AWS infrastructure using AWS Strands framework.

**Key Concepts:**
- Three Layers (Reasoning / Orchestration / Tools)
- Think → Act → Observe loop with `LoopObserver`
- Context window / short-term memory
- Human-in-the-loop pattern
- Model-agnostic architecture

**Tools:** 5 read-only AWS tools (ECS, EC2, RDS, Lambda)

[See module1/README.md for details](module1/)

### Module 2: Repository Analysis Agent (LangChain Framework)

Analyzes git repositories to identify applications and AWS infrastructure requirements using LangChain + LangGraph.

**Key Concepts:**
- LangChain `ChatBedrock` model interface
- `AgentExecutor` and LangGraph state machines
- Repository scanning and dependency analysis
- AWS service mapping from dependencies
- LangSmith tracing for observability

**Tools:** 5 repository analysis tools (scan, detect, analyze, map)

[See module2/README.md for details](module2/)

### Module 3: CDK Generation Agent with Evaluation (LangChain Framework)

Generates AWS CDK infrastructure code from requirements with comprehensive evaluation and quality assurance using LangChain + LangGraph.

**Key Concepts:**
- CDK infrastructure code generation
- LLM-as-judge evaluation pattern
- Automated evaluation pipelines
- ISV integrations (Patronus AI, Deepchecks, Comet ML)
- Routing agent for intent classification
- Self-correction pattern

**Tools:** 5 CDK generation tools (analyze, generate, validate, list, test)

**Additional Components:**
- **Routing Agent**: Intent classification and request routing
- **Evaluation System**: Automated quality assessment for Module 2 & 3
- **ISV Integrations**: Patronus AI, Deepchecks, Comet ML

[See module3/README.md for details](module3/)

---

## Project Structure

```
infra-agent/
├── module1/                    # AWS Infrastructure Agent (Strands)
│   ├── agent.py               # Core agent with three layers
│   ├── app.py                 # AgentCore Runtime entrypoint
│   ├── config/models.py       # Anthropic + Hugging Face configs
│   └── tools/aws_tools.py     # 5 read-only AWS tools
│
├── module2/                    # Repository Analysis Agent (LangChain)
│   ├── agent.py               # LangChain agent factory
│   ├── app.py                 # HTTP server entrypoint
│   ├── config/models.py       # ChatBedrock configuration
│   ├── tools/repo_tools.py    # 5 repository analysis tools
│   ├── workflows/             # LangGraph state machine
│   └── prompts/               # System prompts
│
├── demos/
│   ├── module1_demo.py        # Module 1 workshop demo (6 sections)
│   └── module2_demo.py        # Module 2 workshop demo (6 sections)
│
├── tests/
│   ├── test_tools.py          # Module 1 tests
│   ├── test_repo_tools.py     # Module 2 tests
│   └── fixtures/              # Test repository fixtures
│
└── requirements.txt           # Dependencies for both modules
```

---

## Quick Start

### Setup

```bash
# 1. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Module 1: AWS Infrastructure Agent

```bash
# Run demo in mock mode (no AWS account needed)
AGENT_MOCK_AWS=true python demos/module1_demo.py

# Run specific section (1-6)
AGENT_MOCK_AWS=true python demos/module1_demo.py --section 4

# Run tests
AGENT_MOCK_AWS=true pytest tests/test_tools.py -v
```

### Module 2: Repository Analysis Agent

```bash
# Run demo in mock mode (no real repository needed)
AGENT_MOCK_REPO=true python demos/module2_demo.py

# Run specific section (1-11)
AGENT_MOCK_REPO=true python demos/module2_demo.py --section 5

# Run tests
AGENT_MOCK_REPO=true pytest tests/test_repo_tools.py -v
```

### Module 3: CDK Generation Agent with Evaluation

```bash
# Run demo in mock mode (no AWS account or API keys needed)
AGENT_MOCK_REPO=true python demos/module3_demo.py

# Run specific section (1-11)
AGENT_MOCK_REPO=true python demos/module3_demo.py --section 6

# Run Module 3 evaluation pipeline
AGENT_MOCK_REPO=true python -c "
from evaluation.pipelines.module3_eval import run_module3_evaluation
results = run_module3_evaluation(verbose=True)
print(f'Average Score: {results[\"summary\"][\"average_combined_score\"]:.1f}/100')
"

# Run tests
AGENT_MOCK_REPO=true pytest tests/test_module3_tools.py -v
AGENT_MOCK_REPO=true pytest tests/test_routing_agent.py -v
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py -v
```

### Routing Agent

```bash
# Start routing agent server
python routing-agent/app.py

# Classify a request
curl -X POST http://localhost:8083/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Analyze my repository at /home/user/app"}'

# Run tests
AGENT_MOCK_REPO=true pytest tests/test_repo_tools.py -v

# Start HTTP server
python module2/app.py
```

---

## Live AWS Mode

### Prerequisites

**Anthropic (Claude Sonnet 4 via Amazon Bedrock)**

1. AWS account with credentials configured (`aws configure` or `AWS_*` env vars)
2. Enable model access: *AWS Console → Amazon Bedrock → Model Access → Enable Anthropic models*
3. No subscription needed — pay per token

```bash
# Run against real AWS
python demos/module1_demo.py --live
```

**Hugging Face (via Amazon Bedrock Marketplace)**

1. *AWS Console → Amazon Bedrock → Model Catalog → Filter by "Hugging Face"*
2. Select a model (e.g. **Mistral-7B-Instruct** — public model, no subscription fee)
3. Click **Deploy** → select instance → wait for *"In service"*
4. Copy the SageMaker endpoint ARN from the deployment details page
5. Set: `export HF_ENDPOINT_ARN="arn:aws:sagemaker:..."`

```bash
# Run with Hugging Face model (same agent, different reasoning engine)
python demos/module1_demo.py --live --hf
```

> Guide: https://huggingface.co/blog/bedrock-marketplace

---

## Deploying to AgentCore Runtime

```bash
# 1. Install the CLI
pip install bedrock-agentcore-starter-toolkit

# 2. Configure (run once — prompts for settings)
agentcore configure --entrypoint app.py --disable-memory

# 3. Test locally (no Docker needed)
AGENT_MOCK_AWS=true python app.py
# → Serves on http://localhost:8080/invocations

# 4. Test the local server
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Give me a health summary of us-east-1"}'

# 5. Deploy to AWS (CodeBuild, no Docker needed)
agentcore launch

# 6. Invoke the deployed agent
agentcore invoke '{"prompt": "List ECS services in us-east-1"}'

# 7. Invoke via boto3 (for automation / integration)
export AGENTCORE_ARN="arn:aws:bedrock-agentcore:..."
python scripts/invoke_agentcore.py --prompt "Health check us-east-1"
python scripts/invoke_agentcore.py --repl   # interactive mode
```

---

## Tools Reference

All Module 1 tools are **read-only**. The only action path is `request_human_review`.

| Tool | Purpose | Slide Concept |
|---|---|---|
| `list_aws_resources(service_type, region)` | ECS / EC2 / RDS / Lambda listings | Grounding: agent sees current state |
| `describe_resource(service_type, name, region)` | Detailed drill-down | Multi-step reasoning |
| `check_resource_health(service_type, name, region)` | Structured health verdict | Observation |
| `get_environment_summary(region)` | Cross-service overview | Data synthesis |
| `request_human_review(...)` | Escalation ticket | Human-in-the-loop |

### Mock data

With `AGENT_MOCK_AWS=true` the tools return realistic simulated data including:
- **`api-gateway-svc`** → healthy (3/3 tasks running)
- **`notification-svc`** → degraded (1/2 tasks, EssentialContainerExited event) ← triggers HITL
- **`reporting-mysql`** → degraded (Single-AZ RDS, no failover)
- **`prod-postgres-01`** → healthy (Multi-AZ, available)

---

## The Model-Agnostic Property

The most important architectural property to highlight in the workshop:

```python
# config/models.py

# Anthropic — Claude Sonnet 4 via Amazon Bedrock
model = get_bedrock_model()

# Hugging Face — open model via Bedrock Marketplace (ONE LINE change)
model = get_hf_bedrock_model(endpoint_arn="arn:aws:sagemaker:...")
```

The `create_agent()` factory in `agent.py` accepts `hf_endpoint_arn` and swaps the model. **Tools, system prompt, conversation manager, and AgentCore wrapper are completely unchanged.**

---

## Multi-Agent Architecture (Future)

The two agents are designed to work together in a multi-agent workflow:

```
┌─────────────────────────────────────────────────────────────┐
│  USER REQUEST: "Deploy this repository to AWS"             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (Module 4)                                    │
│  Coordinates both agents to complete the task               │
└─────────────────────────────────────────────────────────────┘
         ↓                                    ↓
┌──────────────────────┐          ┌──────────────────────────┐
│  MODULE 2 AGENT      │          │  MODULE 1 AGENT          │
│  (Repository)        │          │  (Infrastructure)        │
│                      │          │                          │
│  Analyzes repo:      │          │  Checks AWS:             │
│  • Apps detected     │   →→→    │  • Existing resources    │
│  • Stacks identified │          │  • Health status         │
│  • AWS needs mapped  │   ←←←    │  • Gaps identified       │
└──────────────────────┘          └──────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  DEPLOYMENT PLAN                                            │
│  • Infrastructure to provision (CDK/Terraform)              │
│  • Services to deploy (ECS/Lambda)                          │
│  • Monitoring to configure (CloudWatch)                     │
└─────────────────────────────────────────────────────────────┘
```

**Example Workflow:**
1. Module 2 analyzes repository → identifies Node.js app needing PostgreSQL + Redis
2. Module 1 checks AWS → finds existing RDS PostgreSQL, no Redis
3. Orchestrator generates plan → provision ElastiCache, deploy app to ECS
4. Human reviews and approves → infrastructure provisioned, app deployed

## What's Scoped Out (Future Modules)

| Capability | Module |
|---|---|
| Evaluation and routing patterns | Module 3 |
| Multi-agent supervisor pattern | Module 4 |
| Long-term memory (DynamoDB / vector store) | Module 7 |
| RAG / Knowledge Base | Module 10 |
| Production IAM hardening | Module 8 |
| CloudWatch / X-Ray tracing | Module 12 |

---

## Demo Sections

Run `AGENT_MOCK_AWS=true python demos/module1_demo.py --section N`:

| # | Title | Key Concept |
|---|---|---|
| 1 | Architecture anatomy | Three layers in code |
| 2 | The loop | Think → Act → Observe, live |
| 3 | Multi-step reasoning | Compound query, multiple tool calls |
| 4 | Human-in-the-loop | Agent escalates, doesn't act |
| 5 | Model swap | Anthropic ↔ Hugging Face |
| 6 | Context window | Multi-turn short-term memory |
