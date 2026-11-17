# AI Agent Learning Series on AWS

Hands-on demonstration code for the **AI Agent Learning Series** workshop sessions.

**Use case:** An AWS Infrastructure Engineer is building an agentic system that can provision infrastructure, deploy and build microservices, and observe those services running in AWS.

This repository contains multiple modules demonstrating different agent frameworks and patterns:

| Module | Focus | Framework | Featured partners |
| --- | --- | --- | --- |
| **1** | Infrastructure Agent: observe and analyze AWS resources | AWS Strands | AWS only |
| **2** | Repository Analysis Agent: analyze git repos for deployment planning | LangChain | AWS only |
| **3** | CDK Generation Agent with evaluation and routing | LangChain | Comet ML, Deepchecks, Patronus AI |
| **4** | Multi-agent orchestration: supervisor pattern, MCP and A2A protocols | LangGraph | AWS only |
| **5** | Domain-specific agents: the Domain Adaptation Engine | LangGraph | AWS only |
| **6** | Durable orchestration and long-running workflows | Temporal | Temporal |
| **7** | Agent memory systems: session, semantic, and relationship memory | LangGraph | Redis Cloud, MongoDB Atlas, Neo4j Aura |
| **8** | Agent identity and access management | Python (Auth0 device flow, JWKS, MCP); no agent framework | Auth0, CyberArk |
| **9** | Data pipelines and lineage: governed, fresh, traceable knowledge | LangGraph | Confluent Cloud, Databricks |
| **10** | Agent exposure, capability rollout, model routing, and trace inspection | OpenAI SDK (Responses API) on Amazon Bedrock; Strands adapter for hosted-partner live mode | LaunchDarkly, Portkey AI, Logz.io |
| **11** | MLOps and the agent development lifecycle: versioned, gated, progressively delivered releases | OpenAI SDK on Bedrock (Module 10 loop), Pulumi | GitLab, Vercel |
| **12** | Security posture, deterministic policy enforcement, and behavioral investigation for agent workflows | Amazon Bedrock AgentCore, Pulumi, OpenTelemetry | Snyk, Honeycomb |

Partner integrations run as in-process mocks, so you need no partner accounts
to run any module standalone. Demos that use an LLM still call Amazon Bedrock
with your AWS credentials, even in mock mode. See each module's `README.md` for
its own quick start and live partner setup. Module 11 is the exception by
design: it is live-only, because its subject is a real release on AWS. Without
accounts, you can still run its offline tests and replay a real run with
`--replay-fixtures`.

| Demo | Without AWS credentials | Notes |
| --- | --- | --- |
| Module 6, Module 8, Module 10 `--mode mock` | Runs fully offline | No Bedrock calls |
| Module 5, Module 9 | Degrades gracefully | Sections that call Bedrock report the failure and the demo continues |
| Modules 1, 2, 4 and 7, Module 10 `--mode local` | Needs Bedrock | The agent itself is the LLM loop |
| Module 3 | Needs Bedrock for Section 9 | Sections 1-8 run offline (template CDK generation, mock judges); Section 9 makes a live routing call |
| Module 11 | Live only: AWS, GitLab, Vercel | Offline: `pytest tests/test_module11_*.py`, and `python demos/module11_demo.py --replay-fixtures` (committed, redacted captures of a real run, under a REPLAY banner) |
| Module 12 | Runs fully offline by default | Pass `--stack module12-demo` for the deployed AgentCore Runtime, posture controller, and DynamoDB evidence |

---

## Environments

The modules pin different dependency sets, so they install into five
environment families. `./INSTALL.sh <family>` creates the venv, checks the
Python version and prints the next commands; `python verify_installation.py`
checks the family you are in. Run every command from `agentic-ai/`.

| Family | Modules | Python | Venv | Install | Tests (offline) |
| --- | --- | --- | --- | --- | --- |
| `core` | 1-3, 5, 6, 8, 9, routing agent, evaluation, orchestration | 3.12 | `.venv` | `./INSTALL.sh` | `tests/test_tools.py`, `test_repo_tools.py`, `test_module3_*.py`, `test_routing_agent.py`, `test_evaluation.py`, `test_module5_domains.py`, `test_module6_tools.py`, `test_orchestration.py`, `test_module8_identity.py`, `test_module9_*.py` (commands in the [Quick Start](#quick-start)), plus the shared suites in [Maintenance](#maintenance) |
| `module4` | 4 | 3.12 | `module4/.venv` | `./INSTALL.sh module4` | `AGENT_MOCK_MODE=true pytest tests/test_module4_orchestrator.py -v` |
| `module7` | 7 | 3.12 | `module7/.venv` | `./INSTALL.sh module7` | `AGENT_MOCK_MEMORY=true pytest tests/test_module7_*.py -v` |
| `module10` | 10 | 3.13 | `.venv`, or `.venv-m10` if `.venv` already holds the core env | `./INSTALL.sh module10` (`VENV_DIR=.venv-m10 ./INSTALL.sh module10`) | See [Module 10 operations](module10/deployment/OPERATIONS.md) |
| `module12` | 12 | 3.13 | `.venvs/module12` | See [Module 12 setup](module12/README.md#deployment-quick-start) | `python -m pytest tests/test_module12_*.py -q` |

The families are separate because Module 7 pins exact versions (a tested,
advisory-free set), Module 4 has its own requirements, and Modules 10 and 12 run
on Python 3.13 with their own SDK and infrastructure dependencies. Python 3.12
is tested for Modules 1-9 and Python 3.13 for Modules 10 and 12.

### Mock flags

Each flag mocks a module's partner or AWS data. Bedrock LLM calls stay live in
every case except Module 10 `--mode mock`. Defaults are the values the code uses when the variable is unset.

| Flag | Modules | Default | What it mocks | What stays live |
| --- | --- | --- | --- | --- |
| `AGENT_MOCK_AWS` | 1 | `false` | ECS, EC2, RDS and Lambda resource data | Bedrock |
| `AGENT_MOCK_REPO` | 2, 3 | `false` | Repository scans and file reads (Module 2), repository analysis inputs and evaluation judges (Module 3) | Bedrock; Module 3 CDK templates are always template-based |
| `AGENT_MOCK_MODE` | 4, 6, 8, and Module 9's Auth0 layer | `true` | Module 4 sub-agent calls, Module 6 activities, Module 8 Auth0 and CyberArk evidence, Module 9 identity tokens | Bedrock |
| `AGENT_MOCK_DOMAIN` | 5 | `true` in the tools; `demos/module5_demo.py` sets `false` when unset | Algolia, Deepgram, Mapbox and AWS domain services (Location, Lex, Personalize, Connect, Transcribe, Polly) | Bedrock |
| `AGENT_MOCK_MEMORY` | 7, 9 | `false` (`--mock` on the Module 7 and 9 demos sets it) | Redis Cloud, MongoDB Atlas and Neo4j Aura memory stores, embeddings | Bedrock |
| `AGENT_MOCK_PIPELINE` | 9 | `false` (`--mock` sets it; the demo also falls back to the mock per partner when a partner is unreachable) | Confluent Cloud and Databricks; implies `CONFLUENT_MOCK` and `DATABRICKS_MOCK` | Bedrock |
| `MODULE10_MODE` | 10 | `mock` | `mock`: deterministic stand-ins for everything; `local`: local LaunchDarkly file and Portkey gateway; `live`: hosted partners | Bedrock in `local` and `live` |

> `AGENT_MOCK_MODE` is shared. Setting `AGENT_MOCK_MODE=false` for live Auth0
> in Module 8 or 9 also switches Modules 4 and 6 to live mode in the same
> shell. Set it per command rather than exporting it.

`.env.example` lists every variable by module. Module 10 has its own
`module10/.env.example` and `module10/logzio.env.example`.

### Ports

Each module's HTTP server binds to `127.0.0.1` by default and has no
authentication; it is for local demos only.

| Port | Server | Override |
| --- | --- | --- |
| 8080 | `module1/app.py` | fixed |
| 8081 | `module2/app.py` | fixed |
| 8082 | `module3/app.py` | `MODULE3_PORT` |
| 8083 | `routing_agent/app.py` | `ROUTING_PORT` |
| 8084 | `module4/app.py` | `MODULE4_PORT` |
| 8085 | `module5/app.py` | `MODULE5_PORT` |
| 8086 | `module6/app.py` | `MODULE6_PORT` |
| 8087 | `module7/app.py` | `MODULE7_PORT` |
| 8089 | `module9/app.py` | `MODULE9_PORT` |
| 8090 | `module10/server.py` | `MODULE10_PORT` |

---

## Modules Overview

### Module 1: AWS Infrastructure Agent (Strands Framework)

Observes and analyzes AWS infrastructure with five read-only tools, using the
Think → Act → Observe loop, short-term memory, human-in-the-loop escalation, and
a one-line model swap between Anthropic and Hugging Face on Amazon Bedrock. It
also shows deployment to Amazon Bedrock AgentCore Runtime.

[See module1/README.md for details](module1/README.md)

### Module 2: Repository Analysis Agent (LangChain Framework)

Analyzes git repositories to identify applications and AWS infrastructure requirements using LangChain + LangGraph.

**Key Concepts:**
- LangChain `ChatBedrock` model interface
- LangGraph `create_react_agent` ReAct loop and LangGraph state machines
- Repository scanning and dependency analysis
- AWS service mapping from dependencies
- LangSmith tracing for observability

**Tools:** 5 repository analysis tools (scan, read, detect, analyze, map)

[See module2/README.md for details](module2/README.md)

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

[See module3/README.md for details](module3/README.md)

### Module 4: Multi-Agent Architectures

An orchestrator (a LangGraph ReAct agent) coordinates Modules 1-3 as
specialists: Direct HTTP agent-to-agent calls to Modules 1 and 2 (the concept
Google's A2A protocol formalizes) and MCP-style tools for Module 3, with
sequential pipelines, parallel fan-out, context handoff and graceful error
handling. [See module4/README.md](module4/README.md)

### Module 5: Domain-Specific Agents

The Domain Adaptation Engine specializes one general-purpose LangGraph agent
for a domain with four levers: system prompt layers, knowledge corpus, tool
scoping and guardrails. It ships customer, geospatial and voice domains.
[See module5/README.md](module5/README.md)

### Module 6: Durable Orchestration

Turns the DevOps Companion pipeline into a durable Temporal workflow:
checkpointed activities, crash and replay, approval signals, parallel
verification and saga compensation. The `module6/` teaching layer runs fully
offline; real Temporal workflows live in `orchestration/`.
[See module6/README.md](module6/README.md)

### Module 7: Agent Memory Systems

Adds three kinds of memory to a LangGraph agent: session memory through a
Redis Cloud checkpointer, long-term semantic memory in MongoDB Atlas Vector
Search, and relationship memory in Neo4j Aura, with PII redaction on memory
writes. [See module7/README.md](module7/README.md)

### Module 8: Agent Identity and Access Management

Follows one user-initiated workflow through Auth0 device-flow delegation, JWKS
token validation, deterministic agent authorization, an audit trail, and
CyberArk Agent Guard injecting a secret only into a protected MCP process.
[See module8/README.md](module8/README.md)

### Module 9: Data Pipelines and Lineage

Turns an operational event into governed knowledge: Confluent Cloud streaming,
Delta Lake and Unity Catalog lineage on Databricks, quality gates, freshness
SLAs, and answers traced back to the Kafka offset and Delta version.
[See module9/README.md](module9/README.md)

### Module 10: Agent Exposure and Integration

Exposes the agent through API Gateway with Cognito and Lambda authorization,
rolls out capabilities with LaunchDarkly, routes models through Portkey, and
inspects traces in Logz.io, in mock, local or cloud mode.
[See module10/README.md](module10/README.md)

### Module 11: MLOps and the Agent Development Lifecycle
Releases Module 10's DevOps Companion as a harness: every behavior input is a
file, sealed into one content-addressed manifest, declared in Pulumi, gated by
calibrated evaluations on GitLab merge requests and a CodePipeline release,
previewed per MR on Vercel, and delivered by canary with an automatic rollback
controller, drift detection and side-effect reconciliation. Live only (AWS,
GitLab, Vercel); offline tests and a replay of a real run need no account.
[See module11/README.md](module11/README.md)

---

## Project Structure

Most modules are a Python package with the same shape: `agent.py` for the
agent factory, `config/` for model and domain configuration, `tools/` for the
agent-facing tools, `prompts/` for the system prompt layers, and `mock/` for
the offline backends. Some modules differ (Module 6 adds `activities/` and
`workflows/`, Module 8 has `identity/` and no agent, Module 10 has its own
layout); each module's README shows its files.

```
agentic-ai/
├── module1/                    # Infrastructure Agent (AWS Strands)
├── module2/                    # Repository Analysis Agent (LangChain)
├── module3/                    # CDK Generation with evaluation (LangChain)
├── module4/                    # Multi-agent orchestration, MCP and A2A
├── module5/                    # Domain Adaptation Engine
├── module6/                    # Durable workflows (Temporal)
├── module7/                    # Agent memory systems
├── module8/                    # Agent identity and access management
├── module9/                    # Data pipelines and lineage
├── module10/                   # Agent exposure and ISV control planes
│
├── demos/                      # moduleN_demo.py, one guided demo per module
├── tests/                      # pytest suites (live tests are opt-in)
├── evaluation/                 # Shared evaluation harness (modules 2 and 3)
├── orchestration/              # Temporal workflows and activities
├── routing_agent/              # Standalone routing service
├── scripts/                    # invoke_agentcore.py, check_bedrock_models.py
├── docs/history/               # Historical development notes (not instructions)
│
├── INSTALL.sh                  # ./INSTALL.sh [core|module4|module7|module10]
├── verify_installation.py      # Checks the installed family
├── CHANGELOG.md                # Changes per module release
├── requirements.txt            # Shared dependencies (core family)
└── moduleN/requirements.txt    # Module-specific dependencies where needed
```
Module 11 adds one directory next to the others:

```
├── module11/                   # MLOps: harness-in-code, manifest, gates, progressive delivery
```

---

## Quick Start

### Setup

Requires Python 3.12 (3.13 for Module 10) and AWS credentials for Amazon
Bedrock. See [GETTING_STARTED.md](GETTING_STARTED.md) for prerequisites.

```bash
cd agentic-ai

# Core family: Modules 1-3, 5, 6, 8, 9, routing agent, evaluation, orchestration
./INSTALL.sh
source .venv/bin/activate
python verify_installation.py
```

Modules 4, 7 and 10 use their own environments (see [Environments](#environments)).

### Module 1: AWS Infrastructure Agent

```bash
# Run demo in mock mode (simulated AWS data; Bedrock calls are live)
AGENT_MOCK_AWS=true python demos/module1_demo.py

# Run specific section (1-6)
AGENT_MOCK_AWS=true python demos/module1_demo.py --section 4

# Run tests (offline)
AGENT_MOCK_AWS=true pytest tests/test_tools.py -v
```

Live AWS mode, the Hugging Face model swap and AgentCore deployment are in
[module1/README.md](module1/README.md).

### Module 2: Repository Analysis Agent

```bash
# Run demo in mock mode (no real repository needed; Bedrock calls are live)
AGENT_MOCK_REPO=true python demos/module2_demo.py

# Run specific section (1-11)
AGENT_MOCK_REPO=true python demos/module2_demo.py --section 5

# Run tests (offline)
AGENT_MOCK_REPO=true pytest tests/test_repo_tools.py -v
```

### Module 3: CDK Generation Agent with Evaluation

```bash
# Run demo in mock mode (no partner API keys needed;
# Section 9 calls Amazon Bedrock, so it needs AWS credentials)
AGENT_MOCK_REPO=true python demos/module3_demo.py

# Run specific section (1-11)
AGENT_MOCK_REPO=true python demos/module3_demo.py --section 6

# Run Module 3 evaluation pipeline (offline in mock mode)
AGENT_MOCK_REPO=true python -c "
from evaluation.pipelines.module3_eval import run_module3_evaluation
results = run_module3_evaluation(verbose=True)
print(f'Average Score: {results[\"summary\"][\"average_combined_score\"]:.1f}/100')
"

# Run tests (offline)
AGENT_MOCK_REPO=true pytest tests/test_module3_tools.py -v
pytest tests/test_module3_templates.py -v   # synthesizes the generated CDK; needs Node.js
AGENT_MOCK_REPO=true pytest tests/test_routing_agent.py -v
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py -v
```

### Modules 4 to 9

Run each module's demo in mock mode, then its tests. Each module's own
`README.md` covers live setup and the partner credentials it needs. Modules 7
and 9 also accept `--mock` and `--no-pause` on their demos.

```bash
# Module 4: multi-agent orchestration, MCP and A2A (module4 environment)
./INSTALL.sh module4
source module4/.venv/bin/activate
AGENT_MOCK_MODE=true python demos/module4_demo.py
AGENT_MOCK_MODE=true pytest tests/test_module4_orchestrator.py -v

# Module 7: agent memory (module7 environment)
./INSTALL.sh module7
source module7/.venv/bin/activate
AGENT_MOCK_MEMORY=true python demos/module7_demo.py
AGENT_MOCK_MEMORY=true pytest tests/test_module7_*.py -v
```

The live Module 7 agent tests call Bedrock and run only with
`RUN_INTEGRATION_TESTS=true`.

```bash
# Modules 5, 6, 8 and 9 (core environment)
source .venv/bin/activate

# Module 5: Domain Adaptation Engine
AGENT_MOCK_DOMAIN=true python demos/module5_demo.py
pytest tests/test_module5_domains.py -v

# Module 6: durable workflows with Temporal (fully offline)
AGENT_MOCK_MODE=true python demos/module6_demo.py
pytest tests/test_module6_tools.py -v
pytest tests/test_orchestration.py -v   # downloads the Temporal dev server on first run

# Module 8: agent identity and access (Auth0, CyberArk; fully offline)
AGENT_MOCK_MODE=true python demos/module8_demo.py
AGENT_MOCK_MODE=true pytest tests/test_module8_identity.py -v

# Module 9: data pipelines and lineage (Confluent Cloud, Databricks)
python demos/module9_demo.py --mock
AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true pytest tests/test_module9_*.py -v
```

Module 9's optional live partner clients are in `module9/requirements-live.txt`;
see [module9/README.md](module9/README.md) "Live setup".

### Module 10: Agent Exposure and Integration

Follow the [Module 10 quick start](module10/README.md) for local and cloud run
commands, UI credentials, and cleanup. First-time AWS setup is in the
[deployment guide](module10/deployment/README.md). The Module 10 Python tests
need the pinned Portkey gateway first (`module10/gateway/setup.py`); otherwise
28 of them error with "Install the pinned gateway first". The test commands are
in [OPERATIONS.md](module10/deployment/OPERATIONS.md) "Local checks".

### Routing Agent

```bash
# Start routing agent server (port 8083; calls Amazon Bedrock)
python routing_agent/app.py

# Classify a request
curl -X POST http://localhost:8083/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Analyze my repository at /home/user/app"}'

# Run tests (offline)
AGENT_MOCK_REPO=true pytest tests/test_routing_agent.py -v

# Run the live classification tests (Amazon Bedrock)
RUN_INTEGRATION_TESTS=true pytest tests/test_routing_agent.py -k live -v
```

### Module 11: MLOps and the Agent Development Lifecycle

Module 11 is live-only: it releases Module 10's cloud deployment through AWS,
GitLab and Vercel. Set it up with [module11/README.md](module11/README.md).
Without accounts, run the offline parts:

```bash
# Python 3.13 venv at .venvs/module11 with module11/requirements.txt and
# module11/requirements-pulumi.lock (module11/README.md, "Python environment")
python -m pytest tests/test_module11_*.py -q
node --test tests/test_module11_*.mjs            # Node.js 24
python -m module11 check                         # expect 0 error(s), 0 warning(s)

# Replay a real run from the committed, redacted captures (no credentials)
python demos/module11_demo.py --replay-fixtures --no-pause
```

### Module 12: Security and Observability

Run the deterministic local demo or use the deployed Pulumi stack:

```bash
source .venvs/module12/bin/activate
python demos/module12_demo.py

python demos/module12_demo.py --seed --stack module12-demo
python demos/module12_demo.py --stack module12-demo
```

See [module12/README.md](module12/README.md) for deployment and section commands.

---

## Live AWS Mode

### Amazon Bedrock model access

The demos call **Claude Sonnet 4.6** (`us.anthropic.claude-sonnet-4-6`) on
Amazon Bedrock, and some use Claude Haiku 4.5, Claude Opus 4.5 or Amazon Titan
Text Embeddings V2.

1. An AWS account with credentials configured (`aws configure`, `aws login`, or `AWS_*` environment variables).
2. Serverless foundation models are enabled automatically the first time you
   invoke them; there is no model access page to visit.
3. Anthropic models need a one-time use-case (first-time use) submission per
   account, made by selecting an Anthropic model in the Bedrock console model
   catalog.
4. The IAM identity must allow `bedrock:InvokeModel*` and, for the first
   invocation of a third-party model, `aws-marketplace:Subscribe`,
   `aws-marketplace:Unsubscribe` and `aws-marketplace:ViewSubscriptions`.

See [Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).
No subscription fee applies; you pay per token.

```bash
# Run Module 1 against real AWS (read-only ECS, EC2, RDS and Lambda calls)
python demos/module1_demo.py --live
```

### Hugging Face (via Amazon Bedrock Marketplace)

Deploying a Marketplace model creates a SageMaker endpoint that bills by the
hour while it runs. Delete it when you are done.

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

## Deploying to AgentCore Runtime (Module 1)

`module1/app.py` is the AgentCore Runtime entrypoint. Run every command from
`agentic-ai/`.

> These steps use the Bedrock AgentCore Starter Toolkit, which now reports that
> it is no longer supported and is superseded by the
> [AgentCore CLI](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html)
> (`@aws/agentcore`). The commands were checked against `agentcore --help`
> (toolkit 0.3.13) but not re-verified by deployment in this release.

```bash
# 1. Install the CLI
pip install bedrock-agentcore-starter-toolkit

# 2. Configure (run once — prompts for settings)
agentcore configure --entrypoint module1/app.py --disable-memory

# 3. Test locally (no Docker needed)
AGENT_MOCK_AWS=true python -m module1.app
# → Serves on http://localhost:8080/invocations

# 4. Test the local server
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Give me a health summary of us-east-1"}'

# 5. Deploy to AWS (CodeBuild, no Docker needed)
agentcore deploy          # formerly `agentcore launch`

# 6. Invoke the deployed agent
agentcore invoke '{"prompt": "List ECS services in us-east-1"}'

# 7. Invoke via boto3 (for automation / integration)
export AGENTCORE_ARN="arn:aws:bedrock-agentcore:..."
python scripts/invoke_agentcore.py --prompt "Health check us-east-1"
python scripts/invoke_agentcore.py --repl   # interactive mode
```

`scripts/invoke_agentcore.py` takes its Region from `--region`, then
`AWS_REGION`, then `AWS_DEFAULT_REGION`, then the Region inside the runtime ARN,
then `us-east-1`. The local server has no authentication; run it only while you
use it.

---

## Multi-Agent Architecture

Implemented in Module 4 (HTTP A2A-style + simulated MCP); Module 6 makes it
durable. The specialist agents work together in one workflow:

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

## Where each capability lives

| Capability | Module |
|---|---|
| Single agent loop, read-only tools, human-in-the-loop, model swap, AgentCore Runtime | Module 1 |
| LangChain / LangGraph agents, LangSmith tracing | Module 2 |
| Evaluation (LLM-as-judge, Patronus AI, Deepchecks, Comet ML) and intent routing | Module 3 |
| Multi-agent supervisor, HTTP agent-to-agent, MCP tools | Module 4 |
| Domain specialization (prompt layers, tool scoping, guardrails) | Module 5 |
| Durable workflows, signals, saga compensation | Module 6 |
| Agent memory: Redis Cloud, MongoDB Atlas, Neo4j Aura (not DynamoDB) | Module 7 |
| Agent identity and access: Auth0, CyberArk | Module 8 |
| Data pipelines, lineage, governed retrieval | Module 9 |
| Agent exposure, capability rollout, model routing, trace inspection | Module 10 |
| Production CloudWatch / X-Ray monitoring | Module 12 (planned) |
| Release management: harness manifest, evaluation gates, progressive delivery, rollback, drift | Module 11 |

## Maintenance

Each module release also maintains the earlier modules; see
[CHANGELOG.md](CHANGELOG.md). Before a release, `python scripts/check_bedrock_models.py`
checks every Bedrock model ID in the code sample against the model lifecycle
(read-only calls).

These shared suites run offline in the core environment. They cover the local
HTTP server hardening, the `.env` loaders, `scripts/invoke_agentcore.py` and
the model checker:

```bash
pytest tests/test_http_servers.py tests/test_env_loaders.py tests/test_invoke_agentcore.py tests/test_check_bedrock_models.py -v

# The Module 4 and Module 7 servers are tested in their own environments
pytest tests/test_http_servers.py -k module4 -v   # module4 environment
pytest tests/test_http_servers.py -k module7 -v   # module7 environment
```
