"""
evaluation/datasets/module2_testcases.py
=========================================
Test cases for Module 2 Repository Analysis Agent evaluation.

Each test case includes:
- Input: Repository path or description
- Expected output: What the agent should identify
- Evaluation criteria: How to score the output
"""

from __future__ import annotations

MODULE2_TEST_CASES = [
    # Simple single-service repositories
    {
        "id": "m2-001",
        "name": "Simple Node.js Express App",
        "category": "simple",
        "input": {
            "repo_description": "Node.js Express application with PostgreSQL database",
            "files": ["package.json", "server.js", "Dockerfile"],
            "dependencies": ["express", "pg", "dotenv"],
        },
        "expected_output": {
            "applications": 1,
            "languages": ["Node.js"],
            "frameworks": ["Express"],
            "databases": ["PostgreSQL"],
            "aws_services": ["ECS", "RDS", "VPC"],
        },
        "evaluation_criteria": {
            "completeness": "Identifies all services, dependencies, and infrastructure needs",
            "accuracy": "Correctly identifies Node.js, Express, and PostgreSQL",
            "actionability": "Provides sufficient detail for CDK generation",
            "safety_awareness": "Flags any security issues in dependencies or config",
        },
    },
    {
        "id": "m2-002",
        "name": "Python FastAPI with Redis",
        "category": "simple",
        "input": {
            "repo_description": "Python FastAPI application with Redis cache",
            "files": ["requirements.txt", "main.py", "Dockerfile"],
            "dependencies": ["fastapi", "redis", "uvicorn"],
        },
        "expected_output": {
            "applications": 1,
            "languages": ["Python"],
            "frameworks": ["FastAPI"],
            "cache": ["Redis"],
            "aws_services": ["ECS", "ElastiCache", "VPC"],
        },
        "evaluation_criteria": {
            "completeness": "Identifies FastAPI, Redis, and deployment needs",
            "accuracy": "Correctly maps dependencies to AWS services",
            "actionability": "Specifies runtime version and container requirements",
            "safety_awareness": "Notes any security configurations needed",
        },
    },
    
    # Multi-service repositories
    {
        "id": "m2-003",
        "name": "Microservices Monorepo",
        "category": "multi-service",
        "input": {
            "repo_description": "Monorepo with API service, worker service, and frontend",
            "files": [
                "services/api/package.json",
                "services/worker/requirements.txt",
                "frontend/package.json",
            ],
            "dependencies": {
                "api": ["express", "pg", "redis"],
                "worker": ["celery", "boto3"],
                "frontend": ["react", "axios"],
            },
        },
        "expected_output": {
            "applications": 3,
            "languages": ["Node.js", "Python", "JavaScript"],
            "frameworks": ["Express", "Celery", "React"],
            "databases": ["PostgreSQL"],
            "cache": ["Redis"],
            "aws_services": ["ECS", "RDS", "ElastiCache", "S3", "SQS", "CloudFront"],
        },
        "evaluation_criteria": {
            "completeness": "Identifies all three services and their dependencies",
            "accuracy": "Correctly distinguishes between API, worker, and frontend",
            "actionability": "Provides deployment strategy for each service type",
            "safety_awareness": "Identifies inter-service communication requirements",
        },
    },
    
    # Repositories with infrastructure-as-code
    {
        "id": "m2-004",
        "name": "App with Existing Terraform",
        "category": "existing-iac",
        "input": {
            "repo_description": "Application with existing Terraform configuration",
            "files": [
                "app/package.json",
                "terraform/main.tf",
                "terraform/variables.tf",
            ],
            "dependencies": ["express", "mysql"],
            "terraform_resources": ["aws_ecs_cluster", "aws_rds_instance"],
        },
        "expected_output": {
            "applications": 1,
            "existing_infrastructure": ["ECS", "RDS"],
            "infrastructure_gaps": [],
            "migration_needed": False,
        },
        "evaluation_criteria": {
            "completeness": "Identifies existing infrastructure and application needs",
            "accuracy": "Correctly parses Terraform resources",
            "actionability": "Recommends whether to extend or replace existing IaC",
            "safety_awareness": "Notes any infrastructure security issues",
        },
    },
    
    # Ambiguous configurations
    {
        "id": "m2-005",
        "name": "Ambiguous Database Configuration",
        "category": "ambiguous",
        "input": {
            "repo_description": "App with multiple database drivers installed",
            "files": ["package.json", ".env.example"],
            "dependencies": ["pg", "mysql2", "mongodb"],
            "env_vars": ["DATABASE_URL"],
        },
        "expected_output": {
            "applications": 1,
            "databases_unclear": True,
            "clarification_needed": ["Which database is actually used?"],
        },
        "evaluation_criteria": {
            "completeness": "Identifies all potential databases",
            "accuracy": "Recognizes ambiguity rather than guessing",
            "actionability": "Asks specific clarifying questions",
            "safety_awareness": "Notes potential for unused dependencies",
        },
    },
    
    # Security issues
    {
        "id": "m2-006",
        "name": "Repository with Security Issues",
        "category": "security",
        "input": {
            "repo_description": "Application with exposed credentials",
            "files": [".env", "config.json", "package.json"],
            "security_issues": [
                "Hardcoded API key in config.json",
                "Database password in .env committed to git",
            ],
        },
        "expected_output": {
            "applications": 1,
            "security_issues_found": 2,
            "recommendations": [
                "Move secrets to AWS Secrets Manager",
                "Add .env to .gitignore",
            ],
        },
        "evaluation_criteria": {
            "completeness": "Identifies application structure despite security issues",
            "accuracy": "Correctly identifies technology stack",
            "actionability": "Provides clear infrastructure requirements",
            "safety_awareness": "Flags all security issues and provides remediation",
        },
    },
]

# Evaluation criteria descriptions for Module 2
MODULE2_EVALUATION_CRITERIA = {
    "completeness": "Does the analysis identify all applications, services, dependencies, and infrastructure requirements present in the repository?",
    "accuracy": "Are the identified technologies, frameworks, versions, and dependencies correct?",
    "actionability": "Does the analysis provide enough detail for the CDK generation agent (Module 3) to create infrastructure without additional questions?",
    "safety_awareness": "Does the analysis flag security-relevant characteristics such as exposed credentials, vulnerable dependencies, or insecure configurations?",
}
