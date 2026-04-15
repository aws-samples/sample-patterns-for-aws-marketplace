# Evaluation System for Module 2 & Module 3

Comprehensive evaluation framework for assessing agent quality using automated pipelines, LLM-as-judge, and ISV partner integrations.

## Overview

The evaluation system provides:
- **Automated evaluation pipelines** for Module 2 and Module 3
- **LLM-as-judge pattern** for open-ended output assessment
- **Test datasets** with evaluation criteria
- **ISV integrations** (Patronus AI, Deepchecks, Comet ML)
- **Metrics tracking** and regression detection

## Quick Start

```bash
# Run Module 2 evaluation
AGENT_MOCK_REPO=true python -c "
from evaluation.pipelines.module2_eval import run_module2_evaluation
results = run_module2_evaluation(verbose=True)
print(f'Average Score: {results[\"summary\"][\"average_score\"]:.1f}/100')
"

# Run Module 3 evaluation
AGENT_MOCK_REPO=true python -c "
from evaluation.pipelines.module3_eval import run_module3_evaluation
results = run_module3_evaluation(verbose=True)
print(f'Pass Rate: {results[\"summary\"][\"pass_rate\"]*100:.1f}%')
"

# Run tests
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py -v
```

## Evaluation Dimensions

### Module 2: Repository Analysis

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **Completeness** | All services/dependencies identified | 25% |
| **Accuracy** | Correct technology stack identification | 25% |
| **Actionability** | Sufficient detail for CDK generation | 25% |
| **Safety Awareness** | Security issues flagged | 25% |

### Module 3: CDK Generation

| Dimension | Description | Weight |
|-----------|-------------|--------|
| **Syntax Correctness** | Valid Python CDK syntax | 40% |
| **Completeness** | All required resources included | 20% |
| **Best Practices** | Follows AWS and CDK best practices | 20% |
| **Security** | Proper security configurations | 20% |

## LLM-as-Judge Pattern

### Architecture

```
Agent Model:  Claude Sonnet 4 (temperature=0.1)
              ↓
              Generates output
              ↓
Judge Model:  Claude Opus 4 (temperature=0.0)
              ↓
              Evaluates against criteria
              ↓
              Structured scores + rationale
```

### Why Different Models?

- **Avoids bias**: Agent can't game its own evaluation
- **Stronger reasoning**: Opus has better evaluation capabilities
- **Deterministic**: Temperature=0.0 for consistent scoring

### Usage

```python
from module3.evaluators.llm_judge import evaluate_with_llm_judge

criteria = {
    "completeness": "All required CDK resources are included",
    "best_practices": "Follows AWS and CDK best practices",
    "security": "Proper encryption, IAM, and security groups",
}

result = evaluate_with_llm_judge(
    task_description="Generate VPC CDK stack with RDS",
    agent_output=cdk_code,
    criteria=criteria,
    reference_answer=expected_output,  # optional
)

print(f"Overall Score: {result['overall_score']}/100")
print(f"Strengths: {result['strengths']}")
print(f"Weaknesses: {result['weaknesses']}")
print(f"Recommendations: {result['recommendations']}")
```

## Evaluation Pipelines

### Module 2 Pipeline

```python
from evaluation.pipelines.module2_eval import run_module2_evaluation
from module2.agent import analyze_repository

# Run evaluation with real agent
results = run_module2_evaluation(
    agent_function=analyze_repository,
    verbose=True,
)

# Results structure
{
    "summary": {
        "total_test_cases": 6,
        "average_score": 85.3,
        "pass_rate": 0.83,
        "criteria_scores": {
            "completeness": {"average": 88.2, "min": 75, "max": 95},
            "accuracy": {"average": 90.1, "min": 82, "max": 98},
            "actionability": {"average": 82.5, "min": 70, "max": 92},
            "safety_awareness": {"average": 80.7, "min": 65, "max": 90},
        }
    },
    "results": [...],  # Individual test case results
}
```

### Module 3 Pipeline

```python
from evaluation.pipelines.module3_eval import run_module3_evaluation
from module3.agent import generate_infrastructure

# Run evaluation with real agent
results = run_module3_evaluation(
    agent_function=generate_infrastructure,
    verbose=True,
)

# Results structure
{
    "summary": {
        "total_test_cases": 5,
        "average_combined_score": 87.5,
        "average_cdk_score": 85.0,
        "average_llm_score": 89.2,
        "pass_rate": 0.80,
        "syntax_valid_rate": 1.0,
    },
    "results": [...],
}
```

## Test Datasets

### Module 2 Test Cases

6 test cases covering:
- Simple single-service repositories
- Multi-service monorepos
- Repositories with existing IaC
- Ambiguous configurations
- Security issues

```python
from evaluation.datasets.module2_testcases import MODULE2_TEST_CASES

for test_case in MODULE2_TEST_CASES:
    print(f"{test_case['id']}: {test_case['name']}")
    print(f"  Category: {test_case['category']}")
    print(f"  Expected: {test_case['expected_output']}")
```

### Module 3 Test Cases

5 test cases covering:
- Simple web applications
- Serverless architectures
- Microservices patterns
- Data pipelines
- High availability configurations

```python
from evaluation.datasets.module3_testcases import MODULE3_TEST_CASES

for test_case in MODULE3_TEST_CASES:
    print(f"{test_case['id']}: {test_case['name']}")
    print(f"  Category: {test_case['category']}")
    print(f"  Required stacks: {test_case['expected_output']['stacks']}")
```

## ISV Partner Integrations

### Patronus AI - Custom Evaluation Criteria

```python
from evaluation.integrations.patronus_integration import PatronusEvaluator

evaluator = PatronusEvaluator(
    project_name="devops-companion",
    api_key="your-api-key",  # or set PATRONUS_API_KEY env var
)

# Create custom criterion
criterion = evaluator.create_custom_criteria(
    name="cdk_idempotency",
    description="CDK code can be deployed multiple times",
    scoring_rubric={
        "90-100": "Fully idempotent",
        "70-89": "Mostly idempotent",
        "50-69": "Some issues",
        "0-49": "Not idempotent",
    },
)

# Evaluate output
result = evaluator.evaluate(
    task="Generate ECS stack",
    output=cdk_code,
    criteria={"idempotency": "Code is idempotent"},
    metadata={"agent_version": "v1.0"},
)

# Track regression across versions
regression = evaluator.track_regression(
    agent_version="v1.1",
    evaluation_results=[result],
)
```

### Deepchecks - Hallucination Detection

```python
from evaluation.integrations.deepchecks_integration import DeepchecksEvaluator

evaluator = DeepchecksEvaluator(
    api_key="your-api-key",  # or set DEEPCHECKS_API_KEY env var
)

# Detect hallucinations
result = evaluator.detect_hallucinations(
    output=agent_output,
    context="Generate CDK stack",
    reference=expected_output,
)

print(f"Hallucinations detected: {result['hallucination_detected']}")
print(f"Hallucination score: {result['hallucination_score']}/100")

# Validate output quality
quality = evaluator.validate_output_quality(
    output=agent_output,
    expected_format="code",
)

# Run complete quality suite
suite_results = evaluator.run_quality_suite(
    output=agent_output,
    context=context,
    reference=reference,
    expected_format="code",
)
```

### Comet ML - Experiment Tracking

```python
from evaluation.integrations.cometml_integration import CometMLTracker

tracker = CometMLTracker(
    project_name="devops-companion-eval",
    api_key="your-api-key",  # or set COMET_API_KEY env var
)

# Start experiment
exp_id = tracker.start_experiment(
    experiment_name="module3-baseline",
    tags=["module3", "cdk-generation"],
    parameters={"agent_version": "v1.0", "model": "claude-sonnet-4"},
)

# Log metrics
tracker.log_metrics({
    "average_score": 88.5,
    "pass_rate": 0.92,
    "syntax_valid_rate": 1.0,
})

# Log evaluation results
from evaluation.pipelines.module3_eval import run_module3_evaluation
results = run_module3_evaluation()
tracker.log_evaluation_results(results, agent_version="v1.0")

# Detect anomalies
anomalies = tracker.detect_anomalies(
    metric_name="average_score",
    threshold=2.0,  # standard deviations
)

# End experiment
summary = tracker.end_experiment()
print(f"Dashboard: {summary['dashboard_url']}")
```

## Mock Mode

All ISV integrations include mock implementations for testing without API keys:

```python
# Mock mode is automatically enabled if no API key is provided
evaluator = PatronusEvaluator()  # No api_key
# → Prints: "[Patronus] Running in MOCK mode"

# Mock implementations return realistic data structures
result = evaluator.evaluate(...)
# → Returns mock scores and metadata
```

## CDK Code Evaluator

Automated CDK code quality assessment:

```python
from module3.evaluators.cdk_evaluator import evaluate_cdk_code

result = evaluate_cdk_code(
    cdk_code=generated_code,
    expected_resources=["VPC", "RDS", "ECS"],
)

print(f"Syntax valid: {result.syntax_valid}")
print(f"Completeness: {result.completeness_score}/100")
print(f"Best practices: {result.best_practices_score}/100")
print(f"Security: {result.security_score}/100")
print(f"Overall: {result.overall_score}/100")
print(f"Issues: {result.issues}")
print(f"Recommendations: {result.recommendations}")
```

## Metrics and Reporting

### Score Aggregation

```python
# Individual test case scores
test_scores = [85, 92, 78, 88, 95]

# Calculate summary statistics
average = sum(test_scores) / len(test_scores)
min_score = min(test_scores)
max_score = max(test_scores)
pass_rate = sum(1 for s in test_scores if s >= 70) / len(test_scores)

print(f"Average: {average:.1f}/100")
print(f"Range: {min_score}-{max_score}")
print(f"Pass Rate: {pass_rate*100:.1f}%")
```

### Regression Detection

```python
# Compare current version to baseline
baseline_scores = [85, 88, 90, 87, 92]
current_scores = [83, 85, 88, 84, 89]

baseline_avg = sum(baseline_scores) / len(baseline_scores)
current_avg = sum(current_scores) / len(current_scores)

regression = current_avg < baseline_avg - 5  # 5-point threshold

if regression:
    print(f"⚠️  Regression detected: {current_avg:.1f} < {baseline_avg:.1f}")
else:
    print(f"✓ No regression: {current_avg:.1f} vs {baseline_avg:.1f}")
```

## Project Structure

```
evaluation/
├── pipelines/
│   ├── module2_eval.py       # Module 2 evaluation pipeline
│   └── module3_eval.py       # Module 3 evaluation pipeline
├── datasets/
│   ├── module2_testcases.py  # Module 2 test cases
│   └── module3_testcases.py  # Module 3 test cases
├── integrations/
│   ├── patronus_integration.py    # Patronus AI
│   ├── deepchecks_integration.py  # Deepchecks
│   └── cometml_integration.py     # Comet ML
└── metrics/
    └── (future: custom metrics)
```

## Best Practices

1. **Run evaluation before merging**: Catch regressions early
2. **Track metrics over time**: Use Comet ML or similar
3. **Set quality thresholds**: e.g., 70% pass rate minimum
4. **Combine automated + manual**: LLM-as-judge + human review
5. **Version your test datasets**: Track changes to test cases
6. **Monitor hallucinations**: Use Deepchecks in production
7. **Create custom criteria**: Use Patronus for domain-specific evaluation

## Testing

```bash
# Run all evaluation tests
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py -v

# Test specific evaluator
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py::test_llm_judge_evaluation -v

# Test ISV integrations
AGENT_MOCK_REPO=true pytest tests/test_evaluation.py::test_patronus_evaluator_mock -v
```

## License

Part of the AI Agent Learning Series on AWS.
