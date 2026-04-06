"""
module4/protocols/mcp_protocol.py
==================================
MCP (Model Context Protocol) based inter-agent communication.

This module demonstrates MCP-style integration where specialist agent
capabilities are exposed as tools that the orchestrator can call directly.
Instead of HTTP requests, the orchestrator invokes tools served by an
MCP server — the protocol handles discovery, schema, and execution.

PATTERN: Tool-based integration — agents expose capabilities as MCP tools.

Key differences from Direct HTTP:
- Direct HTTP: Orchestrator sends messages to agent endpoints (HTTP POST)
- MCP: Orchestrator calls tools that agents expose (function calls)

In this demo, we simulate MCP by wrapping Module 3's tools as if they
were served by an MCP server, demonstrating the tool-discovery and
invocation pattern.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool


# Mock mode flag
_MOCK = os.getenv("AGENT_MOCK_MODE", "true").lower() == "true"


# ---------------------------------------------------------------------------
# MCP Tool Registry — simulates MCP tool discovery
# ---------------------------------------------------------------------------

class MCPToolRegistry:
    """
    Simulates an MCP server's tool registry.

    In production, an MCP server exposes tools with JSON Schema definitions.
    Clients discover available tools, read their schemas, and invoke them.

    This registry mimics that pattern by wrapping Module 3's CDK tools
    as MCP-served tools.

    Example
    -------
    >>> registry = MCPToolRegistry()
    >>> tools = registry.list_tools()
    >>> print([t["name"] for t in tools])
    ['mcp_analyze_requirements', 'mcp_generate_cdk', 'mcp_validate_cdk']
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._tools: dict[str, dict[str, Any]] = {}
        self._register_module3_tools()

    def _register_module3_tools(self) -> None:
        """Register Module 3's CDK tools as MCP-served tools."""
        self._tools = {
            "mcp_analyze_requirements": {
                "name": "mcp_analyze_requirements",
                "description": "Analyze infrastructure requirements and recommend CDK stacks",
                "source_agent": "module3",
                "schema": {
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "string",
                            "description": "Infrastructure requirements as JSON or plain text",
                        },
                    },
                    "required": ["requirements"],
                },
            },
            "mcp_generate_cdk": {
                "name": "mcp_generate_cdk",
                "description": "Generate CDK stack code for a specific AWS service",
                "source_agent": "module3",
                "schema": {
                    "type": "object",
                    "properties": {
                        "stack_type": {
                            "type": "string",
                            "enum": ["vpc", "ecs", "rds", "elasticache", "s3", "lambda"],
                            "description": "Type of CDK stack to generate",
                        },
                        "parameters": {
                            "type": "string",
                            "description": "JSON string with stack parameters",
                        },
                    },
                    "required": ["stack_type"],
                },
            },
            "mcp_validate_cdk": {
                "name": "mcp_validate_cdk",
                "description": "Validate CDK stack code for syntax and best practices",
                "source_agent": "module3",
                "schema": {
                    "type": "object",
                    "properties": {
                        "cdk_code": {
                            "type": "string",
                            "description": "CDK code to validate",
                        },
                    },
                    "required": ["cdk_code"],
                },
            },
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """
        List all available MCP tools (tool discovery).

        Returns
        -------
        list of dict
            Tool definitions with name, description, and schema.
        """
        if self.verbose:
            print(f"  [MCP] Discovering tools... found {len(self._tools)} tools")
        return list(self._tools.values())

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """
        Get the JSON Schema for a specific tool.

        Parameters
        ----------
        tool_name : str
            Name of the tool.

        Returns
        -------
        dict or None
            Tool schema, or None if not found.
        """
        tool_def = self._tools.get(tool_name)
        if tool_def:
            return tool_def["schema"]
        return None

    def invoke_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Invoke an MCP tool by name.

        Parameters
        ----------
        tool_name : str
            Name of the tool to invoke.
        arguments : dict
            Tool arguments matching the schema.

        Returns
        -------
        dict
            Tool execution result.
        """
        if tool_name not in self._tools:
            return {"error": f"Tool not found: {tool_name}"}

        if self.verbose:
            print(f"  [MCP] Invoking tool: {tool_name}")
            print(f"  [MCP] Arguments: {json.dumps(arguments, indent=2)[:200]}")

        tool_def = self._tools[tool_name]

        if _MOCK:
            result = self._mock_invoke(tool_name, arguments)
        else:
            result = self._live_invoke(tool_name, arguments)

        if self.verbose:
            print(f"  [MCP] Tool {tool_name} completed")

        return {
            "tool": tool_name,
            "source_agent": tool_def["source_agent"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }

    def _mock_invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute tool in mock mode."""
        if tool_name == "mcp_analyze_requirements":
            return {
                "parsed_requirements": {
                    "compute": "ECS Fargate",
                    "database": "RDS PostgreSQL",
                    "cache": "ElastiCache Redis",
                    "networking": "VPC with ALB",
                },
                "recommended_stacks": [
                    "VpcStack", "RdsStack", "ElastiCacheStack", "EcsStack",
                ],
                "questions": [],
            }

        elif tool_name == "mcp_generate_cdk":
            stack_type = arguments.get("stack_type", "vpc")
            return {
                "stack_type": stack_type,
                "status": "generated",
                "syntax_valid": True,
                "code_preview": f"class {stack_type.title()}Stack(Stack): ...",
                "resources_created": _mock_resources_for_type(stack_type),
            }

        elif tool_name == "mcp_validate_cdk":
            return {
                "status": "PASS",
                "syntax_valid": True,
                "best_practices_score": 92,
                "issues": [],
            }

        return {"error": "Unknown tool"}

    def _live_invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute tool in live mode by calling actual Module 3 tools."""
        from module3.tools.cdk_tools import (
            analyze_infrastructure_requirements,
            generate_cdk_stack,
            validate_cdk_syntax,
        )

        if tool_name == "mcp_analyze_requirements":
            raw = analyze_infrastructure_requirements.func(arguments["requirements"])
            return json.loads(raw)["data"]

        elif tool_name == "mcp_generate_cdk":
            raw = generate_cdk_stack.func(
                arguments["stack_type"],
                arguments.get("parameters", "{}"),
            )
            return json.loads(raw)["data"]

        elif tool_name == "mcp_validate_cdk":
            raw = validate_cdk_syntax.func(arguments["cdk_code"])
            return json.loads(raw)["data"]

        return {"error": "Unknown tool"}


def _mock_resources_for_type(stack_type: str) -> list[str]:
    """Return mock resource list for a stack type."""
    resources = {
        "vpc": ["VPC", "Public Subnets (2 AZs)", "Private Subnets (2 AZs)", "NAT Gateway", "Internet Gateway"],
        "ecs": ["ECS Cluster", "Fargate Service", "Task Definition", "ALB", "Target Group"],
        "rds": ["RDS Instance", "Security Group", "Subnet Group", "KMS Key"],
        "elasticache": ["Redis Replication Group", "Subnet Group", "Security Group"],
        "s3": ["S3 Bucket", "Bucket Policy", "Lifecycle Rule"],
        "lambda": ["Lambda Function", "IAM Role", "CloudWatch Log Group"],
    }
    return resources.get(stack_type, ["Unknown resource"])


# ---------------------------------------------------------------------------
# LangChain tool wrappers — MCP tools as LangChain @tool for the orchestrator
# ---------------------------------------------------------------------------

# Create a shared registry instance for LangChain tools
_registry = MCPToolRegistry(verbose=False)


@tool
def mcp_analyze_requirements(requirements: str) -> str:
    """
    Analyze infrastructure requirements via MCP protocol (Module 3).

    Discovers and invokes the analyze_requirements tool served by Module 3's
    MCP server. Returns parsed requirements and recommended CDK stacks.

    Args:
        requirements: Infrastructure requirements as JSON or plain text

    Returns:
        JSON string with parsed requirements and recommendations
    """
    result = _registry.invoke_tool("mcp_analyze_requirements", {"requirements": requirements})
    return json.dumps(result, indent=2, default=str)


@tool
def mcp_generate_cdk(stack_type: str, parameters: str = "{}") -> str:
    """
    Generate CDK stack code via MCP protocol (Module 3).

    Invokes Module 3's CDK generation tool through the MCP server.
    Supports: vpc, ecs, rds, elasticache, s3, lambda.

    Args:
        stack_type: Type of CDK stack (vpc, ecs, rds, elasticache, s3, lambda)
        parameters: JSON string with stack-specific parameters

    Returns:
        JSON string with generated CDK code and metadata
    """
    result = _registry.invoke_tool("mcp_generate_cdk", {
        "stack_type": stack_type,
        "parameters": parameters,
    })
    return json.dumps(result, indent=2, default=str)


@tool
def mcp_validate_cdk(cdk_code: str) -> str:
    """
    Validate CDK code via MCP protocol (Module 3).

    Invokes Module 3's validation tool through the MCP server.
    Checks syntax, best practices, and security configurations.

    Args:
        cdk_code: CDK code to validate

    Returns:
        JSON string with validation results
    """
    result = _registry.invoke_tool("mcp_validate_cdk", {"cdk_code": cdk_code})
    return json.dumps(result, indent=2, default=str)


# All MCP tools for the orchestrator agent
MCP_TOOLS = [
    mcp_analyze_requirements,
    mcp_generate_cdk,
    mcp_validate_cdk,
]
