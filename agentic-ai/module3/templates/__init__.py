"""
module3.templates
=================
CDK templates and patterns for common AWS infrastructure.
"""

from module3.templates.cdk_patterns import (
    CDK_PATTERNS,
    generate_vpc_stack,
    generate_ecs_stack,
    generate_rds_stack,
    generate_elasticache_stack,
    generate_s3_stack,
    generate_lambda_stack,
)

__all__ = [
    "CDK_PATTERNS",
    "generate_vpc_stack",
    "generate_ecs_stack",
    "generate_rds_stack",
    "generate_elasticache_stack",
    "generate_s3_stack",
    "generate_lambda_stack",
]
