"""AgentCore runtime, gateway, governance policy, and image build."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pulumi
import pulumi_aws as aws
import pulumi_aws_native as native

from module12.cedar_policy import (
    MCP_PROTOCOL_VERSION,
    MUTATION_TOOLS,
    READ_ONLY_TOOLS,
    TOOL_TARGET_NAME,
    build_cedar_statements,
)


def _policy(statements: list[dict]) -> pulumi.Output[str]:
    return pulumi.Output.json_dumps(
        {"Version": "2012-10-17", "Statement": statements}
    )


def _runtime_source_tag(
    stack: str,
    *,
    runtime_dir: Path,
    module_dir: Path,
) -> str:
    """Return an immutable ECR tag derived from the packaged Runtime source."""

    paths = (
        runtime_dir / "Dockerfile",
        runtime_dir / "requirements.txt",
        runtime_dir / "app.py",
        module_dir / "__init__.py",
        module_dir / "contracts.py",
        module_dir / "workflow.py",
        module_dir / "gateway_client.py",
        module_dir / "live_agents.py",
        module_dir / "cedar_policy.py",
        module_dir / "policy_verifier.py",
        module_dir / "strands_intervention.py",
        module_dir / "posture.py",
        module_dir / "telemetry.py",
        module_dir / "tools" / "handler.py",
        module_dir / "tools" / "__init__.py",
        module_dir / "fixtures" / "clean_repository.json",
        module_dir / "fixtures" / "poisoned_repository.json",
        module_dir / "fixtures" / "scenarios.json",
    )
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(str(path.relative_to(module_dir.parent)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"companion-{stack}-{digest.hexdigest()[:12]}"


def deploy_security_controls(
    config: pulumi.Config,
    *,
    prefix: str,
    stack: str,
    account_id: str,
    region: str,
    partition: str,
    tags: dict[str, str],
    evidence_bucket: aws.s3.Bucket,
    runtime_repository: aws.ecr.Repository,
    workflow_table: aws.dynamodb.Table,
    governance_table: aws.dynamodb.Table,
    posture_table: aws.dynamodb.Table,
    honeycomb_secret: aws.secretsmanager.Secret,
    honeycomb_secret_version: aws.secretsmanager.SecretVersion,
    operations_log: aws.cloudwatch.LogGroup,
    runtime_role: aws.iam.Role,
    tool_role: aws.iam.Role,
) -> dict[str, pulumi.Input[str]]:
    component_tags = {**tags, "Layer": "agentcore-governance"}
    runtime_dir = Path(__file__).resolve().parents[2] / "runtime"
    module_dir = Path(__file__).resolve().parents[2]
    image_tag = config.get("imageTag") or _runtime_source_tag(
        stack,
        runtime_dir=runtime_dir,
        module_dir=module_dir,
    )
    image_digest = config.get("imageDigest")
    honeycomb_dataset = (
        config.get("honeycombDataset") or "module12-security-observability"
    )
    honeycomb_endpoint = (
        config.get("honeycombEndpoint")
        or "https://api.honeycomb.io/v1/traces"
    )
    honeycomb_api_host = honeycomb_endpoint.removesuffix("/v1/traces")
    enable_gateway_tracing = config.get_bool("enableGatewayTracing") or False
    deployment_label = re.sub(r"^module12-?", "", stack).strip("-") or stack
    gateway_name = (
        config.get("gatewayName")
        or f"devops-companion-{deployment_label}-gateway"
    )
    policy_engine_name = (
        config.get("policyEngineName")
        or f"{gateway_name.removesuffix('-gateway').replace('-', '_')}_policy"
    )
    policy_name_prefix = policy_engine_name.removesuffix("_policy")
    agentcore_provider = native.Provider(
        "agentcore-region",
        region=region,
    )
    source_key = "runtime/companion-source.zip"

    runtime_source = aws.s3.BucketObject(
        "runtime-source",
        bucket=evidence_bucket.id,
        key=source_key,
        source=pulumi.AssetArchive(
            {
                "Dockerfile": pulumi.FileAsset(str(runtime_dir / "Dockerfile")),
                "requirements.txt": pulumi.FileAsset(
                    str(runtime_dir / "requirements.txt")
                ),
                "app.py": pulumi.FileAsset(str(runtime_dir / "app.py")),
                "module12": pulumi.AssetArchive(
                    {
                        "__init__.py": pulumi.FileAsset(str(module_dir / "__init__.py")),
                        "contracts.py": pulumi.FileAsset(
                            str(module_dir / "contracts.py")
                        ),
                        "workflow.py": pulumi.FileAsset(
                            str(module_dir / "workflow.py")
                        ),
                        "gateway_client.py": pulumi.FileAsset(
                            str(module_dir / "gateway_client.py")
                        ),
                        "live_agents.py": pulumi.FileAsset(
                            str(module_dir / "live_agents.py")
                        ),
                        "cedar_policy.py": pulumi.FileAsset(
                            str(module_dir / "cedar_policy.py")
                        ),
                        "policy_verifier.py": pulumi.FileAsset(
                            str(module_dir / "policy_verifier.py")
                        ),
                        "strands_intervention.py": pulumi.FileAsset(
                            str(module_dir / "strands_intervention.py")
                        ),
                        "posture.py": pulumi.FileAsset(
                            str(module_dir / "posture.py")
                        ),
                        "telemetry.py": pulumi.FileAsset(
                            str(module_dir / "telemetry.py")
                        ),
                        "tools": pulumi.AssetArchive(
                            {
                                "handler.py": pulumi.FileAsset(
                                    str(module_dir / "tools" / "handler.py")
                                ),
                                "__init__.py": pulumi.FileAsset(
                                    str(module_dir / "tools" / "__init__.py")
                                ),
                            }
                        ),
                        "fixtures": pulumi.AssetArchive(
                            {
                                "clean_repository.json": pulumi.FileAsset(
                                    str(
                                        module_dir
                                        / "fixtures"
                                        / "clean_repository.json"
                                    )
                                ),
                                "poisoned_repository.json": pulumi.FileAsset(
                                    str(
                                        module_dir
                                        / "fixtures"
                                        / "poisoned_repository.json"
                                    )
                                ),
                                "scenarios.json": pulumi.FileAsset(
                                    str(module_dir / "fixtures" / "scenarios.json")
                                ),
                            }
                        ),
                    }
                ),
            }
        ),
    )

    build_role = aws.iam.Role(
        "runtime-image-build-role",
        name=f"{prefix}-runtime-build",
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "codebuild.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": account_id}
                        },
                    }
                ],
            }
        ),
        tags=component_tags,
    )
    build_policy = pulumi.Output.all(
        runtime_repository.arn,
        evidence_bucket.arn,
        operations_log.arn,
    ).apply(
        lambda values: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "EcrLogin",
                        "Effect": "Allow",
                        "Action": "ecr:GetAuthorizationToken",
                        "Resource": "*",
                    },
                    {
                        "Sid": "PushRuntimeImage",
                        "Effect": "Allow",
                        "Action": [
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:BatchGetImage",
                            "ecr:CompleteLayerUpload",
                            "ecr:DescribeImages",
                            "ecr:InitiateLayerUpload",
                            "ecr:PutImage",
                            "ecr:UploadLayerPart",
                            "ecr:GetDownloadUrlForLayer",
                        ],
                        "Resource": values[0],
                    },
                    {
                        "Sid": "ReadBuildSource",
                        "Effect": "Allow",
                        "Action": "s3:GetObject",
                        "Resource": f"{values[1]}/{source_key}",
                    },
                    {
                        "Sid": "BuildLogs",
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogStream",
                            "logs:PutLogEvents",
                        ],
                        "Resource": f"{values[2]}:*",
                    },
                ],
            },
            sort_keys=True,
        )
    )
    build_role_policy = aws.iam.RolePolicy(
        "runtime-image-build-permissions",
        role=build_role.id,
        policy=build_policy,
    )
    build_project = aws.codebuild.Project(
        "runtime-image-build",
        name=f"{prefix}-runtime-build",
        service_role=build_role.arn,
        artifacts={"type": "NO_ARTIFACTS"},
        source={
            "type": "S3",
            "location": evidence_bucket.bucket.apply(
                lambda bucket: f"{bucket}/{source_key}"
            ),
            "buildspec": "\n".join(
                [
                    "version: 0.2",
                    "phases:",
                    "  pre_build:",
                    "    commands:",
                    '      - export ECR_REGISTRY=$(echo "$ECR_REPOSITORY" | cut -d/ -f1)',
                    '      - aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY"',
                    "  build:",
                    "    commands:",
                    '      - docker build --pull -t "$ECR_REPOSITORY:$IMAGE_TAG" .',
                    "  post_build:",
                    "    commands:",
                    '      - docker push "$ECR_REPOSITORY:$IMAGE_TAG"',
                ]
            ),
        },
        environment={
            "compute_type": "BUILD_GENERAL1_SMALL",
            "image": "aws/codebuild/amazonlinux-aarch64-standard:3.0",
            "type": "ARM_CONTAINER",
            "privileged_mode": True,
            "environment_variables": [
                {
                    "name": "ECR_REPOSITORY",
                    "value": runtime_repository.repository_url,
                },
                {"name": "IMAGE_TAG", "value": image_tag},
            ],
        },
        logs_config={
            "cloudwatch_logs": {
                "group_name": operations_log.name,
                "status": "ENABLED",
            }
        },
        build_timeout=20,
        tags=component_tags,
        opts=pulumi.ResourceOptions(depends_on=[build_role_policy, runtime_source]),
    )

    outputs: dict[str, pulumi.Input[str]] = {
        "securityControlsEnabled": False,
        "runtimeImageBuildProject": build_project.name,
        "runtimeSourceObjectKey": source_key,
        "runtimeImageTag": image_tag,
    }
    if not image_digest:
        return outputs
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
        raise pulumi.RunError("imageDigest must be a sha256:<64 hex characters> digest")

    agentcore_prefix = f"m12_{stack.replace('-', '_')}"
    runtime_name = f"{agentcore_prefix}_companion"

    tool_dir = Path(__file__).resolve().parents[2] / "tools"
    tool_log_group = aws.cloudwatch.LogGroup(
        "companion-tool-lambda-logs",
        name=f"/aws/lambda/{prefix}-tools",
        retention_in_days=30,
        tags=component_tags,
    )
    tool_lambda_log_policy = aws.iam.RolePolicy(
        "companion-tool-lambda-logs",
        role=tool_role.id,
        policy=tool_log_group.arn.apply(
            lambda arn: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": f"{arn}:*",
                        }
                    ],
                },
                sort_keys=True,
            )
        ),
    )
    tool_function = aws.lambda_.Function(
        "companion-tools",
        name=f"{prefix}-tools",
        description="Deterministic Module 12 companion tool adapter",
        role=tool_role.arn,
        runtime="python3.13",
        handler="handler.handler",
        architectures=["arm64"],
        code=pulumi.AssetArchive(
            {
                "handler.py": pulumi.FileAsset(str(tool_dir / "handler.py")),
                "__init__.py": pulumi.FileAsset(str(tool_dir / "__init__.py")),
            }
        ),
        timeout=30,
        tags=component_tags,
        opts=pulumi.ResourceOptions(depends_on=[tool_lambda_log_policy]),
    )

    interceptor_log_group = aws.cloudwatch.LogGroup(
        "gateway-interceptor-logs",
        name=f"/aws/lambda/{prefix}-gateway-interceptor",
        retention_in_days=30,
        tags=component_tags,
    )
    interceptor_role = aws.iam.Role(
        "gateway-interceptor-role",
        name=f"{prefix}-gateway-interceptor",
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": account_id}
                        },
                    }
                ],
            }
        ),
        tags=component_tags,
    )
    interceptor_role_policy = aws.iam.RolePolicy(
        "gateway-interceptor-permissions",
        role=interceptor_role.id,
        policy=pulumi.Output.all(
            governance_table.arn,
            posture_table.arn,
            interceptor_log_group.arn,
        ).apply(
            lambda values: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "ReadGovernanceState",
                            "Effect": "Allow",
                            "Action": "dynamodb:GetItem",
                            "Resource": values[0],
                        },
                        {
                            "Sid": "ReadPostureState",
                            "Effect": "Allow",
                            "Action": "dynamodb:Query",
                            "Resource": values[1],
                        },
                        {
                            "Sid": "WriteInterceptorLogs",
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": f"{values[2]}:*",
                        },
                    ],
                },
                sort_keys=True,
            )
        ),
    )
    interceptor_function = aws.lambda_.Function(
        "gateway-request-interceptor",
        name=f"{prefix}-gateway-interceptor",
        description=(
            "Reload authoritative Module 12 governance state before Gateway authorization"
        ),
        role=interceptor_role.arn,
        runtime="python3.13",
        handler="gateway_interceptor.handler",
        architectures=["arm64"],
        code=pulumi.AssetArchive(
            {
                "gateway_interceptor.py": pulumi.FileAsset(
                    str(module_dir / "gateway_interceptor.py")
                )
            }
        ),
        environment={
            "variables": {
                "MODULE12_GOVERNANCE_STATE_TABLE": governance_table.name,
                "MODULE12_POSTURE_STATE_TABLE": posture_table.name,
                "MODULE12_POSTURE_SUBJECT": "companion-tools",
            }
        },
        timeout=10,
        tags=component_tags,
        opts=pulumi.ResourceOptions(depends_on=[interceptor_role_policy]),
    )

    gateway_role = aws.iam.Role(
        "gateway-role",
        name=f"{prefix}-gateway",
        assume_role_policy=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                        "Condition": {
                            "StringEquals": {"aws:SourceAccount": account_id},
                            "ArnLike": {
                                "aws:SourceArn": f"arn:{partition}:bedrock-agentcore:{region}:{account_id}:gateway/*"
                            },
                        },
                    }
                ],
            }
        ),
        tags=component_tags,
    )
    policy_engine = native.bedrockagentcore.PolicyEngine(
        "policy-engine",
        name=policy_engine_name,
        description="DevOps Companion deterministic authorization policy",
        tags=[{"key": key, "value": value} for key, value in component_tags.items()],
        opts=pulumi.ResourceOptions(provider=agentcore_provider),
    )
    gateway_role_policy = aws.iam.RolePolicy(
        "gateway-tool-invoke",
        role=gateway_role.id,
        policy=pulumi.Output.all(
            tool_function.arn,
            interceptor_function.arn,
            policy_engine.policy_engine_arn,
        ).apply(
            lambda values: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": "lambda:InvokeFunction",
                            "Resource": [values[0], values[1]],
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "bedrock-agentcore:GetPolicyEngine",
                                "bedrock-agentcore:AuthorizeAction",
                                "bedrock-agentcore:PartiallyAuthorizeActions",
                            ],
                            "Resource": values[2],
                        },
                        {
                            "Effect": "Allow",
                            "Action": [
                                "bedrock-agentcore:AuthorizeAction",
                                "bedrock-agentcore:PartiallyAuthorizeActions",
                            ],
                            "Resource": f"arn:{partition}:bedrock-agentcore:{region}:{account_id}:gateway/*",
                        },
                    ],
                },
                sort_keys=True,
            )
        ),
    )

    gateway = aws.bedrock.AgentcoreGateway(
        "agentcore-gateway",
        name=gateway_name,
        authorizer_type="AWS_IAM",
        role_arn=gateway_role.arn,
        description="DevOps Companion tool gateway",
        policy_engine_configuration={
            "arn": policy_engine.policy_engine_arn,
            "mode": "ENFORCE",
        },
        interceptor_configurations=[
            {
                "interceptor": {
                    "lambda_": {"arn": interceptor_function.arn}
                },
                "input_configuration": {"pass_request_headers": False},
                "interception_points": ["REQUEST"],
            }
        ],
        protocol_configuration={
            "mcp": {
                "supported_versions": [MCP_PROTOCOL_VERSION],
            }
        },
        tags=component_tags,
        opts=pulumi.ResourceOptions(
            depends_on=[gateway_role_policy, interceptor_function]
        ),
    )
    gateway_trace_delivery = None
    gateway_trace_exporter = None
    if enable_gateway_tracing:
        gateway_trace_source = aws.cloudwatch.LogDeliverySource(
            "gateway-trace-source",
            name=f"{gateway_name}-traces",
            log_type="TRACES",
            resource_arn=gateway.gateway_arn,
            tags=component_tags,
            opts=pulumi.ResourceOptions(depends_on=[gateway]),
        )
        gateway_trace_destination = aws.cloudwatch.LogDeliveryDestination(
            "gateway-trace-destination",
            name=f"{gateway_name}-xray",
            delivery_destination_type="XRAY",
            tags=component_tags,
        )
        gateway_trace_delivery = aws.cloudwatch.LogDelivery(
            "gateway-trace-delivery",
            delivery_source_name=gateway_trace_source.name,
            delivery_destination_arn=gateway_trace_destination.arn,
            tags=component_tags,
            opts=pulumi.ResourceOptions(
                depends_on=[
                    gateway_trace_source,
                    gateway_trace_destination,
                ]
            ),
        )
        trace_exporter_role = aws.iam.Role(
            "gateway-trace-exporter-role",
            name=f"{gateway_name}-trace-exporter",
            assume_role_policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "lambda.amazonaws.com"
                            },
                            "Action": "sts:AssumeRole",
                            "Condition": {
                                "StringEquals": {
                                    "aws:SourceAccount": account_id
                                }
                            },
                        }
                    ],
                }
            ),
            tags=component_tags,
        )
        trace_exporter_log_group = aws.cloudwatch.LogGroup(
            "gateway-trace-exporter-logs",
            name=f"/aws/lambda/{gateway_name}-trace-exporter",
            retention_in_days=30,
            tags=component_tags,
        )
        trace_exporter_policy = aws.iam.RolePolicy(
            "gateway-trace-exporter-policy",
            role=trace_exporter_role.id,
            policy=pulumi.Output.all(
                honeycomb_secret.arn,
                trace_exporter_log_group.arn,
            ).apply(
                lambda values: json.dumps(
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": "secretsmanager:GetSecretValue",
                                "Resource": values[0],
                            },
                            {
                                "Effect": "Allow",
                                "Action": [
                                    "logs:CreateLogStream",
                                    "logs:PutLogEvents",
                                ],
                                "Resource": f"{values[1]}:*",
                            },
                        ],
                    },
                    sort_keys=True,
                )
            ),
        )
        trace_exporter_path = (
            Path(__file__).resolve().parents[1]
            / "lambdas"
            / "gateway_trace_exporter.py"
        )
        gateway_trace_exporter = aws.lambda_.Function(
            "gateway-trace-exporter",
            name=f"{gateway_name}-trace-exporter",
            description=(
                "Forwards authoritative AgentCore Gateway policy spans "
                "to Honeycomb"
            ),
            role=trace_exporter_role.arn,
            runtime="python3.13",
            handler="gateway_trace_exporter.handler",
            architectures=["arm64"],
            code=pulumi.AssetArchive(
                {
                    "gateway_trace_exporter.py": pulumi.FileAsset(
                        str(trace_exporter_path)
                    )
                }
            ),
            environment={
                "variables": {
                    "AGENTCORE_GATEWAY_ARN": gateway.gateway_arn,
                    "AGENTCORE_GATEWAY_NAME": gateway.name,
                    "HONEYCOMB_API_HOST": honeycomb_api_host,
                    "HONEYCOMB_DATASET": honeycomb_dataset,
                    "HONEYCOMB_SECRET_ID": honeycomb_secret.arn,
                }
            },
            timeout=30,
            memory_size=128,
            tags=component_tags,
            opts=pulumi.ResourceOptions(
                depends_on=[
                    trace_exporter_policy,
                    trace_exporter_log_group,
                    honeycomb_secret_version,
                ]
            ),
        )
        trace_exporter_permission = aws.lambda_.Permission(
            "gateway-trace-exporter-cloudwatch",
            action="lambda:InvokeFunction",
            function=gateway_trace_exporter.name,
            principal="logs.amazonaws.com",
            source_account=account_id,
            source_arn=(
                f"arn:{partition}:logs:{region}:{account_id}:"
                "log-group:aws/spans:*"
            ),
        )
        aws.cloudwatch.LogSubscriptionFilter(
            "gateway-trace-exporter-subscription",
            name=f"{gateway_name}-policy-spans",
            log_group="aws/spans",
            destination_arn=gateway_trace_exporter.arn,
            filter_pattern=(
                '{ $.name = "AgentCore.Policy.AuthorizeAction" || '
                '$.name = "AgentCore.Gateway.InvokeTool" }'
            ),
            opts=pulumi.ResourceOptions(
                depends_on=[
                    gateway_trace_delivery,
                    trace_exporter_permission,
                ]
            ),
        )
    governance_properties = [
        {
            "name": "workflow_id",
            "type": "string",
            "description": "Workflow identifier used to reload governance state",
            "required": True,
        },
        {
            "name": "governance_source",
            "type": "string",
            "description": "Gateway interceptor that supplied external governance",
            "required": False,
        },
        {
            "name": "mutation",
            "type": "boolean",
            "description": "Control-plane supplied mutation classification",
            "required": True,
        },
        {
            "name": "session_tainted",
            "type": "boolean",
            "description": "Trusted repository taint state",
            "required": True,
        },
        {
            "name": "companion_posture",
            "type": "string",
            "description": "Trusted Companion posture",
            "required": True,
        },
        {
            "name": "snyk_posture",
            "type": "string",
            "description": "Trusted Snyk posture",
            "required": True,
        },
        {
            "name": "security_review",
            "type": "string",
            "description": "Trusted security review status",
            "required": True,
        },
        {
            "name": "financial_approval",
            "type": "string",
            "description": "Trusted financial approval status",
            "required": True,
        },
        {
            "name": "artifact_digest",
            "type": "string",
            "description": "Observed artifact digest",
            "required": True,
        },
        {
            "name": "reviewed_artifact_digest",
            "type": "string",
            "description": "Reviewed artifact digest",
            "required": True,
        },
        {
            "name": "environment",
            "type": "string",
            "description": "Deployment environment",
            "required": True,
        },
    ]
    tool_names = [
        "read_repository",
        "validate_iac",
        "generate_iac",
        "security_review",
        "get_approval_state",
        "apply_infrastructure",
        "rollback_infrastructure",
        "smoke_test",
    ]
    inline_payloads = [
        {
            "name": tool_name,
            "description": f"Deterministic Module 12 {tool_name} tool",
            "input_schema": {
                "type": "object",
                "description": "Trusted governance context for the tool call",
                "properties": governance_properties,
            },
            "output_schema": {
                "type": "object",
                "properties": [
                    {"name": "status", "type": "string", "required": True},
                    {"name": "mutation", "type": "boolean", "required": True},
                    {
                        "name": "infrastructure_changed",
                        "type": "boolean",
                        "required": True,
                    },
                ],
            },
        }
        for tool_name in tool_names
    ]
    tool_target = aws.bedrock.AgentcoreGatewayTarget(
        "agentcore-tool-target",
        gateway_identifier=gateway.gateway_id,
        name=TOOL_TARGET_NAME,
        description="Module 12 companion tool manifest",
        target_configuration={
            "mcp": {
                "lambda_": {
                    "lambda_arn": tool_function.arn,
                    "tool_schema": {"inline_payloads": inline_payloads},
                }
            }
        },
        credential_provider_configuration={"gateway_iam_role": {}},
        opts=pulumi.ResourceOptions(depends_on=[gateway, tool_function]),
    )
    policies: dict[str, native.bedrockagentcore.Policy] = {}
    runtime_principal_id = (
        f"arn:{partition}:sts::{account_id}:assumed-role/{prefix}-runtime"
    )
    for tool_name in (*READ_ONLY_TOOLS, *MUTATION_TOOLS):
        cedar_statement = gateway.gateway_arn.apply(
            lambda arn, tool=tool_name: build_cedar_statements(
                arn,
                target_name=TOOL_TARGET_NAME,
                principal_ids=[runtime_principal_id],
            )[tool]
        )
        policies[tool_name] = native.bedrockagentcore.Policy(
            f"policy-{tool_name.replace('_', '-')}",
            name=f"{policy_name_prefix}_p_{tool_name}",
            description=f"DevOps Companion authorization policy for {tool_name}",
            policy_engine_id=policy_engine.policy_engine_id,
            definition={"cedar": {"statement": cedar_statement}},
            enforcement_mode="ACTIVE",
            validation_mode="FAIL_ON_ANY_FINDINGS",
            opts=pulumi.ResourceOptions(
                provider=agentcore_provider,
                depends_on=[tool_target],
            ),
        )

    gateway_resource_policy = aws.bedrock.AgentcoreResourcePolicy(
        "gateway-resource-policy",
        resource_arn=gateway.gateway_arn,
        policy=pulumi.Output.all(gateway.gateway_arn, runtime_role.arn).apply(
            lambda values: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "RuntimeInvoke",
                            "Effect": "Allow",
                            "Principal": {"AWS": values[1]},
                            "Action": "bedrock-agentcore:InvokeGateway",
                            "Resource": values[0],
                        }
                    ],
                },
                sort_keys=True,
            )
        ),
        opts=pulumi.ResourceOptions(depends_on=[gateway]),
    )
    runtime_extra_policy = aws.iam.RolePolicy(
        "companion-runtime-permissions",
        role=runtime_role.id,
        policy=_policy(
            [
                {
                    "Sid": "EcrAuth",
                    "Effect": "Allow",
                    "Action": "ecr:GetAuthorizationToken",
                    "Resource": "*",
                },
                {
                    "Sid": "PullRuntimeImage",
                    "Effect": "Allow",
                    "Action": [
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    "Resource": runtime_repository.arn,
                },
                {
                    "Sid": "RuntimeServiceLogs",
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:DescribeLogStreams",
                        "logs:PutLogEvents",
                    ],
                    "Resource": [
                        f"arn:{partition}:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/{runtime_name}-*",
                        f"arn:{partition}:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/{runtime_name}-*:*",
                    ],
                },
                {
                    "Sid": "InvokeDemoModels",
                    "Effect": "Allow",
                    "Action": "bedrock:InvokeModel",
                    "Resource": [
                        f"arn:{partition}:bedrock:{region}:{account_id}:inference-profile/us.openai.gpt-5.6-luna",
                        f"arn:{partition}:bedrock:{region}:{account_id}:inference-profile/us.openai.gpt-5.6-terra",
                        f"arn:{partition}:bedrock:{region}:{account_id}:inference-profile/us.openai.gpt-5.6-sol",
                        f"arn:{partition}:bedrock:*::foundation-model/openai.gpt-5.6-luna",
                        f"arn:{partition}:bedrock:*::foundation-model/openai.gpt-5.6-terra",
                        f"arn:{partition}:bedrock:*::foundation-model/openai.gpt-5.6-sol",
                    ],
                },
                {
                    "Sid": "InvokeModule12Gateway",
                    "Effect": "Allow",
                    "Action": "bedrock-agentcore:InvokeGateway",
                    "Resource": gateway.gateway_arn,
                },
            ]
        ),
    )
    runtime = aws.bedrock.AgentcoreAgentRuntime(
        "agentcore-runtime",
        agent_runtime_name=runtime_name,
        description="Module 12 Strands agents with deterministic governance",
        agent_runtime_artifact={
            "container_configuration": {
                "container_uri": runtime_repository.repository_url.apply(
                    lambda url: f"{url}@{image_digest}"
                )
            }
        },
        role_arn=runtime_role.arn,
        environment_variables={
            "MODULE12_WORKFLOW_STATE_TABLE": workflow_table.name,
            "MODULE12_GOVERNANCE_STATE_TABLE": governance_table.name,
            "MODULE12_POSTURE_STATE_TABLE": posture_table.name,
            "MODULE12_POSTURE_SUBJECT": "companion-tools",
            "MODULE12_HONEYCOMB_SECRET_ARN": honeycomb_secret.arn,
            "MODULE12_HONEYCOMB_DATASET": honeycomb_dataset,
            "MODULE12_HONEYCOMB_OTLP_ENDPOINT": honeycomb_endpoint,
            "MODULE12_DEPLOYMENT_ENVIRONMENT": stack,
            "OTEL_SERVICE_NAME": honeycomb_dataset,
            "OTEL_SEMCONV_STABILITY_OPT_IN": (
                "gen_ai_latest_experimental,"
                "gen_ai_use_latest_invocation_tokens,"
                "gen_ai_unredacted_attributes="
            ),
            "MODULE12_LIVE_AGENTS": "true",
            "MODULE12_ANALYSIS_MODEL_ID": "us.openai.gpt-5.6-luna",
            "MODULE12_IAC_MODEL_ID": "us.openai.gpt-5.6-terra",
            "MODULE12_DEPLOYMENT_MODEL_ID": "us.openai.gpt-5.6-sol",
            "MODULE12_GATEWAY_URL": gateway.gateway_url,
            "MODULE12_GATEWAY_ID": gateway.gateway_id,
            "MODULE12_GATEWAY_TARGET_NAME": TOOL_TARGET_NAME,
        },
        network_configuration={"network_mode": "PUBLIC"},
        protocol_configuration={"server_protocol": "HTTP"},
        lifecycle_configurations=[
            {"idle_runtime_session_timeout": 60, "max_lifetime": 900}
        ],
        tags=component_tags,
        opts=pulumi.ResourceOptions(
            depends_on=[
                runtime_extra_policy,
                gateway_resource_policy,
                honeycomb_secret_version,
                *policies.values(),
            ]
        ),
    )
    outputs.update(
        {
            "securityControlsEnabled": True,
            "honeycombDataset": honeycomb_dataset,
            "runtimeName": runtime.agent_runtime_name,
            "runtimeArn": runtime.agent_runtime_arn,
            "runtimeId": runtime.agent_runtime_id,
            "gatewayName": gateway.name,
            "gatewayArn": gateway.gateway_arn,
            "gatewayId": gateway.gateway_id,
            "gatewayUrl": gateway.gateway_url,
            "toolGatewayTargetName": tool_target.name,
            "toolGatewayTargetId": tool_target.target_id,
            "policyEngineArn": policy_engine.policy_engine_arn,
            "policyEngineId": policy_engine.policy_engine_id,
            "policyArn": policies["read_repository"].policy_arn,
            "policyId": policies["read_repository"].policy_id,
            "policyArns": pulumi.Output.all(
                *[policy.policy_arn for policy in policies.values()]
            ),
            "policyIds": pulumi.Output.all(
                *[policy.policy_id for policy in policies.values()]
            ),
            "gatewayRoleArn": gateway_role.arn,
            "gatewayInterceptorFunctionName": interceptor_function.name,
            "gatewayInterceptorFunctionArn": interceptor_function.arn,
            "gatewayInterceptorRoleArn": interceptor_role.arn,
            "gatewayResourcePolicyId": gateway_resource_policy.id,
            "gatewayTracingEnabled": enable_gateway_tracing,
        }
    )
    if gateway_trace_delivery is not None:
        outputs["gatewayTraceDeliveryArn"] = gateway_trace_delivery.arn
    if gateway_trace_exporter is not None:
        outputs["gatewayTraceExporterName"] = gateway_trace_exporter.name
    return outputs
