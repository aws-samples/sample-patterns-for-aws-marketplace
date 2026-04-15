"""
module3/evaluators/cdk_evaluator.py
====================================
CDK code quality evaluator.

Evaluates generated CDK code for:
- Syntax correctness
- Completeness
- Best practices
- Security configurations
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class CDKEvaluationResult:
    """Result of CDK code evaluation."""
    
    syntax_valid: bool
    syntax_errors: list[dict[str, Any]]
    completeness_score: int  # 0-100
    best_practices_score: int  # 0-100
    security_score: int  # 0-100
    overall_score: int  # 0-100
    issues: list[str]
    recommendations: list[str]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "syntax_valid": self.syntax_valid,
            "syntax_errors": self.syntax_errors,
            "scores": {
                "completeness": self.completeness_score,
                "best_practices": self.best_practices_score,
                "security": self.security_score,
                "overall": self.overall_score,
            },
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


def evaluate_cdk_code(
    cdk_code: str,
    expected_resources: list[str] | None = None,
) -> CDKEvaluationResult:
    """
    Evaluate CDK code quality.

    Parameters
    ----------
    cdk_code : str
        CDK stack code to evaluate.
    expected_resources : list of str, optional
        List of expected AWS resources (e.g., ["VPC", "RDS", "ECS"]).

    Returns
    -------
    CDKEvaluationResult
        Evaluation results with scores and recommendations.

    Example
    -------
    >>> code = "from aws_cdk import Stack\\n..."
    >>> result = evaluate_cdk_code(code, expected_resources=["VPC", "RDS"])
    >>> print(result.overall_score)
    """
    issues = []
    recommendations = []
    
    # 1. Syntax validation
    syntax_valid = True
    syntax_errors = []
    try:
        ast.parse(cdk_code)
    except SyntaxError as e:
        syntax_valid = False
        syntax_errors.append({
            "line": e.lineno,
            "offset": e.offset,
            "message": e.msg,
            "text": e.text,
        })
        issues.append(f"Syntax error at line {e.lineno}: {e.msg}")
    
    # 2. Completeness check
    completeness_score = 100
    
    # Check for required imports
    required_imports = [
        "from aws_cdk import",
        "from constructs import Construct",
        "class",
        "Stack",
    ]
    for imp in required_imports:
        if imp not in cdk_code:
            completeness_score -= 15
            issues.append(f"Missing required import or declaration: {imp}")
    
    # Check for expected resources
    if expected_resources:
        for resource in expected_resources:
            if resource.lower() not in cdk_code.lower():
                completeness_score -= 10
                issues.append(f"Expected resource not found: {resource}")
    
    completeness_score = max(0, completeness_score)
    
    # 3. Best practices check
    best_practices_score = 100
    best_practices = {
        "docstring": '"""' in cdk_code or "'''" in cdk_code,
        "type_hints": "->" in cdk_code or ": " in cdk_code,
        "super_init": "super().__init__" in cdk_code,
        "construct_id": "construct_id" in cdk_code,
    }
    
    for practice, present in best_practices.items():
        if not present:
            best_practices_score -= 15
            recommendations.append(f"Consider adding {practice.replace('_', ' ')}")
    
    best_practices_score = max(0, best_practices_score)
    
    # 4. Security check
    security_score = 100
    security_checks = {
        "encryption": "encrypt" in cdk_code.lower(),
        "security_group": "security" in cdk_code.lower(),
        "iam": "iam" in cdk_code.lower() or "role" in cdk_code.lower(),
        "logging": "log" in cdk_code.lower(),
    }
    
    for check, present in security_checks.items():
        if not present:
            security_score -= 20
            recommendations.append(f"Consider adding {check.replace('_', ' ')} configuration")
    
    # Check for security anti-patterns
    if "block_public_access=False" in cdk_code.lower():
        security_score -= 30
        issues.append("Security issue: Public access enabled")
    
    if "deletion_protection=False" in cdk_code.lower():
        security_score -= 10
        recommendations.append("Consider enabling deletion protection for production")
    
    security_score = max(0, security_score)
    
    # 5. Calculate overall score
    if not syntax_valid:
        overall_score = 0
    else:
        overall_score = int(
            (completeness_score * 0.4) +
            (best_practices_score * 0.3) +
            (security_score * 0.3)
        )
    
    return CDKEvaluationResult(
        syntax_valid=syntax_valid,
        syntax_errors=syntax_errors,
        completeness_score=completeness_score,
        best_practices_score=best_practices_score,
        security_score=security_score,
        overall_score=overall_score,
        issues=issues,
        recommendations=recommendations,
    )


def evaluate_cdk_batch(
    code_samples: list[dict[str, Any]],
) -> list[CDKEvaluationResult]:
    """
    Evaluate multiple CDK code samples.

    Parameters
    ----------
    code_samples : list of dict
        List of samples, each with:
        - code: str
        - expected_resources: list of str (optional)

    Returns
    -------
    list of CDKEvaluationResult
        Evaluation results for each sample.
    """
    results = []
    
    for sample in code_samples:
        result = evaluate_cdk_code(
            cdk_code=sample["code"],
            expected_resources=sample.get("expected_resources"),
        )
        results.append(result)
    
    return results
