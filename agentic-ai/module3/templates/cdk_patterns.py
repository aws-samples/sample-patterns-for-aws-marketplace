"""
module3/templates/cdk_patterns.py
==================================
Reusable CDK patterns and templates for common AWS infrastructure.

These templates follow AWS best practices:
- Multi-AZ deployments for high availability
- Encryption at rest and in transit
- Least privilege IAM policies
- Security groups with minimal access
- CloudWatch monitoring and alarms
"""

from __future__ import annotations

from typing import Any


# CDK pattern templates as strings that can be customized
CDK_PATTERNS = {
    "vpc": """
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct


class VpcStack(Stack):
    \"\"\"VPC stack with public and private subnets across multiple AZs.\"\"\"

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC with public and private subnets
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs={max_azs},
            nat_gateways={nat_gateways},
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )
""",
    "ecs": """
from aws_cdk import (
    Stack,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
)
from constructs import Construct


class EcsStack(Stack):
    \"\"\"ECS Fargate service with Application Load Balancer.\"\"\"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ECS Cluster
        cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=vpc,
            container_insights=True,
        )

        # Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            memory_limit_mib={memory},
            cpu={cpu},
        )

        # Container
        container = task_definition.add_container(
            "{container_name}",
            image=ecs.ContainerImage.from_registry("{image}"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="{service_name}",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={environment},
        )

        container.add_port_mappings(
            ecs.PortMapping(container_port={container_port})
        )

        # Fargate Service
        service = ecs.FargateService(
            self,
            "Service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count={desired_count},
            assign_public_ip=False,
        )

        # Application Load Balancer
        lb = elbv2.ApplicationLoadBalancer(
            self,
            "ALB",
            vpc=vpc,
            internet_facing=True,
        )

        listener = lb.add_listener(
            "Listener",
            port=80,
        )

        listener.add_targets(
            "ECS",
            port={container_port},
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
            ),
        )
""",
    "rds": """
from aws_cdk import (
    Stack,
    aws_rds as rds,
    aws_ec2 as ec2,
    RemovalPolicy,
)
from constructs import Construct


class RdsStack(Stack):
    \"\"\"RDS database with Multi-AZ deployment and encryption.\"\"\"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Security Group
        db_security_group = ec2.SecurityGroup(
            self,
            "DBSecurityGroup",
            vpc=vpc,
            description="Security group for RDS database",
            allow_all_outbound=False,
        )

        # RDS Instance
        self.database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.{engine}(
                version=rds.{engine}EngineVersion.{version}
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.{instance_class},
                ec2.InstanceSize.{instance_size},
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[db_security_group],
            multi_az={multi_az},
            allocated_storage={allocated_storage},
            storage_encrypted=True,
            backup_retention=Duration.days({backup_retention}),
            deletion_protection={deletion_protection},
            removal_policy=RemovalPolicy.{removal_policy},
        )
""",
    "elasticache": """
from aws_cdk import (
    Stack,
    aws_elasticache as elasticache,
    aws_ec2 as ec2,
)
from constructs import Construct


class ElastiCacheStack(Stack):
    \"\"\"ElastiCache Redis cluster with encryption.\"\"\"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Security Group
        cache_security_group = ec2.SecurityGroup(
            self,
            "CacheSecurityGroup",
            vpc=vpc,
            description="Security group for ElastiCache",
        )

        # Subnet Group
        subnet_group = elasticache.CfnSubnetGroup(
            self,
            "SubnetGroup",
            description="Subnet group for ElastiCache",
            subnet_ids=[subnet.subnet_id for subnet in vpc.private_subnets],
        )

        # Replication Group (Redis Cluster)
        self.cache_cluster = elasticache.CfnReplicationGroup(
            self,
            "RedisCluster",
            replication_group_description="{description}",
            engine="redis",
            engine_version="{engine_version}",
            cache_node_type="{node_type}",
            num_cache_clusters={num_nodes},
            automatic_failover_enabled={automatic_failover},
            multi_az_enabled={multi_az},
            at_rest_encryption_enabled=True,
            transit_encryption_enabled=True,
            cache_subnet_group_name=subnet_group.ref,
            security_group_ids=[cache_security_group.security_group_id],
        )
""",
    "s3": """
from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
)
from constructs import Construct


class S3Stack(Stack):
    \"\"\"S3 bucket with encryption and versioning.\"\"\"

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket
        self.bucket = s3.Bucket(
            self,
            "Bucket",
            bucket_name="{bucket_name}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned={versioned},
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.{removal_policy},
            auto_delete_objects={auto_delete},
        )
""",
    "lambda": """
from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_ec2 as ec2,
    aws_logs as logs,
    Duration,
)
from constructs import Construct


class LambdaStack(Stack):
    \"\"\"Lambda function with VPC access and monitoring.\"\"\"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda Function
        self.function = lambda_.Function(
            self,
            "Function",
            runtime=lambda_.Runtime.{runtime},
            handler="{handler}",
            code=lambda_.Code.from_asset("{code_path}"),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            memory_size={memory_size},
            timeout=Duration.seconds({timeout}),
            environment={environment},
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
""",
}


def generate_vpc_stack(
    max_azs: int = 2,
    nat_gateways: int = 1,
) -> str:
    """Generate a VPC stack with customizable parameters."""
    return CDK_PATTERNS["vpc"].format(
        max_azs=max_azs,
        nat_gateways=nat_gateways,
    )


def generate_ecs_stack(
    service_name: str = "app",
    container_name: str = "app-container",
    image: str = "nginx:latest",
    container_port: int = 80,
    memory: int = 512,
    cpu: int = 256,
    desired_count: int = 2,
    environment: dict[str, str] | None = None,
) -> str:
    """Generate an ECS Fargate stack with ALB."""
    env_dict = environment or {}
    return CDK_PATTERNS["ecs"].format(
        service_name=service_name,
        container_name=container_name,
        image=image,
        container_port=container_port,
        memory=memory,
        cpu=cpu,
        desired_count=desired_count,
        environment=env_dict,
    )


def generate_rds_stack(
    engine: str = "POSTGRES",
    version: str = "VER_15_4",
    instance_class: str = "BURSTABLE3",
    instance_size: str = "SMALL",
    multi_az: bool = True,
    allocated_storage: int = 20,
    backup_retention: int = 7,
    deletion_protection: bool = True,
    removal_policy: str = "SNAPSHOT",
) -> str:
    """Generate an RDS database stack."""
    return CDK_PATTERNS["rds"].format(
        engine=engine,
        version=version,
        instance_class=instance_class,
        instance_size=instance_size,
        multi_az=str(multi_az),
        allocated_storage=allocated_storage,
        backup_retention=backup_retention,
        deletion_protection=str(deletion_protection),
        removal_policy=removal_policy,
    )


def generate_elasticache_stack(
    description: str = "Redis cache cluster",
    engine_version: str = "7.0",
    node_type: str = "cache.t3.micro",
    num_nodes: int = 2,
    automatic_failover: bool = True,
    multi_az: bool = True,
) -> str:
    """Generate an ElastiCache Redis stack."""
    return CDK_PATTERNS["elasticache"].format(
        description=description,
        engine_version=engine_version,
        node_type=node_type,
        num_nodes=num_nodes,
        automatic_failover=str(automatic_failover).lower(),
        multi_az=str(multi_az).lower(),
    )


def generate_s3_stack(
    bucket_name: str | None = None,
    versioned: bool = True,
    removal_policy: str = "RETAIN",
    auto_delete: bool = False,
) -> str:
    """Generate an S3 bucket stack."""
    return CDK_PATTERNS["s3"].format(
        bucket_name=bucket_name or "",
        versioned=str(versioned),
        removal_policy=removal_policy,
        auto_delete=str(auto_delete),
    )


def generate_lambda_stack(
    runtime: str = "PYTHON_3_11",
    handler: str = "index.handler",
    code_path: str = "lambda",
    memory_size: int = 128,
    timeout: int = 30,
    environment: dict[str, str] | None = None,
) -> str:
    """Generate a Lambda function stack."""
    env_dict = environment or {}
    return CDK_PATTERNS["lambda"].format(
        runtime=runtime,
        handler=handler,
        code_path=code_path,
        memory_size=memory_size,
        timeout=timeout,
        environment=env_dict,
    )
