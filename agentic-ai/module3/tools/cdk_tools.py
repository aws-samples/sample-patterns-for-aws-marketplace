"""
module3/tools/cdk_tools.py
==========================
CDK generation and validation tools for Module 3.

These tools enable the agent to:
1. Parse infrastructure requirements from Module 2 output
2. Generate CDK stack code for AWS services
3. Validate generated CDK syntax
4. List available CDK constructs
5. Generate test files for CDK stacks

DESIGN PRINCIPLES
-----------------
- Generate production-ready CDK code
- Follow AWS best practices
- Support mock mode for testing
- Validate syntax before returning
- Include comprehensive documentation
"""

from __future__ import annotations

import ast
import json
import os
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool

from module3.templates.cdk_patterns import (
    generate_vpc_stack,
    generate_ecs_stack,
    generate_rds_stack,
    generate_elasticache_stack,
    generate_s3_stack,
    generate_lambda_stack,
)

# Mock mode flag
_MOCK = os.getenv("AGENT_MOCK_REPO", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _wrap(data: Any, tool_name: str) -> str:
    """Wrap tool output in consistent JSON envelope."""
    return json.dumps(
        {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mock_mode": _MOCK,
            "data": data,
        },
        indent=2,
        default=str,
    )


def _validate_python_syntax(code: str) -> dict[str, Any]:
    """Validate Python syntax using AST parsing."""
    try:
        ast.parse(code)
        return {
            "valid": True,
            "errors": [],
        }
    except SyntaxError as e:
        return {
            "valid": False,
            "errors": [
                {
                    "line": e.lineno,
                    "offset": e.offset,
                    "message": e.msg,
                    "text": e.text,
                }
            ],
        }


# ---------------------------------------------------------------------------
# Mock Data
# ---------------------------------------------------------------------------

MOCK_MODULE2_OUTPUT = {
    "repository": "/mock/repo/nodejs-app",
    "applications": [
        {
            "name": "api-service",
            "path": "services/api",
            "stack": {
                "language": "Node.js",
                "runtime": "18.x",
                "framework": "Express",
                "dependencies": ["pg", "redis", "aws-sdk"],
            },
            "aws_requirements": {
                "compute": "ECS Fargate",
                "database": "RDS PostgreSQL",
                "cache": "ElastiCache Redis",
                "storage": "S3",
                "networking": "VPC, ALB",
            },
        }
    ],
    "summary": {
        "total_applications": 1,
        "languages": ["Node.js"],
        "aws_services_needed": ["ECS", "RDS", "ElastiCache", "S3", "VPC", "ALB"],
    },
}


# ---------------------------------------------------------------------------
# Tool 1: Analyze Infrastructure Requirements
# ---------------------------------------------------------------------------

@tool
def analyze_infrastructure_requirements(requirements: str) -> str:
    """
    Parse infrastructure requirements from Module 2 output or user specifications.

    This tool analyzes the infrastructure requirements and extracts:
    - Required AWS services (compute, database, cache, storage)
    - Technology stack details (languages, frameworks, runtimes)
    - Deployment patterns (containers, serverless, etc.)
    - Networking requirements (VPC, load balancers)

    Args:
        requirements: JSON string from Module 2 or plain text requirements

    Returns:
        JSON string with parsed requirements and recommended CDK stacks
    """
    if _MOCK:
        # Return mock parsed requirements
        result = {
            "parsed_requirements": {
                "compute": {
                    "type": "ECS Fargate",
                    "container_port": 3000,
                    "desired_count": 2,
                    "memory": 512,
                    "cpu": 256,
                },
                "database": {
                    "type": "RDS PostgreSQL",
                    "engine": "postgres",
                    "version": "15.4",
                    "multi_az": True,
                },
                "cache": {
                    "type": "ElastiCache Redis",
                    "engine_version": "7.0",
                    "node_type": "cache.t3.micro",
                },
                "storage": {
                    "type": "S3",
                    "versioned": True,
                },
                "networking": {
                    "vpc": True,
                    "load_balancer": "ALB",
                    "max_azs": 2,
                },
            },
            "recommended_stacks": [
                "VpcStack - VPC with public/private subnets",
                "RdsStack - PostgreSQL database",
                "ElastiCacheStack - Redis cluster",
                "S3Stack - Object storage bucket",
                "EcsStack - Fargate service with ALB",
            ],
            "questions_needed": [
                "What AWS region should this be deployed to?",
                "What environment is this for (dev/staging/prod)?",
                "Do you need deletion protection on the database?",
            ],
        }
        return _wrap(result, "analyze_infrastructure_requirements")

    # Real implementation would parse JSON or text requirements
    try:
        # Try to parse as JSON first (Module 2 output)
        req_data = json.loads(requirements)
        
        # Extract AWS requirements
        aws_reqs = {}
        if "applications" in req_data and req_data["applications"]:
            app = req_data["applications"][0]
            aws_reqs = app.get("aws_requirements", {})
        
        # Parse into structured format
        parsed = {
            "parsed_requirements": aws_reqs,
            "recommended_stacks": [],
            "questions_needed": [
                "What AWS region should this be deployed to?",
                "What environment is this for (dev/staging/prod)?",
            ],
        }
        
        return _wrap(parsed, "analyze_infrastructure_requirements")
        
    except json.JSONDecodeError:
        # Plain text requirements - return basic parsing
        result = {
            "parsed_requirements": {"raw_text": requirements},
            "recommended_stacks": [],
            "questions_needed": [
                "Please provide more specific details about required AWS services",
            ],
        }
        return _wrap(result, "analyze_infrastructure_requirements")


# ---------------------------------------------------------------------------
# Tool 2: Generate CDK Stack
# ---------------------------------------------------------------------------

@tool
def generate_cdk_stack(
    stack_type: str,
    parameters: str,
) -> str:
    """
    Generate CDK stack code for a specific AWS service.

    Supported stack types:
    - vpc: VPC with public/private subnets
    - ecs: ECS Fargate service with ALB
    - rds: RDS database (PostgreSQL, MySQL)
    - elasticache: ElastiCache Redis cluster
    - s3: S3 bucket with encryption
    - lambda: Lambda function

    Args:
        stack_type: Type of stack to generate (vpc, ecs, rds, elasticache, s3, lambda)
        parameters: JSON string with stack-specific parameters

    Returns:
        JSON string with generated CDK code and metadata
    """
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError:
        params = {}

    stack_type = stack_type.lower()
    
    # Generate stack based on type
    if stack_type == "vpc":
        code = generate_vpc_stack(
            max_azs=params.get("max_azs", 2),
            nat_gateways=params.get("nat_gateways", 1),
        )
    elif stack_type == "ecs":
        code = generate_ecs_stack(
            service_name=params.get("service_name", "app"),
            container_name=params.get("container_name", "app-container"),
            image=params.get("image", "nginx:latest"),
            container_port=params.get("container_port", 80),
            memory=params.get("memory", 512),
            cpu=params.get("cpu", 256),
            desired_count=params.get("desired_count", 2),
            environment=params.get("environment"),
        )
    elif stack_type == "rds":
        code = generate_rds_stack(
            engine=params.get("engine", "POSTGRES"),
            version=params.get("version", "VER_15_4"),
            instance_class=params.get("instance_class", "BURSTABLE3"),
            instance_size=params.get("instance_size", "SMALL"),
            multi_az=params.get("multi_az", True),
            allocated_storage=params.get("allocated_storage", 20),
            backup_retention=params.get("backup_retention", 7),
            deletion_protection=params.get("deletion_protection", True),
        )
    elif stack_type == "elasticache":
        code = generate_elasticache_stack(
            description=params.get("description", "Redis cache cluster"),
            engine_version=params.get("engine_version", "7.0"),
            node_type=params.get("node_type", "cache.t3.micro"),
            num_nodes=params.get("num_nodes", 2),
            automatic_failover=params.get("automatic_failover", True),
            multi_az=params.get("multi_az", True),
        )
    elif stack_type == "s3":
        code = generate_s3_stack(
            bucket_name=params.get("bucket_name"),
            versioned=params.get("versioned", True),
            removal_policy=params.get("removal_policy", "RETAIN"),
            auto_delete=params.get("auto_delete", False),
        )
    elif stack_type == "lambda":
        code = generate_lambda_stack(
            runtime=params.get("runtime", "PYTHON_3_11"),
            handler=params.get("handler", "index.handler"),
            code_path=params.get("code_path", "lambda"),
            memory_size=params.get("memory_size", 128),
            timeout=params.get("timeout", 30),
            environment=params.get("environment"),
        )
    else:
        return _wrap(
            {
                "error": f"Unknown stack type: {stack_type}",
                "supported_types": ["vpc", "ecs", "rds", "elasticache", "s3", "lambda"],
            },
            "generate_cdk_stack",
        )

    # Validate syntax
    validation = _validate_python_syntax(code)

    result = {
        "stack_type": stack_type,
        "parameters": params,
        "code": code,
        "syntax_valid": validation["valid"],
        "syntax_errors": validation["errors"],
        "required_packages": [
            "aws-cdk-lib>=2.100.0",
            "constructs>=10.0.0",
        ],
        "deployment_command": "cdk deploy",
    }

    return _wrap(result, "generate_cdk_stack")


# ---------------------------------------------------------------------------
# Tool 3: Validate CDK Syntax
# ---------------------------------------------------------------------------

@tool
def validate_cdk_syntax(cdk_code: str) -> str:
    """
    Validate CDK stack code for syntax errors and best practices.

    Checks:
    - Python syntax validity
    - Required imports present
    - CDK patterns followed
    - Security best practices

    Args:
        cdk_code: CDK stack code to validate

    Returns:
        JSON string with validation results
    """
    # Syntax validation
    syntax_check = _validate_python_syntax(cdk_code)

    # Check for required imports
    required_imports = [
        "from aws_cdk import",
        "from constructs import Construct",
        "class",
        "Stack",
    ]
    
    missing_imports = []
    for imp in required_imports:
        if imp not in cdk_code:
            missing_imports.append(imp)

    # Check for best practices
    best_practice_checks = {
        "encryption": "encrypt" in cdk_code.lower(),
        "multi_az": "multi_az" in cdk_code.lower() or "multi-az" in cdk_code.lower(),
        "backup": "backup" in cdk_code.lower() or "retention" in cdk_code.lower(),
        "security_group": "security" in cdk_code.lower(),
        "logging": "log" in cdk_code.lower(),
    }

    issues = []
    if not best_practice_checks["encryption"]:
        issues.append("Consider enabling encryption for data at rest")
    if not best_practice_checks["security_group"]:
        issues.append("Consider adding security group configurations")

    result = {
        "status": "PASS" if syntax_check["valid"] and not missing_imports else "FAIL",
        "syntax": {
            "valid": syntax_check["valid"],
            "errors": syntax_check["errors"],
        },
        "imports": {
            "complete": len(missing_imports) == 0,
            "missing": missing_imports,
        },
        "best_practices": {
            "checks": best_practice_checks,
            "issues": issues,
        },
        "recommendations": [
            "Ensure all resources have proper tags for cost allocation",
            "Add CloudWatch alarms for critical resources",
            "Use L2 constructs when available for better defaults",
        ] if not issues else issues,
    }

    return _wrap(result, "validate_cdk_syntax")


# ---------------------------------------------------------------------------
# Tool 4: List Available Constructs
# ---------------------------------------------------------------------------

@tool
def list_available_constructs(service: str) -> str:
    """
    List available CDK constructs for a specific AWS service.

    Args:
        service: AWS service name (ec2, ecs, rds, s3, lambda, etc.)

    Returns:
        JSON string with available constructs and their descriptions
    """
    constructs_db = {
        "ec2": [
            {"name": "Vpc", "level": "L2", "description": "VPC with subnets and routing"},
            {"name": "SecurityGroup", "level": "L2", "description": "Security group for network access control"},
            {"name": "Instance", "level": "L2", "description": "EC2 instance"},
            {"name": "SubnetSelection", "level": "L2", "description": "Subnet selection criteria"},
        ],
        "ecs": [
            {"name": "Cluster", "level": "L2", "description": "ECS cluster"},
            {"name": "FargateTaskDefinition", "level": "L2", "description": "Fargate task definition"},
            {"name": "FargateService", "level": "L2", "description": "Fargate service"},
            {"name": "ContainerImage", "level": "L2", "description": "Container image reference"},
        ],
        "rds": [
            {"name": "DatabaseInstance", "level": "L2", "description": "RDS database instance"},
            {"name": "DatabaseCluster", "level": "L2", "description": "RDS Aurora cluster"},
            {"name": "DatabaseInstanceEngine", "level": "L2", "description": "Database engine configuration"},
        ],
        "elasticache": [
            {"name": "CfnReplicationGroup", "level": "L1", "description": "Redis replication group"},
            {"name": "CfnCacheCluster", "level": "L1", "description": "Cache cluster"},
            {"name": "CfnSubnetGroup", "level": "L1", "description": "Subnet group for cache"},
        ],
        "s3": [
            {"name": "Bucket", "level": "L2", "description": "S3 bucket"},
            {"name": "BucketEncryption", "level": "L2", "description": "Bucket encryption configuration"},
            {"name": "BlockPublicAccess", "level": "L2", "description": "Block public access settings"},
        ],
        "lambda": [
            {"name": "Function", "level": "L2", "description": "Lambda function"},
            {"name": "Runtime", "level": "L2", "description": "Lambda runtime configuration"},
            {"name": "Code", "level": "L2", "description": "Lambda code source"},
        ],
        "elbv2": [
            {"name": "ApplicationLoadBalancer", "level": "L2", "description": "Application Load Balancer"},
            {"name": "NetworkLoadBalancer", "level": "L2", "description": "Network Load Balancer"},
            {"name": "HealthCheck", "level": "L2", "description": "Health check configuration"},
        ],
    }

    service_lower = service.lower()
    constructs = constructs_db.get(service_lower, [])

    if not constructs:
        result = {
            "service": service,
            "constructs": [],
            "message": f"No constructs found for service: {service}",
            "available_services": list(constructs_db.keys()),
        }
    else:
        result = {
            "service": service,
            "constructs": constructs,
            "total": len(constructs),
            "documentation": f"https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_{service_lower}.html",
        }

    return _wrap(result, "list_available_constructs")


# ---------------------------------------------------------------------------
# Tool 5: Generate CDK Tests
# ---------------------------------------------------------------------------

@tool
def generate_cdk_tests(stack_name: str, stack_type: str) -> str:
    """
    Generate test file for a CDK stack.

    Creates pytest tests that verify:
    - Stack synthesizes without errors
    - Required resources are created
    - Security configurations are correct

    Args:
        stack_name: Name of the stack class (e.g., "VpcStack")
        stack_type: Type of stack (vpc, ecs, rds, etc.)

    Returns:
        JSON string with generated test code
    """
    test_template = f'''"""
Test suite for {stack_name}.
"""

import aws_cdk as cdk
from aws_cdk.assertions import Template, Match


def test_{stack_type}_stack_synthesizes():
    """Test that the stack synthesizes without errors."""
    app = cdk.App()
    stack = {stack_name}(app, "test-stack")
    template = Template.from_stack(stack)
    
    # Stack should synthesize successfully
    assert template is not None


def test_{stack_type}_stack_has_required_resources():
    """Test that required resources are created."""
    app = cdk.App()
    stack = {stack_name}(app, "test-stack")
    template = Template.from_stack(stack)
    
    # Add resource-specific assertions here
    # Example: template.resource_count_is("AWS::EC2::VPC", 1)


def test_{stack_type}_stack_security_configuration():
    """Test security configurations."""
    app = cdk.App()
    stack = {stack_name}(app, "test-stack")
    template = Template.from_stack(stack)
    
    # Add security-specific assertions here
    # Example: Check encryption is enabled
'''

    result = {
        "stack_name": stack_name,
        "stack_type": stack_type,
        "test_code": test_template,
        "test_file_name": f"test_{stack_type}_stack.py",
        "required_packages": [
            "pytest>=7.0.0",
            "aws-cdk-lib>=2.100.0",
        ],
        "run_command": f"pytest test_{stack_type}_stack.py -v",
    }

    return _wrap(result, "generate_cdk_tests")


# ---------------------------------------------------------------------------
# Export all tools
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    analyze_infrastructure_requirements,
    generate_cdk_stack,
    validate_cdk_syntax,
    list_available_constructs,
    generate_cdk_tests,
]
