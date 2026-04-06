"""
module4/mock/agent_mocks.py
============================
Mock responses from Modules 1-3 for demo mode.

These simulate realistic agent outputs without requiring running agent
servers or AWS credentials. Used when AGENT_MOCK_MODE=true.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Module 1 — Infrastructure Agent Mock Responses
# ---------------------------------------------------------------------------

def mock_module1_health_check(region: str = "us-east-1", **kwargs) -> dict:
    """Mock Module 1 health check response."""
    return {
        "agent": "module1",
        "task": "health_check",
        "timestamp": _timestamp(),
        "region": region,
        "data": {
            "environment_summary": {
                "region": region,
                "total_services": 4,
                "healthy": 2,
                "degraded": 2,
                "critical": 0,
            },
            "services": [
                {
                    "name": "api-gateway-svc",
                    "type": "ECS",
                    "status": "healthy",
                    "tasks_running": 3,
                    "tasks_desired": 3,
                    "findings": [],
                },
                {
                    "name": "notification-svc",
                    "type": "ECS",
                    "status": "degraded",
                    "tasks_running": 1,
                    "tasks_desired": 2,
                    "findings": [
                        "Container exit code 137 (OOMKilled)",
                        "Memory utilization at 95% before crash",
                    ],
                },
                {
                    "name": "prod-postgres-01",
                    "type": "RDS",
                    "status": "healthy",
                    "multi_az": True,
                    "findings": [],
                },
                {
                    "name": "reporting-mysql",
                    "type": "RDS",
                    "status": "degraded",
                    "multi_az": False,
                    "findings": [
                        "Single-AZ deployment — no failover capability",
                        "Storage at 78% capacity",
                    ],
                },
            ],
            "recommendations": [
                "Increase notification-svc memory limits to prevent OOM",
                "Enable Multi-AZ for reporting-mysql database",
                "Add CloudWatch alarms for storage capacity",
            ],
        },
    }


def mock_module1_list_resources(region: str = "us-east-1", **kwargs) -> dict:
    """Mock Module 1 list resources response."""
    return {
        "agent": "module1",
        "task": "list_resources",
        "timestamp": _timestamp(),
        "region": region,
        "data": {
            "ecs_services": ["api-gateway-svc", "notification-svc"],
            "rds_instances": ["prod-postgres-01", "reporting-mysql"],
            "ec2_instances": [],
            "lambda_functions": ["log-processor", "alert-handler"],
            "total_resources": 6,
        },
    }


# ---------------------------------------------------------------------------
# Module 2 — Repository Analysis Agent Mock Responses
# ---------------------------------------------------------------------------

def mock_module2_analyze_repo(repo_path: str = "/mock/repo/nodejs-app", **kwargs) -> dict:
    """Mock Module 2 repository analysis response."""
    return {
        "agent": "module2",
        "task": "analyze_repository",
        "timestamp": _timestamp(),
        "data": {
            "repository": repo_path,
            "applications": [
                {
                    "name": "api-service",
                    "path": "services/api",
                    "stack": {
                        "language": "Node.js",
                        "runtime": "18.x",
                        "framework": "Express",
                        "dependencies": ["pg", "redis", "aws-sdk", "express", "cors"],
                    },
                    "aws_requirements": {
                        "compute": "ECS Fargate",
                        "database": "RDS PostgreSQL",
                        "cache": "ElastiCache Redis",
                        "storage": "S3",
                        "networking": "VPC, ALB",
                    },
                },
                {
                    "name": "worker-service",
                    "path": "services/worker",
                    "stack": {
                        "language": "Python",
                        "runtime": "3.11",
                        "framework": "Celery",
                        "dependencies": ["celery", "redis", "boto3", "psycopg2"],
                    },
                    "aws_requirements": {
                        "compute": "ECS Fargate",
                        "queue": "SQS",
                        "cache": "ElastiCache Redis",
                    },
                },
            ],
            "summary": {
                "total_applications": 2,
                "languages": ["Node.js", "Python"],
                "aws_services_needed": [
                    "ECS Fargate", "RDS PostgreSQL", "ElastiCache Redis",
                    "S3", "VPC", "ALB", "SQS",
                ],
            },
        },
    }


def mock_module2_scan_structure(repo_path: str = "/mock/repo/nodejs-app", **kwargs) -> dict:
    """Mock Module 2 scan structure response."""
    return {
        "agent": "module2",
        "task": "scan_structure",
        "timestamp": _timestamp(),
        "data": {
            "repository": repo_path,
            "total_files": 47,
            "languages_detected": ["JavaScript", "Python", "YAML"],
            "config_files": [
                "package.json",
                "requirements.txt",
                "docker-compose.yml",
                "Dockerfile",
            ],
            "structure": {
                "services/api/": "Node.js Express API",
                "services/worker/": "Python Celery worker",
                "infra/": "Infrastructure configuration",
                "tests/": "Test suites",
            },
        },
    }


# ---------------------------------------------------------------------------
# Module 3 — CDK Generation Agent Mock Responses
# ---------------------------------------------------------------------------

def mock_module3_analyze_requirements(**kwargs) -> dict:
    """Mock Module 3 analyze requirements response."""
    return {
        "agent": "module3",
        "task": "analyze_requirements",
        "timestamp": _timestamp(),
        "data": {
            "parsed_requirements": {
                "compute": "ECS Fargate",
                "database": "RDS PostgreSQL",
                "cache": "ElastiCache Redis",
                "networking": "VPC with ALB",
            },
            "recommended_stacks": [
                "VpcStack — VPC with public/private subnets",
                "RdsStack — PostgreSQL database",
                "ElastiCacheStack — Redis cluster",
                "EcsStack — Fargate service with ALB",
            ],
            "questions": [],
        },
    }


def mock_module3_generate_cdk(requirements: dict | None = None, **kwargs) -> dict:
    """Mock Module 3 CDK generation response."""
    return {
        "agent": "module3",
        "task": "generate_cdk",
        "timestamp": _timestamp(),
        "data": {
            "stacks_generated": [
                {
                    "name": "VpcStack",
                    "type": "vpc",
                    "resources": ["VPC", "Public Subnets", "Private Subnets", "NAT Gateway"],
                    "status": "generated",
                    "syntax_valid": True,
                },
                {
                    "name": "RdsStack",
                    "type": "rds",
                    "resources": ["RDS PostgreSQL", "Security Group", "Subnet Group"],
                    "status": "generated",
                    "syntax_valid": True,
                },
                {
                    "name": "ElastiCacheStack",
                    "type": "elasticache",
                    "resources": ["Redis Cluster", "Subnet Group", "Security Group"],
                    "status": "generated",
                    "syntax_valid": True,
                },
                {
                    "name": "EcsApiStack",
                    "type": "ecs",
                    "resources": ["ECS Cluster", "Fargate Service", "ALB", "Target Group"],
                    "status": "generated",
                    "syntax_valid": True,
                },
                {
                    "name": "EcsWorkerStack",
                    "type": "ecs",
                    "resources": ["Fargate Service", "SQS Queue", "IAM Role"],
                    "status": "generated",
                    "syntax_valid": True,
                },
            ],
            "total_stacks": 5,
            "all_syntax_valid": True,
            "evaluation_score": 88,
            "deployment_order": [
                "VpcStack",
                "RdsStack",
                "ElastiCacheStack",
                "EcsApiStack",
                "EcsWorkerStack",
            ],
        },
    }


def mock_module3_validate(stack_name: str = "VpcStack", **kwargs) -> dict:
    """Mock Module 3 validation response."""
    return {
        "agent": "module3",
        "task": "validate_cdk",
        "timestamp": _timestamp(),
        "data": {
            "stack_name": stack_name,
            "status": "PASS",
            "syntax_valid": True,
            "best_practices": {
                "encryption": True,
                "multi_az": True,
                "backup": True,
                "security_group": True,
                "logging": True,
            },
            "score": 92,
        },
    }


# ---------------------------------------------------------------------------
# Convenience — get mock response by agent and task
# ---------------------------------------------------------------------------

MOCK_HANDLERS = {
    ("module1", "health_check"): mock_module1_health_check,
    ("module1", "list_resources"): mock_module1_list_resources,
    ("module2", "analyze_repository"): mock_module2_analyze_repo,
    ("module2", "scan_structure"): mock_module2_scan_structure,
    ("module3", "analyze_requirements"): mock_module3_analyze_requirements,
    ("module3", "generate_cdk"): mock_module3_generate_cdk,
    ("module3", "validate_cdk"): mock_module3_validate,
}


def get_mock_response(agent: str, task: str, **kwargs) -> dict:
    """
    Get a mock response for a given agent and task.

    Parameters
    ----------
    agent : str
        Agent identifier (module1, module2, module3).
    task : str
        Task type (health_check, analyze_repository, generate_cdk, etc.).
    **kwargs
        Additional parameters passed to the mock handler.

    Returns
    -------
    dict
        Mock response matching the agent's real output format.
    """
    handler = MOCK_HANDLERS.get((agent, task))
    if handler:
        return handler(**kwargs)

    return {
        "agent": agent,
        "task": task,
        "timestamp": _timestamp(),
        "data": {"error": f"No mock handler for {agent}/{task}"},
    }
