#!/usr/bin/env python3
"""
demos/module3_demo.py
=====================
Live workshop demonstration for Module 3: Agent Evaluation and Decision Engines.

Demonstrates CDK generation agent, evaluation harnesses, routing agent, and
ISV integrations (Patronus AI, Deepchecks, Comet ML).

USAGE
-----
  # Recommended: mock mode (no AWS account or API keys needed)
  AGENT_MOCK_REPO=true python demos/module3_demo.py

  # Run specific section
  AGENT_MOCK_REPO=true python demos/module3_demo.py --section 5

  # Run with real repository
  python demos/module3_demo.py --repo /path/to/repo

SECTIONS
--------
  1  Framework consistency    — LangChain across Module 2 & 3
  2  CDK generation          — Simple web app infrastructure
  3  Interactive questions   — Agent asks clarifying questions
  4  Complex infrastructure  — Multi-service microservices stack
  5  Evaluation pipeline     — Running Module 2 evaluation
  6  LLM-as-judge           — Automated quality scoring
  7  Patronus AI            — Custom evaluation criteria
  8  Deepchecks             — Hallucination detection
  9  Routing agent          — Intent classification demo
  10 Self-correction        — Agent evaluates and revises output
  11 Full workflow          — Module 2 → Module 3 → Evaluation
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
    from rich.syntax import Syntax
    from rich.table import Table
    _c = Console()

    def header(text: str, color: str = "cyan") -> None:
        _c.rule(f"[bold {color}]{text}[/bold {color}]", style=color)

    def concept(text: str) -> None:
        _c.print(f"\n[bold yellow]💡 Module 3 Concept:[/bold yellow] [yellow]{text}[/yellow]")

    def user_says(text: str) -> None:
        _c.print(f"\n[bold green]USER ›[/bold green] [italic]{text}[/italic]")

    def box(title: str, body: str) -> None:
        _c.print(Panel(f"[dim]{body}[/dim]", title=f"[bold]{title}[/bold]", border_style="cyan"))

    def code_block(code: str, language: str = "python") -> None:
        syntax = Syntax(code, language, theme="monokai", line_numbers=False)
        _c.print(syntax)

except ImportError:
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


def pause(msg: str = "  ↵  Press Enter to continue...") -> None:
    try:
        input(msg)
    except KeyboardInterrupt:
        sys.exit(0)


# ---------------------------------------------------------------------------
# Section 1 — Framework Consistency
# ---------------------------------------------------------------------------

def section_1_framework_consistency() -> None:
    header("SECTION 1 — LangChain Framework Consistency", "cyan")
    box(
        "Module 2 & Module 3: Same Framework, Different Use Cases",
        "Both Module 2 (Repository Analysis) and Module 3 (CDK Generation) use LangChain.\n"
        "This demonstrates framework consistency across different agent types.",
    )

    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  MODULE 2: Repository Analysis Agent                           │
  │                                                                 │
  │    from langchain_aws import ChatBedrock                        │
  │    from langgraph.prebuilt import create_react_agent           │
  │                                                                 │
  │    model = ChatBedrock(model_id="claude-sonnet-4", ...)        │
  │    agent = create_react_agent(model, repo_tools)               │
  │                                                                 │
  │    Tools: scan_repository, detect_applications, analyze_deps   │
  └─────────────────────────────────────────────────────────────────┘
              │
  ┌─────────────────────────────────────────────────────────────────┐
  │  MODULE 3: CDK Generation Agent                                │
  │                                                                 │
  │    from langchain_aws import ChatBedrock                        │
  │    from langgraph.prebuilt import create_react_agent           │
  │                                                                 │
  │    model = ChatBedrock(model_id="claude-sonnet-4", ...)        │
  │    agent = create_react_agent(model, cdk_tools)                │
  │                                                                 │
  │    Tools: analyze_requirements, generate_cdk_stack, validate   │
  └─────────────────────────────────────────────────────────────────┘
""")

    concept(
        "Same framework (LangChain), same model (Claude Sonnet 4), same pattern (ReAct), "
        "but different tools and prompts for different tasks. This is the power of "
        "the agent abstraction."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 2 — CDK Generation
# ---------------------------------------------------------------------------

def section_2_cdk_generation() -> None:
    header("SECTION 2 — CDK Code Generation", "cyan")
    
    user_says("Generate CDK infrastructure for a simple web application with PostgreSQL database")
    
    print("\n  [Module 3 Agent] Analyzing requirements...")
    print("  [Module 3 Agent] Using LangGraph ReAct Agent")
    print("  [Model] Claude Sonnet 4 via Amazon Bedrock")
    print("  [Tools] 5 CDK generation tools\n")
    
    # Simulate agent execution by calling tool functions directly
    from module3.tools import cdk_tools
    
    print("  🔧 [Step 1] ACT → analyze_infrastructure_requirements(...)")
    print("  ✓  OBSERVE ← Requirements parsed: VPC, RDS PostgreSQL, ECS Fargate\n")
    
    print("  🔧 [Step 2] ACT → generate_cdk_stack(stack_type='vpc', ...)")
    # Call the underlying function, not the LangChain tool wrapper
    result = cdk_tools.generate_cdk_stack.func("vpc", json.dumps({"max_azs": 2, "nat_gateways": 1}))
    vpc_data = json.loads(result)
    print("  ✓  OBSERVE ← VPC stack generated\n")
    
    print("  🔧 [Step 3] ACT → generate_cdk_stack(stack_type='rds', ...)")
    result = cdk_tools.generate_cdk_stack.func("rds", json.dumps({"engine": "POSTGRES", "multi_az": True}))
    rds_data = json.loads(result)
    print("  ✓  OBSERVE ← RDS stack generated\n")
    
    print("  🔧 [Step 4] ACT → validate_cdk_syntax(...)")
    print("  ✓  OBSERVE ← Syntax validation: PASS\n")
    
    box("Generated VPC Stack (excerpt)", vpc_data["data"]["code"][:400] + "\n...")
    
    concept(
        "The agent decomposed the request into multiple tool calls: analyze requirements, "
        "generate VPC, generate RDS, validate syntax. Each stack follows AWS best practices "
        "with multi-AZ, encryption, and proper security groups."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 3 — Interactive Questions
# ---------------------------------------------------------------------------

def section_3_interactive_questions() -> None:
    header("SECTION 3 — Interactive Clarification", "cyan")
    
    user_says("Generate infrastructure for my microservices application")
    
    print("\n  [Module 3 Agent] Analyzing requirements...")
    print("  [Module 3 Agent] Insufficient information detected\n")
    
    box(
        "Agent's Clarifying Questions",
        """The agent needs more details to generate appropriate infrastructure:

1. How many microservices do you have?
2. What databases do they require (PostgreSQL, MySQL, MongoDB)?
3. Do you need caching (Redis, Memcached)?
4. What AWS region should this be deployed to?
5. What environment is this for (dev, staging, prod)?
6. Do you need high availability (multi-AZ)?
7. What are your scaling requirements?

Please provide these details so I can generate the most appropriate CDK stacks."""
    )
    
    concept(
        "The agent recognizes when it doesn't have enough information and asks targeted "
        "questions rather than making assumptions. This is the 'Clarify' step from the "
        "Module 3 system prompt."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 4 — Complex Infrastructure
# ---------------------------------------------------------------------------

def section_4_complex_infrastructure() -> None:
    header("SECTION 4 — Complex Multi-Service Infrastructure", "cyan")
    
    requirements = {
        "services": ["api", "worker", "scheduler"],
        "database": "RDS PostgreSQL",
        "cache": "ElastiCache Redis",
        "queue": "SQS",
        "region": "us-east-1",
        "environment": "production",
    }
    
    user_says(f"Generate CDK for: {json.dumps(requirements, indent=2)}")
    
    print("\n  [Module 3 Agent] Processing complex requirements...")
    print("  [Module 3 Agent] Identified 6 required stacks\n")
    
    stacks = [
        ("VpcStack", "VPC with public/private subnets across 2 AZs"),
        ("RdsStack", "PostgreSQL Multi-AZ with automated backups"),
        ("ElastiCacheStack", "Redis cluster with automatic failover"),
        ("SqsStack", "SQS queues for inter-service communication"),
        ("EcsApiStack", "API service on ECS Fargate with ALB"),
        ("EcsWorkerStack", "Worker service on ECS Fargate"),
    ]
    
    try:
        from rich.table import Table
        table = Table(title="Generated CDK Stacks")
        table.add_column("Stack", style="cyan")
        table.add_column("Description", style="white")
        
        for stack_name, description in stacks:
            table.add_row(stack_name, description)
        
        _c.print(table)
    except:
        print("\n  Generated Stacks:")
        for stack_name, description in stacks:
            print(f"    • {stack_name}: {description}")
    
    concept(
        "For complex infrastructure, the agent generates multiple coordinated stacks. "
        "Each stack is self-contained but designed to work together through proper "
        "resource references and security group configurations."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 5 — Evaluation Pipeline
# ---------------------------------------------------------------------------

def section_5_evaluation_pipeline() -> None:
    header("SECTION 5 — Module 2 Evaluation Pipeline", "cyan")
    
    box(
        "Evaluation Dimensions",
        """Module 2 (Repository Analysis) is evaluated on 4 dimensions:

1. Completeness: All services/dependencies identified (0-100%)
2. Accuracy: Correct technology stack identification (0-100%)
3. Actionability: Sufficient detail for CDK generation (0-100%)
4. Safety Awareness: Security issues flagged (0-100%)"""
    )
    
    print("\n  [Evaluation] Running Module 2 evaluation pipeline...")
    print("  [Test Cases] 6 test cases loaded")
    print("  [Mode] MOCK\n")
    
    from evaluation.pipelines.module2_eval import run_module2_evaluation
    
    # Run evaluation in mock mode
    results = run_module2_evaluation(verbose=True)
    
    summary = results["summary"]
    
    print(f"\n  ═══════════════════════════════════════════════════════════")
    print(f"  EVALUATION RESULTS")
    print(f"  ═══════════════════════════════════════════════════════════")
    print(f"  Average Score: {summary['average_score']:.1f}/100")
    print(f"  Pass Rate: {summary['pass_rate']*100:.1f}%")
    print(f"  Score Range: {summary['min_score']:.0f} - {summary['max_score']:.0f}")
    print(f"\n  Criteria Scores:")
    for criterion, stats in summary['criteria_scores'].items():
        print(f"    {criterion}: {stats['average']:.1f}/100")
    print(f"  ═══════════════════════════════════════════════════════════\n")
    
    concept(
        "The evaluation pipeline runs the agent against a test dataset, scores each output "
        "using LLM-as-judge, and aggregates results. This provides objective metrics for "
        "tracking agent quality across versions."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 6 — LLM-as-Judge
# ---------------------------------------------------------------------------

def section_6_llm_as_judge() -> None:
    header("SECTION 6 — LLM-as-Judge Pattern", "cyan")
    
    box(
        "LLM-as-Judge Architecture",
        """Agent Model: Claude Sonnet 4 (temperature=0.1 for code generation)
Judge Model: Claude Opus 4 (temperature=0.0 for evaluation)

Why different models?
• Avoids bias (agent can't game its own evaluation)
• Opus has stronger reasoning for complex evaluation
• Deterministic judging (temperature=0.0)"""
    )
    
    sample_cdk = '''from aws_cdk import Stack
from constructs import Construct

class VpcStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        # VPC implementation...
'''
    
    criteria = {
        "syntax_correctness": "Valid Python CDK syntax",
        "completeness": "All required resources included",
        "best_practices": "Follows AWS best practices",
        "security": "Proper security configurations",
    }
    
    print("\n  [LLM Judge] Evaluating CDK code...")
    print("  [Judge Model] Claude Opus 4")
    print("  [Criteria] 4 evaluation criteria\n")
    
    from module3.evaluators.llm_judge import evaluate_with_llm_judge
    
    result = evaluate_with_llm_judge(
        task_description="Generate VPC CDK stack",
        agent_output=sample_cdk,
        criteria=criteria,
        verbose=True,
    )
    
    print(f"\n  Evaluation Results:")
    print(f"    Overall Score: {result.get('overall_score', 0)}/100")
    print(f"    Strengths: {len(result.get('strengths', []))}")
    print(f"    Weaknesses: {len(result.get('weaknesses', []))}")
    print(f"    Recommendations: {len(result.get('recommendations', []))}\n")
    
    concept(
        "LLM-as-judge is the most scalable approach to automated evaluation. It can assess "
        "open-ended outputs without requiring predefined answers, and provides structured "
        "feedback with rationale."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 7 — Patronus AI
# ---------------------------------------------------------------------------

def section_7_patronus_ai() -> None:
    header("SECTION 7 — Patronus AI Integration", "cyan")
    
    box(
        "Patronus AI Capabilities",
        """• Custom evaluation criteria definition
• Automated scoring with regression tracking
• Evaluation dashboard and analytics
• Version comparison across agent releases"""
    )
    
    print("\n  [Patronus] Initializing evaluator...")
    
    from evaluation.integrations.patronus_integration import PatronusEvaluator
    
    evaluator = PatronusEvaluator(project_name="devops-companion")
    
    # Create custom criterion
    custom_criterion = evaluator.create_custom_criteria(
        name="cdk_idempotency",
        description="CDK code can be deployed multiple times without errors",
        scoring_rubric={
            "90-100": "Fully idempotent with proper resource naming",
            "70-89": "Mostly idempotent with minor issues",
            "50-69": "Some idempotency issues",
            "0-49": "Not idempotent, will fail on re-deployment",
        },
    )
    
    print(f"  [Patronus] Custom criterion created: {custom_criterion['name']}")
    print(f"  [Patronus] Criterion ID: {custom_criterion['criterion_id']}\n")
    
    # Evaluate sample output
    result = evaluator.evaluate(
        task="Generate ECS CDK stack",
        output="Sample CDK code...",
        criteria={"idempotency": "Code is idempotent"},
        metadata={"agent_version": "module3-v1.0"},
    )
    
    print(f"  Evaluation Results:")
    print(f"    Evaluation ID: {result['evaluation_id']}")
    print(f"    Overall Score: {result['overall_score']:.1f}/100")
    print(f"    Pass: {result['pass']}")
    print(f"    Dashboard: {result['dashboard_url']}\n")
    
    concept(
        "Patronus AI provides a platform for defining custom evaluation criteria specific "
        "to your use case. It tracks evaluations across agent versions, making it easy to "
        "detect regressions."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 8 — Deepchecks
# ---------------------------------------------------------------------------

def section_8_deepchecks() -> None:
    header("SECTION 8 — Deepchecks Hallucination Detection", "cyan")
    
    box(
        "Deepchecks Capabilities",
        """• Hallucination detection in LLM outputs
• Automated quality testing
• LLM output validation
• Anomaly detection"""
    )
    
    print("\n  [Deepchecks] Initializing evaluator...")
    
    from evaluation.integrations.deepchecks_integration import DeepchecksEvaluator
    
    evaluator = DeepchecksEvaluator()
    
    # Sample output with potential hallucination
    sample_output = """This CDK stack will definitely work in all regions and will never fail. 
    It's absolutely guaranteed to be 100% secure and will always scale perfectly."""
    
    print(f"  [Deepchecks] Checking for hallucinations...\n")
    
    result = evaluator.detect_hallucinations(
        output=sample_output,
        context="Generate CDK stack for web application",
    )
    
    print(f"  Hallucination Detection Results:")
    print(f"    Hallucinations Detected: {result['hallucination_detected']}")
    print(f"    Hallucination Count: {result['hallucination_count']}")
    print(f"    Hallucination Score: {result['hallucination_score']}/100")
    print(f"    Severity: {result['severity']}")
    
    if result['hallucinations']:
        print(f"\n    Detected Issues:")
        for h in result['hallucinations']:
            print(f"      • {h['type']}: {h.get('indicator', 'N/A')} (severity: {h['severity']})")
    
    print()
    
    concept(
        "Deepchecks detects unsupported claims and hallucinations in LLM outputs. "
        "This is critical for production agents where accuracy and truthfulness matter. "
        "Absolute statements like 'always', 'never', 'guaranteed' are red flags."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 9 — Routing Agent
# ---------------------------------------------------------------------------

def section_9_routing_agent() -> None:
    header("SECTION 9 — Intent Classification & Routing", "cyan")
    
    box(
        "Routing Agent Categories",
        """1. repository_analysis → Module 2 (port 8081)
2. infrastructure_generation → Module 3 (port 8082)
3. aws_infrastructure → Module 1 (port 8080)
4. deployment_monitoring → Future capability"""
    )
    
    print("\n  [Routing Agent] Classifying requests...\n")
    
    from routing_agent.agent import classify_intent
    
    test_requests = [
        "Analyze the repository at /home/user/myapp",
        "Generate CDK for a Node.js app with PostgreSQL",
        "Check the health of my ECS services in us-east-1",
    ]
    
    for i, request in enumerate(test_requests, 1):
        print(f"  Request {i}: \"{request}\"")
        
        result = classify_intent(request, verbose=False)
        
        print(f"    → Category: {result['category']}")
        print(f"    → Confidence: {result['confidence']:.2f}")
        print(f"    → Target: {result['target_agent']}")
        print(f"    → URL: {result['target_url']}\n")
    
    concept(
        "The routing agent uses a single LLM call (not a full agent loop) to classify "
        "intent and route to the appropriate specialist agent. This is more efficient "
        "than running all agents and choosing the best response."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 10 — Self-Correction
# ---------------------------------------------------------------------------

def section_10_self_correction() -> None:
    header("SECTION 10 — Self-Correction Pattern", "cyan")
    
    box(
        "Self-Correction Flow",
        """1. Agent generates CDK code
2. Agent evaluates its own output
3. If quality < threshold, agent revises
4. Maximum 2 iterations to bound latency"""
    )
    
    print("\n  [Module 3 Agent] Generating CDK stack...")
    print("  [Module 3 Agent] Initial generation complete\n")
    
    print("  [Self-Evaluation] Checking output quality...")
    print("  [Self-Evaluation] Issues found:")
    print("    • Missing encryption configuration")
    print("    • Security group too permissive")
    print("    • No CloudWatch logging\n")
    
    print("  [Self-Correction] Quality below threshold (65/100)")
    print("  [Self-Correction] Revising output...\n")
    
    print("  [Module 3 Agent] Generating revised CDK stack...")
    print("  [Module 3 Agent] Added encryption at rest")
    print("  [Module 3 Agent] Restricted security group rules")
    print("  [Module 3 Agent] Added CloudWatch log groups\n")
    
    print("  [Self-Evaluation] Re-checking output quality...")
    print("  [Self-Evaluation] Quality score: 92/100")
    print("  [Self-Evaluation] PASS - returning output\n")
    
    concept(
        "Self-correction adds latency but improves output quality. The agent uses the same "
        "evaluation tools available to humans, making it aware of quality standards. "
        "This is particularly useful for code generation where syntax and best practices matter."
    )
    pause()


# ---------------------------------------------------------------------------
# Section 11 — Full Workflow
# ---------------------------------------------------------------------------

def section_11_full_workflow() -> None:
    header("SECTION 11 — Complete Multi-Agent Workflow", "cyan")
    
    box(
        "End-to-End Flow",
        """USER REQUEST
  ↓
ROUTING AGENT (classify intent)
  ↓
MODULE 2 AGENT (analyze repository)
  ↓
MODULE 3 AGENT (generate CDK infrastructure)
  ↓
EVALUATION SYSTEM (assess quality)
  ↓
ISV INTEGRATIONS (Patronus, Deepchecks, Comet ML)
  ↓
RESULTS + METRICS"""
    )
    
    print("\n  Starting complete workflow...\n")
    
    # Step 1: Routing
    print("  [Step 1] ROUTING AGENT")
    user_request = "Analyze my repository and generate infrastructure"
    print(f"    Request: \"{user_request}\"")
    
    from routing_agent.agent import classify_intent
    routing = classify_intent(user_request, verbose=False)
    print(f"    → Classified as: {routing['category']}")
    print(f"    → Confidence: {routing['confidence']:.2f}\n")
    
    # Step 2: Module 2
    print("  [Step 2] MODULE 2 AGENT (Repository Analysis)")
    print("    → Scanning repository structure")
    print("    → Detecting applications: 1 found")
    print("    → Analyzing dependencies: Node.js, Express, PostgreSQL, Redis")
    print("    → Mapping to AWS services: ECS, RDS, ElastiCache\n")
    
    module2_output = {
        "applications": 1,
        "stack": "Node.js + Express",
        "aws_requirements": ["ECS", "RDS PostgreSQL", "ElastiCache Redis", "VPC"],
    }
    
    # Step 3: Module 3
    print("  [Step 3] MODULE 3 AGENT (CDK Generation)")
    print("    → Parsing Module 2 output")
    print("    → Generating VPC stack")
    print("    → Generating RDS stack")
    print("    → Generating ElastiCache stack")
    print("    → Generating ECS stack")
    print("    → Validating syntax: PASS\n")
    
    # Step 4: Evaluation
    print("  [Step 4] EVALUATION SYSTEM")
    print("    → LLM-as-judge evaluation")
    print("    → CDK syntax validation")
    print("    → Best practices check")
    print("    → Security audit\n")
    
    # Step 5: ISV Integrations
    print("  [Step 5] ISV INTEGRATIONS")
    print("    → Patronus AI: Regression tracking")
    print("    → Deepchecks: Hallucination detection")
    print("    → Comet ML: Experiment logging\n")
    
    # Results
    print("  ═══════════════════════════════════════════════════════════")
    print("  WORKFLOW COMPLETE")
    print("  ═══════════════════════════════════════════════════════════")
    print("  Repository Analysis: ✓ Complete")
    print("  CDK Generation: ✓ 4 stacks generated")
    print("  Evaluation Score: 88/100")
    print("  Hallucinations: None detected")
    print("  Quality: PASS")
    print("  ═══════════════════════════════════════════════════════════\n")
    
    concept(
        "This is the complete DevOps Companion workflow: routing → analysis → generation → "
        "evaluation. Each agent is specialized, evaluation is automated, and ISV tools provide "
        "production-grade quality assurance. Module 4 will add orchestration to coordinate "
        "these agents automatically."
    )
    pause()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Module 3 Workshop Demo")
    parser.add_argument("--section", "-s", type=int, choices=range(1, 12), metavar="1-11")
    parser.add_argument("--repo", type=str, help="Path to real repository to analyze")
    args = parser.parse_args()

    # Set mock mode if no real repo provided
    if not args.repo:
        os.environ["AGENT_MOCK_REPO"] = "true"
        print("  Mock mode ON  (pass --repo /path to analyze a real repository)\n")

    header("MODULE 3 DEMO — EVALUATION & CDK GENERATION", "bold cyan")
    print("""
  Use case: DevOps Engineer building an agentic system that analyzes
  repositories, generates infrastructure code, and evaluates quality
  using automated pipelines and ISV partner tools.

  This demo covers:
    • CDK infrastructure generation with LangChain
    • Automated evaluation pipelines
    • LLM-as-judge pattern
    • ISV integrations (Patronus AI, Deepchecks, Comet ML)
    • Routing agent for multi-agent orchestration
    • Self-correction pattern
""")

    sections = {
        1: section_1_framework_consistency,
        2: section_2_cdk_generation,
        3: section_3_interactive_questions,
        4: section_4_complex_infrastructure,
        5: section_5_evaluation_pipeline,
        6: section_6_llm_as_judge,
        7: section_7_patronus_ai,
        8: section_8_deepchecks,
        9: section_9_routing_agent,
        10: section_10_self_correction,
        11: section_11_full_workflow,
    }

    if args.section:
        sections[args.section]()
    else:
        for section_func in sections.values():
            section_func()

    header("DEMO COMPLETE", "green")
    print("""
  Next steps:
    • Explore the code in module3/, routing-agent/, and evaluation/
    • Run the evaluation pipelines with your own test cases
    • Integrate ISV partner APIs for production use
    • Wait for Module 4 for multi-agent orchestration

  Thank you for completing Module 3!
""")


if __name__ == "__main__":
    main()
