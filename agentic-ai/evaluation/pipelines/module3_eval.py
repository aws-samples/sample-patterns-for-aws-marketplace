"""
evaluation/pipelines/module3_eval.py
=====================================
Evaluation pipeline for Module 3 CDK Generation Agent.

Runs the agent against test cases and evaluates:
- Syntax Correctness: Valid Python CDK syntax
- Completeness: All required resources included
- Best Practices: Follows AWS and CDK best practices
- Security: Proper security configurations
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from module3.evaluators.llm_judge import evaluate_with_llm_judge
from module3.evaluators.cdk_evaluator import evaluate_cdk_code
from evaluation.datasets.module3_testcases import MODULE3_TEST_CASES, MODULE3_EVALUATION_CRITERIA


def run_module3_evaluation(
    test_cases: list[dict[str, Any]] | None = None,
    agent_function: Any | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run evaluation pipeline for Module 3 agent.

    Parameters
    ----------
    test_cases : list of dict, optional
        Test cases to evaluate. Defaults to MODULE3_TEST_CASES.
    agent_function : callable, optional
        Function to invoke the agent. If None, uses mock mode.
    verbose : bool
        Print evaluation progress.

    Returns
    -------
    dict
        Evaluation results with scores, pass/fail rates, and detailed results.

    Example
    -------
    >>> from module3.agent import generate_infrastructure
    >>> results = run_module3_evaluation(agent_function=generate_infrastructure)
    >>> print(f"Overall score: {results['summary']['average_score']}")
    """
    test_cases = test_cases or MODULE3_TEST_CASES
    mock_mode = agent_function is None
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"  MODULE 3 EVALUATION PIPELINE")
        print(f"{'='*70}")
        print(f"  Test cases: {len(test_cases)}")
        print(f"  Mode: {'MOCK' if mock_mode else 'LIVE'}")
        print(f"  Criteria: {len(MODULE3_EVALUATION_CRITERIA)}")
        print(f"{'='*70}\n")
    
    results = []
    
    for i, test_case in enumerate(test_cases):
        if verbose:
            print(f"\n[Test Case {i+1}/{len(test_cases)}] {test_case['name']}")
            print(f"  Category: {test_case['category']}")
        
        # Get agent output (mock or real)
        if mock_mode:
            agent_output = _generate_mock_module3_output(test_case)
        else:
            try:
                agent_output = agent_function(test_case["input"])
            except Exception as e:
                agent_output = f"ERROR: {str(e)}"
        
        # Extract CDK code from output
        cdk_code = _extract_cdk_code(agent_output)
        
        # Automated CDK evaluation
        cdk_eval = evaluate_cdk_code(
            cdk_code=cdk_code,
            expected_resources=test_case["expected_output"].get("resources", []),
        )
        
        # LLM-as-judge evaluation
        task_description = f"Generate CDK infrastructure: {test_case['name']}\nRequirements: {json.dumps(test_case['input'], indent=2)}"
        
        llm_evaluation = evaluate_with_llm_judge(
            task_description=task_description,
            agent_output=cdk_code,
            criteria=MODULE3_EVALUATION_CRITERIA,
            reference_answer=f"Expected stacks: {test_case['expected_output'].get('stacks', [])}",
            verbose=verbose,
        )
        
        # Combine evaluations
        combined_score = int(
            (cdk_eval.overall_score * 0.4) +
            (llm_evaluation.get("overall_score", 0) * 0.6)
        )
        
        # Store result
        result = {
            "test_case_id": test_case["id"],
            "test_case_name": test_case["name"],
            "category": test_case["category"],
            "cdk_code": cdk_code,
            "cdk_evaluation": cdk_eval.to_dict(),
            "llm_evaluation": llm_evaluation,
            "combined_score": combined_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        results.append(result)
        
        if verbose:
            print(f"  CDK Score: {cdk_eval.overall_score}/100")
            print(f"  LLM Score: {llm_evaluation.get('overall_score', 0)}/100")
            print(f"  Combined: {combined_score}/100")
    
    # Calculate summary statistics
    combined_scores = [r["combined_score"] for r in results]
    cdk_scores = [r["cdk_evaluation"]["scores"]["overall"] for r in results]
    llm_scores = [r["llm_evaluation"].get("overall_score", 0) for r in results]
    
    criteria_scores = {}
    for criterion in MODULE3_EVALUATION_CRITERIA.keys():
        criterion_scores = [
            r["llm_evaluation"].get("scores", {}).get(criterion, 0)
            for r in results
        ]
        criteria_scores[criterion] = {
            "average": sum(criterion_scores) / len(criterion_scores) if criterion_scores else 0,
            "min": min(criterion_scores) if criterion_scores else 0,
            "max": max(criterion_scores) if criterion_scores else 0,
        }
    
    summary = {
        "total_test_cases": len(test_cases),
        "average_combined_score": sum(combined_scores) / len(combined_scores) if combined_scores else 0,
        "average_cdk_score": sum(cdk_scores) / len(cdk_scores) if cdk_scores else 0,
        "average_llm_score": sum(llm_scores) / len(llm_scores) if llm_scores else 0,
        "pass_rate": sum(1 for s in combined_scores if s >= 70) / len(combined_scores) if combined_scores else 0,
        "syntax_valid_rate": sum(1 for r in results if r["cdk_evaluation"]["syntax_valid"]) / len(results) if results else 0,
        "criteria_scores": criteria_scores,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"  EVALUATION SUMMARY")
        print(f"{'='*70}")
        print(f"  Average Combined Score: {summary['average_combined_score']:.1f}/100")
        print(f"  Average CDK Score: {summary['average_cdk_score']:.1f}/100")
        print(f"  Average LLM Score: {summary['average_llm_score']:.1f}/100")
        print(f"  Pass Rate: {summary['pass_rate']*100:.1f}%")
        print(f"  Syntax Valid: {summary['syntax_valid_rate']*100:.1f}%")
        print(f"\n  Criteria Scores:")
        for criterion, stats in criteria_scores.items():
            print(f"    {criterion}: {stats['average']:.1f}/100")
        print(f"{'='*70}\n")
    
    return {
        "summary": summary,
        "results": results,
        "test_cases": test_cases,
    }


def _extract_cdk_code(output: Any) -> str:
    """Extract CDK code from agent output."""
    if isinstance(output, dict):
        # Try to find code in common keys
        for key in ["cdk_code", "code", "output", "stack"]:
            if key in output:
                return str(output[key])
        return str(output)
    return str(output)


def _generate_mock_module3_output(test_case: dict[str, Any]) -> str:
    """Generate mock Module 3 CDK output for testing."""
    expected = test_case["expected_output"]
    
    # Generate simple mock CDK code
    mock_code = f'''"""
Mock CDK Stack for {test_case['name']}
"""

from aws_cdk import Stack
from constructs import Construct

class MockStack(Stack):
    """Mock stack for testing."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Mock resources: {', '.join(expected.get('resources', []))}
        # Expected stacks: {', '.join(expected.get('stacks', []))}
'''
    
    return mock_code
