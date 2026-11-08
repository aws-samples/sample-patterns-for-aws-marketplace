"""Deploy the Module 12 security and observability foundation.

This stack deliberately stops at the foundation boundary. It creates the
durable state, evidence, logging, event, secret, image, and IAM resources
needed by the Companion security workflow. The deployment tool remains
simulation-only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pulumi
import pulumi_aws as aws

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from module12.infrastructure.pulumi.security_controls import (
    deploy_security_controls,
)
from module12.infrastructure.pulumi.posture_infrastructure import (
    deploy_posture_infrastructure,
)


PROJECT = "module12-security-observability"
DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_EVIDENCE_RETENTION_DAYS = 90


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return value or "default"


def _policy(statements: list[dict]) -> pulumi.Output[str]:
    return pulumi.Output.json_dumps(
        {"Version": "2012-10-17", "Statement": statements}
    )


def _role(name: str, service: str, *, account_id: str, tags: dict[str, str]) -> aws.iam.Role:
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": service},
                "Action": "sts:AssumeRole",
                "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
            }
        ],
    }
    return aws.iam.Role(
        name,
        name=name,
        assume_role_policy=json.dumps(trust),
        tags=tags,
    )


def _resource_arn(bucket_arn: pulumi.Input[str]) -> pulumi.Output[str]:
    return pulumi.Output.from_input(bucket_arn).apply(lambda arn: f"{arn}/*")


config = pulumi.Config()
stack = _slug(pulumi.get_stack())
region = aws.get_region().region
account_id = aws.get_caller_identity().account_id
partition = aws.get_partition().partition
tags = {
    "Project": PROJECT,
    "Stack": pulumi.get_stack(),
    "ManagedBy": "pulumi",
    "Layer": "foundation",
}

log_retention_days = config.get_int("logRetentionDays") or DEFAULT_LOG_RETENTION_DAYS
evidence_retention_days = (
    config.get_int("evidenceRetentionDays") or DEFAULT_EVIDENCE_RETENTION_DAYS
)
if not 1 <= log_retention_days <= 3653:
    raise pulumi.RunError("logRetentionDays must be between 1 and 3653")
if evidence_retention_days < 1:
    raise pulumi.RunError("evidenceRetentionDays must be positive")

prefix = f"m12-{stack}"

# S3 is the durable home for repository snapshots, manifests, Snyk-shaped
# findings, and workflow evidence. force_destroy is intentionally false.
evidence_bucket = aws.s3.Bucket(
    "evidence-bucket",
    bucket=f"{prefix}-{account_id}-{region}",
    force_destroy=False,
    object_lock_enabled=False,
    tags=tags,
)
aws.s3.BucketOwnershipControls(
    "evidence-bucket-ownership",
    bucket=evidence_bucket.id,
    rule={"object_ownership": "BucketOwnerEnforced"},
)
aws.s3.BucketPublicAccessBlock(
    "evidence-bucket-public-access",
    bucket=evidence_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)
aws.s3.BucketVersioning(
    "evidence-bucket-versioning",
    bucket=evidence_bucket.id,
    versioning_configuration={"status": "Enabled"},
)
aws.s3.BucketServerSideEncryptionConfiguration(
    "evidence-bucket-encryption",
    bucket=evidence_bucket.id,
    rules=[
        {
            "apply_server_side_encryption_by_default": {
                "sse_algorithm": "AES256"
            },
            "bucket_key_enabled": True,
        }
    ],
)
aws.s3.BucketLifecycleConfiguration(
    "evidence-bucket-lifecycle",
    bucket=evidence_bucket.id,
    rules=[
        {
            "id": "evidence-retention",
            "status": "Enabled",
            "filter": {"prefix": "evidence/"},
            "expiration": {"days": evidence_retention_days},
        },
        {
            "id": "noncurrent-version-retention",
            "status": "Enabled",
            "filter": {},
            "noncurrent_version_expiration": {"noncurrent_days": evidence_retention_days},
        },
    ],
)
aws.s3.BucketPolicy(
    "evidence-bucket-tls-only",
    bucket=evidence_bucket.id,
    policy=evidence_bucket.arn.apply(
        lambda arn: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "DenyInsecureTransport",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": "s3:*",
                        "Resource": [arn, f"{arn}/*"],
                        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                    }
                ],
            }
        )
    ),
)

# The immutable repository is ready for the Companion runtime image.
runtime_repository = aws.ecr.Repository(
    "runtime-image",
    name=f"{prefix}-runtime",
    image_tag_mutability="IMMUTABLE",
    image_scanning_configuration={"scan_on_push": True},
    encryption_configurations=[{"encryption_type": "AES256"}],
    tags=tags,
)
aws.ecr.LifecyclePolicy(
    "runtime-image-lifecycle",
    repository=runtime_repository.name,
    policy=json.dumps(
        {
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep the newest twenty untagged images",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "imageCountMoreThan",
                        "countNumber": 20,
                    },
                    "action": {"type": "expire"},
                }
            ]
        }
    ),
)

log_groups = {
    "runtime": aws.cloudwatch.LogGroup(
        "runtime-logs",
        name=f"/aws/module12/{stack}/runtime",
        retention_in_days=log_retention_days,
        tags=tags,
    ),
    "tools": aws.cloudwatch.LogGroup(
        "tool-logs",
        name=f"/aws/module12/{stack}/tools",
        retention_in_days=log_retention_days,
        tags=tags,
    ),
    "operations": aws.cloudwatch.LogGroup(
        "operations-logs",
        name=f"/aws/module12/{stack}/operations",
        retention_in_days=log_retention_days,
        tags=tags,
    ),
}

workflow_table = aws.dynamodb.Table(
    "workflow-state",
    name=f"{prefix}-workflow-state",
    billing_mode="PAY_PER_REQUEST",
    hash_key="workflowId",
    range_key="recordType",
    attributes=[
        {"name": "workflowId", "type": "S"},
        {"name": "recordType", "type": "S"},
    ],
    point_in_time_recovery={"enabled": True},
    server_side_encryption={"enabled": True},
    tags=tags,
)
governance_table = aws.dynamodb.Table(
    "governance-state",
    name=f"{prefix}-governance-state",
    billing_mode="PAY_PER_REQUEST",
    hash_key="workflowId",
    attributes=[{"name": "workflowId", "type": "S"}],
    ttl={"attribute_name": "expiresAt", "enabled": True},
    point_in_time_recovery={"enabled": True},
    server_side_encryption={"enabled": True},
    tags={**tags, "Layer": "trusted-governance"},
)
posture_table = aws.dynamodb.Table(
    "posture-history",
    name=f"{prefix}-posture-history",
    billing_mode="PAY_PER_REQUEST",
    hash_key="subject",
    range_key="observedAt",
    attributes=[
        {"name": "subject", "type": "S"},
        {"name": "observedAt", "type": "S"},
    ],
    point_in_time_recovery={"enabled": True},
    server_side_encryption={"enabled": True},
    tags=tags,
)

posture_bus = aws.cloudwatch.EventBus(
    "posture-events",
    name=f"{prefix}-posture",
    tags=tags,
)

honeycomb_secret = aws.secretsmanager.Secret(
    "honeycomb-credentials",
    name=f"{prefix}/honeycomb",
    description="Complete Honeycomb Ingest Key managed from encrypted Pulumi configuration.",
    recovery_window_in_days=7,
    tags=tags,
)
honeycomb_secret_version = aws.secretsmanager.SecretVersion(
    "honeycomb-credentials-value",
    secret_id=honeycomb_secret.id,
    secret_string=config.require_secret("honeycombIngestKey"),
)
snyk_secret = aws.secretsmanager.Secret(
    "snyk-credentials",
    name=f"{prefix}/snyk",
    description="Snyk credentials for the CodeBuild scanner; no value is managed by Pulumi.",
    recovery_window_in_days=7,
    tags=tags,
)

# These roles establish the least-privilege identities consumed by later
# later security controls. They do not grant environment deployment
# permissions.
runtime_role = _role(
    f"{prefix}-runtime",
    "bedrock-agentcore.amazonaws.com",
    account_id=account_id,
    tags=tags,
)
tool_role = _role(
    f"{prefix}-tool",
    "lambda.amazonaws.com",
    account_id=account_id,
    tags=tags,
)

runtime_policy = pulumi.Output.all(
    evidence_bucket.arn,
    _resource_arn(evidence_bucket.arn),
    workflow_table.arn,
    posture_table.arn,
    governance_table.arn,
    posture_bus.arn,
    honeycomb_secret.arn,
    log_groups["runtime"].arn,
).apply(
    lambda values: json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "Evidence",
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject"],
                    "Resource": values[1],
                },
                {
                    "Sid": "EvidenceList",
                    "Effect": "Allow",
                    "Action": ["s3:ListBucket"],
                    "Resource": values[0],
                    "Condition": {
                        "StringLike": {
                            "s3:prefix": [
                                "artifacts/*",
                                "manifests/*",
                                "findings/*",
                                "evidence/*",
                            ]
                        }
                    },
                },
                {
                    "Sid": "WorkflowState",
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:Query",
                    ],
                    "Resource": values[2],
                },
                {
                    "Sid": "ReadPostureState",
                    "Effect": "Allow",
                    "Action": "dynamodb:Query",
                    "Resource": values[3],
                },
                {
                    "Sid": "ReadGovernanceState",
                    "Effect": "Allow",
                    "Action": "dynamodb:GetItem",
                    "Resource": values[4],
                },
                {
                    "Sid": "PostureEvents",
                    "Effect": "Allow",
                    "Action": "events:PutEvents",
                    "Resource": values[5],
                },
                {
                    "Sid": "TelemetrySecretRead",
                    "Effect": "Allow",
                    "Action": "secretsmanager:GetSecretValue",
                    "Resource": values[6],
                },
                {
                    "Sid": "RuntimeLogs",
                    "Effect": "Allow",
                    "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                    "Resource": f"{values[7]}:*",
                },
            ],
        },
        sort_keys=True,
    )
)
aws.iam.RolePolicy(
    "runtime-permissions",
    role=runtime_role.id,
    policy=runtime_policy,
)

tool_log_arns = pulumi.Output.all(log_groups["tools"].arn, log_groups["operations"].arn)
tool_policy = tool_log_arns.apply(
    lambda values: json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ToolLogs",
                    "Effect": "Allow",
                    "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                    "Resource": [f"{values[0]}:*", f"{values[1]}:*"],
                }
            ],
        },
        sort_keys=True,
    )
)
aws.iam.RolePolicy(
    "tool-log-permissions",
    role=tool_role.id,
    policy=tool_policy,
)


def export(name: str, value: pulumi.Input[str]) -> None:
    pulumi.export(name, value)


export("project", PROJECT)
export("stack", pulumi.get_stack())
export("accountId", account_id)
export("region", region)
export("partition", partition)
export("projectTag", PROJECT)
export("evidenceBucketName", evidence_bucket.bucket)
export("evidenceBucketArn", evidence_bucket.arn)
export("runtimeRepositoryName", runtime_repository.name)
export("runtimeRepositoryArn", runtime_repository.arn)
export("runtimeRepositoryUrl", runtime_repository.repository_url)
export("workflowStateTableName", workflow_table.name)
export("workflowStateTableArn", workflow_table.arn)
export("governanceStateTableName", governance_table.name)
export("governanceStateTableArn", governance_table.arn)
export("postureHistoryTableName", posture_table.name)
export("postureHistoryTableArn", posture_table.arn)
export("postureEventBusName", posture_bus.name)
export("postureEventBusArn", posture_bus.arn)
export("runtimeLogGroupName", log_groups["runtime"].name)
export("runtimeLogGroupArn", log_groups["runtime"].arn)
export("toolLogGroupName", log_groups["tools"].name)
export("toolLogGroupArn", log_groups["tools"].arn)
export("operationsLogGroupName", log_groups["operations"].name)
export("operationsLogGroupArn", log_groups["operations"].arn)
export("honeycombSecretArn", honeycomb_secret.arn)
export("snykSecretArn", snyk_secret.arn)
export("runtimeRoleArn", runtime_role.arn)
export("toolRoleArn", tool_role.arn)

for output_name, output_value in deploy_security_controls(
    config,
    prefix=prefix,
    stack=stack,
    account_id=account_id,
    region=region,
    partition=partition,
    tags=tags,
    evidence_bucket=evidence_bucket,
    runtime_repository=runtime_repository,
    workflow_table=workflow_table,
    governance_table=governance_table,
    posture_table=posture_table,
    honeycomb_secret=honeycomb_secret,
    honeycomb_secret_version=honeycomb_secret_version,
    operations_log=log_groups["operations"],
    runtime_role=runtime_role,
    tool_role=tool_role,
).items():
    export(output_name, output_value)

for output_name, output_value in deploy_posture_infrastructure(
    prefix=prefix,
    account_id=account_id,
    region=region,
    partition=partition,
    tags=tags,
    evidence_bucket=evidence_bucket,
    posture_table=posture_table,
    posture_bus=posture_bus,
    snyk_secret=snyk_secret,
    operations_log=log_groups["operations"],
).items():
    export(output_name, output_value)
