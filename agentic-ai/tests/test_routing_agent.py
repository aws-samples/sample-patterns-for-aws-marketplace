"""
tests/test_routing_agent.py
============================
Tests for routing agent intent classification.
"""

import os
import pytest

# Set mock mode
os.environ["AGENT_MOCK_REPO"] = "true"

from routing_agent.agent import classify_intent, route_request, classify_batch


def test_classify_repository_analysis():
    """Test classification of repository analysis requests."""
    request = "Analyze the repository at /home/user/myapp"
    
    result = classify_intent(request, verbose=False)
    
    assert result["category"] == "repository_analysis"
    assert result["target_agent"] == "module2"
    assert result["confidence"] > 0.7


def test_classify_infrastructure_generation():
    """Test classification of infrastructure generation requests."""
    request = "Generate CDK code for a web application with PostgreSQL"
    
    result = classify_intent(request, verbose=False)
    
    assert result["category"] == "infrastructure_generation"
    assert result["target_agent"] == "module3"
    assert result["confidence"] > 0.7


def test_classify_aws_infrastructure():
    """Test classification of AWS infrastructure monitoring requests."""
    request = "Check the health of my ECS services in us-east-1"
    
    result = classify_intent(request, verbose=False)
    
    assert result["category"] == "aws_infrastructure"
    assert result["target_agent"] == "module1"
    assert result["confidence"] > 0.7


def test_route_request_high_confidence():
    """Test routing with high confidence classification."""
    request = "Analyze my repository"
    
    result = route_request(request, verbose=False)
    
    assert result["suggested_action"] == "route"
    assert result["confidence"] >= 0.7


def test_classify_batch():
    """Test batch classification of multiple requests."""
    requests = [
        "Analyze repository at /path/to/repo",
        "Generate CDK for ECS",
        "Check AWS health",
    ]
    
    results = classify_batch(requests, verbose=False)
    
    assert len(results) == 3
    assert all("category" in r for r in results)
    assert all("confidence" in r for r in results)


def test_classification_includes_target_url():
    """Test that classification includes target URL."""
    request = "Generate infrastructure"
    
    result = classify_intent(request, verbose=False)
    
    assert "target_url" in result
    assert result["target_url"] != ""


def test_classification_response_structure():
    """Test that classification response has expected structure."""
    request = "Test request"
    
    result = classify_intent(request, verbose=False)
    
    required_keys = ["category", "confidence", "reasoning", "target_agent", "target_url"]
    for key in required_keys:
        assert key in result
