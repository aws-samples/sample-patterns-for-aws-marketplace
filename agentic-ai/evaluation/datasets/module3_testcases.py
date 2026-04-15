"""
evaluation/datasets/module3_testcases.py
=========================================
Test cases for Module 3 CDK Generation Agent evaluation.

Each test case includes:
- Input: Infrastructure requirements
- Expected output: CDK code characteristics
- Evaluation criteria: How to score the generated code
"""

from __future__ import annotations

MODULE3_TEST_CASES = [
    # Simple web application patterns
    {
        "id": "m3-001",
        "name": "Simple Web App with Database",
        "category": "simple",
        "input": {
            "requirements": {
                "compute": "ECS Fargate",
                "database": "RDS PostgreSQL",
                "networking": "VPC with ALB",
            },
            "region": "us-east-1",
            "environment": "dev",
        },
        "expected_output": {
            "stacks": ["VpcStack", "RdsStack", "EcsStack"],
            "resources": ["VPC", "RDS::DBInstance", "ECS::Service", "ElasticLoadBalancingV2::LoadBalancer"],
            "security": ["SecurityGroup", "encryption", "multi_az"],
        },
        "evaluation_criteria": {
            "syntax_correctness": "Valid Python CDK syntax that can be synthesized",
            "completeness": "All required resources (VPC, RDS, ECS, ALB) are included",
            "best_practices": "Multi-AZ deployment, encryption, proper security groups",
            "security": "IAM roles, security groups, encryption at rest and in transit",
        },
    },
    {
        "id": "m3-002",
        "name": "Serverless API with DynamoDB",
        "category": "serverless",
        "input": {
            "requirements": {
                "compute": "Lambda",
                "database": "DynamoDB",
                "api": "API Gateway",
            },
            "region": "us-west-2",
            "environment": "prod",
        },
        "expected_output": {
            "stacks": ["LambdaStack", "DynamoDBStack", "ApiGatewayStack"],
            "resources": ["Lambda::Function", "DynamoDB::Table", "ApiGateway::RestApi"],
            "security": ["IAM::Role", "encryption"],
        },
        "evaluation_criteria": {
            "syntax_correctness": "Valid CDK code with proper imports",
            "completeness": "Lambda, DynamoDB, API Gateway all configured",
            "best_practices": "Point-in-time recovery, encryption, proper IAM",
            "security": "Least privilege IAM, encryption, API authentication",
        },
    },
    
    # Microservices patterns
    {
        "id": "m3-003",
        "name": "Microservices with Service Mesh",
        "category": "microservices",
        "input": {
            "requirements": {
                "compute": "ECS Fargate",
                "services": ["api", "worker", "scheduler"],
                "database": "RDS PostgreSQL",
                "cache": "ElastiCache Redis",
                "queue": "SQS",
            },
            "region": "us-east-1",
            "environment": "prod",
        },
        "expected_output": {
            "stacks": ["VpcStack", "RdsStack", "ElastiCacheStack", "EcsStack"],
            "resources": ["VPC", "RDS::DBInstance", "ElastiCache::ReplicationGroup", "ECS::Service", "SQS::Queue"],
            "multi_service": True,
        },
        "evaluation_criteria": {
            "syntax_correctness": "Valid CDK code for all stacks",
            "completeness": "All services, database, cache, and queue configured",
            "best_practices": "Service discovery, auto-scaling, monitoring",
            "security": "Network isolation, encryption, IAM policies per service",
        },
    },
    
    # Data pipeline patterns
    {
        "id": "m3-004",
        "name": "Data Processing Pipeline",
        "category": "data",
        "input": {
            "requirements": {
                "ingestion": "Kinesis Data Streams",
                "processing": "Lambda",
                "storage": "S3",
                "analytics": "Athena",
            },
            "region": "us-east-1",
            "environment": "prod",
        },
        "expected_output": {
            "stacks": ["KinesisStack", "LambdaStack", "S3Stack"],
            "resources": ["Kinesis::Stream", "Lambda::Function", "S3::Bucket", "Glue::Database"],
            "data_flow": True,
        },
        "evaluation_criteria": {
            "syntax_correctness": "Valid CDK code with data pipeline constructs",
            "completeness": "Complete data flow from ingestion to analytics",
            "best_practices": "Data partitioning, lifecycle policies, monitoring",
            "security": "Encryption at rest and in transit, access policies",
        },
    },
    
    # High availability patterns
    {
        "id": "m3-005",
        "name": "High Availability Web Application",
        "category": "ha",
        "input": {
            "requirements": {
                "compute": "ECS Fargate",
                "database": "Aurora PostgreSQL",
                "cache": "ElastiCache Redis Cluster",
                "cdn": "CloudFront",
                "availability": "multi-region",
            },
            "region": "us-east-1",
            "environment": "prod",
        },
        "expected_output": {
            "stacks": ["VpcStack", "AuroraStack", "ElastiCacheStack", "EcsStack", "CloudFrontStack"],
            "resources": ["Aurora::DBCluster", "ElastiCache::ReplicationGroup", "CloudFront::Distribution"],
            "ha_features": ["multi_az", "read_replicas", "automatic_failover"],
        },
        "evaluation_criteria": {
            "syntax_correctness": "Valid CDK code for HA configuration",
            "completeness": "All HA components configured correctly",
            "best_practices": "Multi-AZ, read replicas, automatic failover, health checks",
            "security": "Encryption, network isolation, DDoS protection",
        },
    },
]

# Evaluation criteria descriptions for Module 3
MODULE3_EVALUATION_CRITERIA = {
    "syntax_correctness": "Is the generated CDK code syntactically valid Python that can be parsed and synthesized without errors?",
    "completeness": "Are all required AWS resources included in the generated stacks? Are there any missing components?",
    "best_practices": "Does the code follow AWS and CDK best practices such as multi-AZ deployments, proper tagging, monitoring, and resource organization?",
    "security": "Are proper security configurations in place including encryption, IAM policies, security groups, and network isolation?",
}
