"""
evaluation/pipelines/module2_eval.py
=====================================
Evaluation pipeline for Module 2 Repository Analysis Agent.

Runs the agent against test cases and evaluates:
- Completeness: All services/dependencies identified
- Accuracy: Correct technology stack identification
- Actionability: Sufficient detail for CDK generation
- Safety Awareness: Security issues flagged
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from module3.evaluators.llm_judge import evaluate_with_llm_judge
from evaluation.datasets.module2_testcases import MODULE2_TEST_CASES, MODULE2_EVALUATION_CRITERIA


def run_module2_evaluation(
    test_cases: list[dict[str, Any]] | None = None,
    agent_function: Any | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run evaluation pipeline for Module 2 agent.

    Parameters
    ----------
    test_cases : list of dict, optional
        Test cases to evaluate. Defaults to MODULE2_TEST_CASES.
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
    >>> from module2.agent import analyze_repository
    >>> results = run_module2_evaluation(agent_function=analyze_repository)
    >>> print(f"Overall score: {results['summary']['average_score']}")
    """
    test_cases = test_cases or MODULE2_TEST_CASES
    mock_mode = agent_function is None
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"  MODULE 2 EVALUATION PIPELINE")
        print(f"{'='*70}")
        print(f"  Test cases: {len(test_cases)}")
        print(f"  Mode: {'MOCK' if mock_mode else 'LIVE'}")
        print(f"  Criteria: {len(MODULE2_EVALUATION_CRITERIA)}")
        print(f"{'='*70}\n")
    
    results = []
    
    for i, test_case in enumerate(test_cases):
        if verbose:
            print(f"\n[Test Case {i+1}/{len(test_cases)}] {test_case['name']}")
            print(f"  Category: {test_case['category']}")
        
        # Get agent output (mock or real)
        if mock_mode:
            agent_output = _generate_mock_module2_output(test_case)
        else:
            try:
                agent_output = agent_function(test_case["input"])
            except Exception as e:
                agent_output = f"ERROR: {str(e)}"
        
        # Evaluate with LLM-as-judge
        task_description = f"Analyze repository: {test_case['name']}\nInput: {json.dumps(test_case['input'], indent=2)}"
        
        evaluation = evaluate_with_llm_judge(
            task_description=task_description,
            agent_output=str(agent_output),
            criteria=MODULE2_EVALUATION_CRITERIA,
            reference_answer=json.dumps(test_case["expected_output"], indent=2),
            verbose=verbose,
        )
        
        # Store result
        result = {
            "test_case_id": test_case["id"],
            "test_case_name": test_case["name"],
            "category": test_case["category"],
            "agent_output": agent_output,
            "evaluation": evaluation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        results.append(result)
        
        if verbose:
            print(f"  Score: {evaluation.get('overall_score', 0)}/100")
    
    # Calculate summary statistics
    scores = [r["evaluation"].get("overall_score", 0) for r in results]
    criteria_scores = {}
    for criterion in MODULE2_EVALUATION_CRITERIA.keys():
        criterion_scores = [
            r["evaluation"].get("scores", {}).get(criterion, 0)
            for r in results
        ]
        criteria_scores[criterion] = {
            "average": sum(criterion_scores) / len(criterion_scores) if criterion_scores else 0,
            "min": min(criterion_scores) if criterion_scores else 0,
            "max": max(criterion_scores) if criterion_scores else 0,
        }
    
    summary = {
        "total_test_cases": len(test_cases),
        "average_score": sum(scores) / len(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "pass_rate": sum(1 for s in scores if s >= 70) / len(scores) if scores else 0,
        "criteria_scores": criteria_scores,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"  EVALUATION SUMMARY")
        print(f"{'='*70}")
        print(f"  Average Score: {summary['average_score']:.1f}/100")
        print(f"  Pass Rate: {summary['pass_rate']*100:.1f}%")
        print(f"  Score Range: {summary['min_score']:.0f} - {summary['max_score']:.0f}")
        print(f"\n  Criteria Scores:")
        for criterion, stats in criteria_scores.items():
            print(f"    {criterion}: {stats['average']:.1f}/100")
        print(f"{'='*70}\n")
    
    return {
        "summary": summary,
        "results": results,
        "test_cases": test_cases,
    }


def _generate_mock_module2_output(test_case: dict[str, Any]) -> dict[str, Any]:
    """Generate mock Module 2 output for testing."""
    expected = test_case["expected_output"]
    
    return {
        "repository": test_case["input"].get("repo_description", "mock-repo"),
        "applications": [
            {
                "name": "app",
                "languages": expected.get("languages", []),
                "frameworks": expected.get("frameworks", []),
            }
        ] * expected.get("applications", 1),
        "infrastructure_requirements": {
            "databases": expected.get("databases", []),
            "cache": expected.get("cache", []),
            "aws_services": expected.get("aws_services", []),
        },
        "security_issues": expected.get("security_issues_found", 0),
    }
