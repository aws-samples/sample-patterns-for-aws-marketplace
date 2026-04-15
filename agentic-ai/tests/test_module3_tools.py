"""
tests/test_module3_tools.py
============================
Tests for Module 3 CDK generation tools.
"""

import json
import os
import pytest

# Set mock mode for testing
os.environ["AGENT_MOCK_REPO"] = "true"

from module3.tools.cdk_tools import (
    analyze_infrastructure_requirements,
    generate_cdk_stack,
    validate_cdk_syntax,
    list_available_constructs,
    generate_cdk_tests,
)


def test_analyze_infrastructure_requirements_mock():
    """Test infrastructure requirements analysis in mock mode."""
    requirements = json.dumps({
        "compute": "ECS Fargate",
        "database": "RDS PostgreSQL",
    })
    
    result = analyze_infrastructure_requirements.func(requirements)
    data = json.loads(result)
    
    assert data["tool"] == "analyze_infrastructure_requirements"
    assert data["mock_mode"] is True
    assert "parsed_requirements" in data["data"]
    assert "recommended_stacks" in data["data"]


def test_generate_cdk_stack_vpc():
    """Test VPC stack generation."""
    parameters = json.dumps({"max_azs": 2, "nat_gateways": 1})
    
    result = generate_cdk_stack.func("vpc", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "vpc"
    assert data["data"]["syntax_valid"] is True
    assert "from aws_cdk import" in data["data"]["code"]
    assert "class VpcStack" in data["data"]["code"]


def test_generate_cdk_stack_rds():
    """Test RDS stack generation."""
    parameters = json.dumps({
        "engine": "POSTGRES",
        "multi_az": True,
    })
    
    result = generate_cdk_stack.func("rds", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "rds"
    assert data["data"]["syntax_valid"] is True
    assert "DatabaseInstance" in data["data"]["code"]


def test_generate_cdk_stack_ecs():
    """Test ECS stack generation."""
    parameters = json.dumps({
        "service_name": "api",
        "container_port": 3000,
    })
    
    result = generate_cdk_stack.func("ecs", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "ecs"
    assert "FargateService" in data["data"]["code"]


def test_generate_cdk_stack_elasticache():
    """Test ElastiCache stack generation."""
    parameters = json.dumps({
        "engine_version": "7.0",
        "num_nodes": 2,
    })
    
    result = generate_cdk_stack.func("elasticache", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "elasticache"
    assert "CfnReplicationGroup" in data["data"]["code"]


def test_generate_cdk_stack_s3():
    """Test S3 stack generation."""
    parameters = json.dumps({
        "versioned": True,
    })
    
    result = generate_cdk_stack.func("s3", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "s3"
    assert "Bucket" in data["data"]["code"]


def test_generate_cdk_stack_lambda():
    """Test Lambda stack generation."""
    parameters = json.dumps({
        "runtime": "PYTHON_3_11",
        "memory_size": 256,
    })
    
    result = generate_cdk_stack.func("lambda", parameters)
    data = json.loads(result)
    
    assert data["data"]["stack_type"] == "lambda"
    assert "Function" in data["data"]["code"]


def test_generate_cdk_stack_unknown_type():
    """Test handling of unknown stack type."""
    result = generate_cdk_stack.func("unknown_type", "{}")
    data = json.loads(result)
    
    assert "error" in data["data"]


def test_validate_cdk_syntax_valid():
    """Test validation of valid CDK code."""
    valid_code = """
from aws_cdk import Stack
from constructs import Construct

class TestStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
"""
    
    result = validate_cdk_syntax.func(valid_code)
    data = json.loads(result)
    
    assert data["data"]["status"] == "PASS"
    assert data["data"]["syntax"]["valid"] is True


def test_validate_cdk_syntax_invalid():
    """Test validation of invalid CDK code."""
    invalid_code = "def broken syntax here"
    
    result = validate_cdk_syntax.func(invalid_code)
    data = json.loads(result)
    
    assert data["data"]["status"] == "FAIL"
    assert data["data"]["syntax"]["valid"] is False


def test_list_available_constructs_ec2():
    """Test listing EC2 constructs."""
    result = list_available_constructs.func("ec2")
    data = json.loads(result)
    
    assert data["data"]["service"] == "ec2"
    assert len(data["data"]["constructs"]) > 0
    assert any(c["name"] == "Vpc" for c in data["data"]["constructs"])


def test_list_available_constructs_ecs():
    """Test listing ECS constructs."""
    result = list_available_constructs.func("ecs")
    data = json.loads(result)
    
    assert data["data"]["service"] == "ecs"
    assert any(c["name"] == "Cluster" for c in data["data"]["constructs"])


def test_list_available_constructs_unknown():
    """Test listing constructs for unknown service."""
    result = list_available_constructs.func("unknown_service")
    data = json.loads(result)
    
    assert len(data["data"]["constructs"]) == 0
    assert "available_services" in data["data"]


def test_generate_cdk_tests():
    """Test CDK test generation."""
    result = generate_cdk_tests.func("VpcStack", "vpc")
    data = json.loads(result)
    
    assert data["data"]["stack_name"] == "VpcStack"
    assert data["data"]["stack_type"] == "vpc"
    assert "def test_vpc_stack_synthesizes" in data["data"]["test_code"]
    assert any("pytest" in pkg for pkg in data["data"]["required_packages"])


def test_all_tools_return_json():
    """Test that all tools return valid JSON."""
    tools = [
        (analyze_infrastructure_requirements, ("{}",)),
        (generate_cdk_stack, ("vpc", "{}")),
        (validate_cdk_syntax, ("from aws_cdk import Stack",)),
        (list_available_constructs, ("ec2",)),
        (generate_cdk_tests, ("TestStack", "test")),
    ]
    
    for tool_func, args in tools:
        result = tool_func.func(*args)
        # Should not raise exception
        data = json.loads(result)
        assert "tool" in data
        assert "timestamp" in data
        assert "data" in data
