# Module 3: CDK Infrastructure Generation Agent

LangChain-based agent for generating AWS CDK infrastructure code from repository analysis or direct requirements.

## Overview

Module 3 demonstrates **evaluation and decision engines** using LangChain and LangGraph. It generates production-ready AWS CDK stacks based on infrastructure requirements, with comprehensive evaluation and quality assurance.

## What This Agent Does

1. **Analyzes** infrastructure requirements from Module 2 output or user specifications
2. **Clarifies** deployment preferences through targeted questions
3. **Generates** production-ready CDK stack code following AWS best practices
4. **Validates** generated code for syntax correctness and security
5. **Evaluates** output quality using LLM-as-judge and automated checks

## Quick Start

```bash
# Mock mode (no AWS account needed)
AGENT_MOCK_REPO=true python demos/module3_demo.py

# Generate infrastructure from requirements
python demos/module3_demo.py --section 2

# Run specific demo section
AGENT_MOCK_REPO=true python demos/module3_demo.py --section 6

# Run tests
AGENT_MOCK_REPO=true pytest tests/test_module3_tools.py -v
```

## Architecture

### Framework: LangChain + LangGraph

**Model Interface**: `ChatBedrock` (LangChain wrapper for Amazon Bedrock)  
**Execution Loop**: `AgentExecutor` with ReAct pattern  
**Tools**: 5 CDK generation and validation tools  
**Observability**: LangSmith tracing integration  

### Five CDK Generation Tools

1. **`analyze_infrastructure_requirements`** - Parse Module 2 output or requirements
2. **`generate_cdk_stack`** - Generate CDK code for specific AWS services
3. **`validate_cdk_syntax`** - Validate generated CDK syntax
4. **`list_available_constructs`** - List available CDK constructs for services
5. **`generate_cdk_tests`** - Generate test files for CDK stacks

## Supported Infrastructure Patterns

- **VPC**: Multi-AZ with public/private subnets
- **ECS**: Fargate service with Application Load Balancer
- **RDS**: Multi-AZ database with encryption and backups
- **ElastiCache**: Redis cluster with automatic failover
- **S3**: Encrypted buckets with versioning
- **Lambda**: Functions with VPC access and monitoring

## Example Output

```python
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_rds as rds,
)
from constructs import Construct


class RdsStack(Stack):
    """RDS database with Multi-AZ deployment and encryption."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Security Group
        db_security_group = ec2.SecurityGroup(
            self,
            "DBSecurityGroup",
            vpc=vpc,
            description="Security group for RDS database",
        )

        # RDS Instance
        self.database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15_4
            ),
            vpc=vpc,
            multi_az=True,
            storage_encrypted=True,
            backup_retention=Duration.days(7),
            deletion_protection=True,
        )
```

## Usage

### Python API

```python
from module3.agent import create_agent, generate_infrastructure

# Simple approach
agent = create_agent(verbose=True)
result = agent.invoke({
    "messages": [("user", "Generate CDK for web app with PostgreSQL")]
})
print(result["messages"][-1].content)

# Convenience function
requirements = {
    "compute": "ECS Fargate",
    "database": "RDS PostgreSQL",
    "cache": "ElastiCache Redis",
}
results = generate_infrastructure(requirements, region="us-east-1")
print(results["output"])
```

### HTTP Server

```bash
# Start server
python module3/app.py

# Generate infrastructure
curl -X POST http://localhost:8082/generate \
  -H "Content-Type: application/json" \
  -d '{
    "requirements": {
      "compute": "ECS",
      "database": "RDS PostgreSQL"
    },
    "region": "us-east-1",
    "environment": "prod"
  }'

# Validate CDK code
curl -X POST http://localhost:8082/validate \
  -H "Content-Type: application/json" \
  -d '{"cdk_code": "from aws_cdk import Stack..."}'
```

## Evaluation System

Module 3 includes comprehensive evaluation capabilities:

### Four Evaluation Dimensions

1. **Syntax Correctness**: Valid Python CDK syntax (pass/fail)
2. **Completeness**: All required resources included (0-100%)
3. **Best Practices**: Follows AWS and CDK best practices (0-100%)
4. **Security**: Proper encryption, IAM, security groups (0-100%)

### LLM-as-Judge Pattern

```python
from module3.evaluators.llm_judge import evaluate_with_llm_judge

criteria = {
    "completeness": "All required CDK resources are included",
    "best_practices": "Follows AWS and CDK best practices",
    "security": "Proper security configurations",
}

result = evaluate_with_llm_judge(
    task_description="Generate VPC CDK stack",
    agent_output=cdk_code,
    criteria=criteria,
)

print(f"Overall Score: {result['overall_score']}/100")
```

### Automated Evaluation Pipeline

```python
from evaluation.pipelines.module3_eval import run_module3_evaluation

results = run_module3_evaluation(verbose=True)

print(f"Average Score: {results['summary']['average_score']:.1f}/100")
print(f"Pass Rate: {results['summary']['pass_rate']*100:.1f}%")
```

## ISV Partner Integrations

### Patronus AI - Custom Evaluation Criteria

```python
from evaluation.integrations.patronus_integration import PatronusEvaluator

evaluator = PatronusEvaluator(project_name="devops-companion")

result = evaluator.evaluate(
    task="Generate CDK stack",
    output=cdk_code,
    criteria={"quality": "Production-ready code"},
)
```

### Deepchecks - Hallucination Detection

```python
from evaluation.integrations.deepchecks_integration import DeepchecksEvaluator

evaluator = DeepchecksEvaluator()

result = evaluator.detect_hallucinations(
    output=agent_output,
    context="Generate infrastructure",
)
```

### Comet ML - Experiment Tracking

```python
from evaluation.integrations.cometml_integration import CometMLTracker

tracker = CometMLTracker(project_name="devops-companion-eval")

exp_id = tracker.start_experiment("module3-baseline")
tracker.log_metrics({"average_score": 88.5, "pass_rate": 0.92})
tracker.end_experiment()
```

## Integration with Module 2

Module 3 is designed to work seamlessly with Module 2:

```python
# Module 2: Analyze repository
from module2.agent import analyze_repository

repo_analysis = analyze_repository("/path/to/repo")

# Module 3: Generate infrastructure from analysis
from module3.agent import generate_infrastructure

cdk_code = generate_infrastructure(
    requirements=repo_analysis["output"],
    region="us-east-1",
    environment="prod",
)
```

## Project Structure

```
module3/
├── agent.py              # Agent factory and main logic
├── app.py                # HTTP server entrypoint
├── config/
│   └── models.py         # ChatBedrock configuration
├── tools/
│   └── cdk_tools.py      # 5 CDK generation tools
├── templates/
│   └── cdk_patterns.py   # Reusable CDK patterns
├── prompts/
│   └── system_prompts.py # System prompts for generation
└── evaluators/
    ├── llm_judge.py      # LLM-as-judge implementation
    └── cdk_evaluator.py  # CDK code quality evaluator
```

## Testing

```bash
# Run all Module 3 tests
AGENT_MOCK_REPO=true pytest tests/test_module3_tools.py -v

# Run specific test
AGENT_MOCK_REPO=true pytest tests/test_module3_tools.py::test_generate_cdk_stack_vpc -v

# Run evaluation tests
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py -v
```

## Demo Sections

Run `AGENT_MOCK_REPO=true python demos/module3_demo.py --section N`:

| # | Title | Key Concept |
|---|-------|-------------|
| 1 | Framework consistency | LangChain across Module 2 & 3 |
| 2 | CDK generation | Simple web app infrastructure |
| 3 | Interactive questions | Agent asks clarifying questions |
| 4 | Complex infrastructure | Multi-service microservices stack |
| 5 | Evaluation pipeline | Running Module 2 evaluation |
| 6 | LLM-as-judge | Automated quality scoring |
| 7 | Patronus AI | Custom evaluation criteria |
| 8 | Deepchecks | Hallucination detection |
| 9 | Routing agent | Intent classification demo |
| 10 | Self-correction | Agent evaluates and revises output |
| 11 | Full workflow | Module 2 → Module 3 → Evaluation |

## Best Practices

### CDK Code Generation

- **Multi-AZ deployments** for production workloads
- **Encryption at rest and in transit** for all data stores
- **Least privilege IAM policies** for all resources
- **Security groups** with minimal necessary access
- **CloudWatch monitoring** and alarms
- **Proper tagging** for cost allocation

### Evaluation

- Run evaluation pipeline before merging changes
- Track metrics across agent versions
- Use LLM-as-judge for open-ended outputs
- Combine automated and manual evaluation
- Set quality thresholds (e.g., 70% pass rate)

## Next Steps

- **Module 4**: Multi-agent orchestration (Module 1 + Module 2 + Module 3)
- **Module 7**: Long-term memory with DynamoDB and vector stores
- **Module 12**: Production monitoring with CloudWatch and X-Ray

## License

Part of the AI Agent Learning Series on AWS.
