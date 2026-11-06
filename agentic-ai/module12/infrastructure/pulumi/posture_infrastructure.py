"""AWS posture publisher and quarantine controller resources."""
from __future__ import annotations

import json
from pathlib import Path

import pulumi
import pulumi_aws as aws

from module12.posture import LIVE_SCAN_BUILDSPEC


def _lambda_trust(account_id: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                    "Condition": {"StringEquals": {"aws:SourceAccount": account_id}},
                }
            ],
        },
        sort_keys=True,
    )


def deploy_posture_infrastructure(
    *,
    prefix: str,
    account_id: str,
    region: str,
    partition: str,
    tags: dict[str, str],
    evidence_bucket: aws.s3.Bucket,
    posture_table: aws.dynamodb.Table,
    posture_bus: aws.cloudwatch.EventBus,
    snyk_secret: aws.secretsmanager.Secret,
    operations_log: aws.cloudwatch.LogGroup,
) -> dict[str, pulumi.Input[str]]:
    component_tags = {**tags, "Layer": "posture-quarantine"}
    module_dir = Path(__file__).resolve().parents[2]
    scanner_source_key = "scanner/snyk-source.zip"
    scanner_source = aws.s3.BucketObject(
        "snyk-scanner-source",
        bucket=evidence_bucket.id,
        key=scanner_source_key,
        source=pulumi.AssetArchive(
            {
                "module12": pulumi.AssetArchive(
                    {
                        "__init__.py": pulumi.FileAsset(
                            str(module_dir / "__init__.py")
                        ),
                        "posture.py": pulumi.FileAsset(
                            str(module_dir / "posture.py")
                        ),
                        "posture_handler.py": pulumi.FileAsset(
                            str(module_dir / "posture_handler.py")
                        ),
                        "telemetry.py": pulumi.FileAsset(
                            str(module_dir / "telemetry.py")
                        ),
                        "fixtures": pulumi.AssetArchive(
                            {
                                "vulnerable_companion_tool": pulumi.AssetArchive(
                                    {
                                        "package.json": pulumi.FileAsset(
                                            str(
                                                module_dir
                                                / "fixtures"
                                                / "vulnerable_companion_tool"
                                                / "package.json"
                                            )
                                        ),
                                        "package-lock.json": pulumi.FileAsset(
                                            str(
                                                module_dir
                                                / "fixtures"
                                                / "vulnerable_companion_tool"
                                                / "package-lock.json"
                                            )
                                        ),
                                    }
                                )
                            }
                        ),
                    }
                )
            }
        ),
    )
    scanner_role = aws.iam.Role(
        "snyk-scanner-role",
        name=f"{prefix}-snyk-scan",
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
            },
            sort_keys=True,
        ),
        tags=component_tags,
    )
    scanner_role_policy = aws.iam.RolePolicy(
        "snyk-scanner-permissions",
        role=scanner_role.id,
        policy=pulumi.Output.all(
            evidence_bucket.arn,
            posture_bus.arn,
            snyk_secret.arn,
            operations_log.arn,
        ).apply(
            lambda values: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "ReadScannerSource",
                            "Effect": "Allow",
                            "Action": "s3:GetObject",
                            "Resource": (
                                f"{values[0]}/{scanner_source_key}"
                            ),
                        },
                        {
                            "Sid": "WriteScanEvidence",
                            "Effect": "Allow",
                            "Action": "s3:PutObject",
                            "Resource": [
                                f"{values[0]}/findings/*",
                                f"{values[0]}/scans/*",
                            ],
                        },
                        {
                            "Sid": "ReadSnykCredential",
                            "Effect": "Allow",
                            "Action": "secretsmanager:GetSecretValue",
                            "Resource": values[2],
                        },
                        {
                            "Sid": "PublishPostureEvent",
                            "Effect": "Allow",
                            "Action": "events:PutEvents",
                            "Resource": values[1],
                        },
                        {
                            "Sid": "ScannerLogs",
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": f"{values[3]}:*",
                        },
                    ],
                },
                sort_keys=True,
            )
        ),
    )
    scanner_project = aws.codebuild.Project(
        "snyk-scanner",
        name=f"{prefix}-snyk-scan",
        service_role=scanner_role.arn,
        artifacts={"type": "NO_ARTIFACTS"},
        source={
            "type": "S3",
            "location": evidence_bucket.bucket.apply(
                lambda bucket: f"{bucket}/{scanner_source_key}"
            ),
            "buildspec": LIVE_SCAN_BUILDSPEC,
        },
        environment={
            "compute_type": "BUILD_GENERAL1_SMALL",
            "image": "aws/codebuild/standard:7.0",
            "type": "LINUX_CONTAINER",
            "environment_variables": [
                {
                    "name": "SNYK_TOKEN",
                    "value": snyk_secret.arn,
                    "type": "SECRETS_MANAGER",
                },
                {
                    "name": "MODULE12_EVIDENCE_BUCKET",
                    "value": evidence_bucket.bucket,
                },
                {
                    "name": "MODULE12_POSTURE_EVENT_BUS",
                    "value": posture_bus.name,
                },
                {
                    "name": "MODULE12_TOOL_DIGEST",
                    "value": "sha256:" + ("b" * 64),
                },
                {
                    "name": "MODULE12_REVIEWED_TOOL_DIGEST",
                    "value": "sha256:" + ("a" * 64),
                },
            ],
        },
        logs_config={
            "cloudwatch_logs": {
                "group_name": operations_log.name,
                "status": "ENABLED",
            }
        },
        build_timeout=15,
        tags=component_tags,
        opts=pulumi.ResourceOptions(
            depends_on=[scanner_role_policy, scanner_source]
        ),
    )
    posture_log_group = aws.cloudwatch.LogGroup(
        "posture-controller-logs",
        name=f"/aws/lambda/{prefix}-posture-controller",
        retention_in_days=30,
        tags=component_tags,
    )
    posture_role = aws.iam.Role(
        "posture-controller-role",
        name=f"{prefix}-posture",
        assume_role_policy=_lambda_trust(account_id),
        tags=component_tags,
    )
    posture_role_policy = aws.iam.RolePolicy(
        "posture-controller-permissions",
        role=posture_role.id,
        policy=pulumi.Output.all(
            evidence_bucket.arn,
            posture_table.arn,
            posture_bus.arn,
            posture_log_group.arn,
        ).apply(
            lambda values: json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "FindingsEvidence",
                            "Effect": "Allow",
                            "Action": ["s3:PutObject"],
                            "Resource": f"{values[0]}/findings/*",
                        },
                        {
                            "Sid": "ScanEvidence",
                            "Effect": "Allow",
                            "Action": ["s3:PutObject"],
                            "Resource": f"{values[0]}/scans/*",
                        },
                        {
                            "Sid": "PostureTransitions",
                            "Effect": "Allow",
                            "Action": ["dynamodb:PutItem"],
                            "Resource": values[1],
                        },
                        {
                            "Sid": "PublishPostureEvents",
                            "Effect": "Allow",
                            "Action": ["events:PutEvents"],
                            "Resource": values[2],
                        },
                        {
                            "Sid": "LambdaLogs",
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            "Resource": f"{values[3]}:*",
                        },
                    ],
                },
                sort_keys=True,
            )
        ),
    )
    posture_function = aws.lambda_.Function(
        "posture-controller",
        name=f"{prefix}-posture-controller",
        description="Deterministic Snyk finding publisher and posture controller",
        role=posture_role.arn,
        runtime="python3.13",
        handler="posture_handler.handler",
        architectures=["arm64"],
        code=pulumi.AssetArchive(
            {
                "posture_handler.py": pulumi.FileAsset(
                    str(module_dir / "posture_handler.py")
                ),
                "posture.py": pulumi.FileAsset(str(module_dir / "posture.py")),
                "telemetry.py": pulumi.FileAsset(str(module_dir / "telemetry.py")),
            }
        ),
        environment={
            "variables": {
                "MODULE12_EVIDENCE_BUCKET": evidence_bucket.bucket,
                "MODULE12_POSTURE_EVENT_BUS": posture_bus.name,
                "MODULE12_POSTURE_TABLE": posture_table.name,
            }
        },
        timeout=30,
        tags=component_tags,
        opts=pulumi.ResourceOptions(depends_on=[posture_role_policy]),
    )
    posture_rule = aws.cloudwatch.EventRule(
        "posture-controller-rule",
        name=f"{prefix}-posture-events",
        description="Apply trusted posture transitions from Snyk-shaped events",
        event_bus_name=posture_bus.name,
        event_pattern=json.dumps(
            {
                "source": ["module12.snyk"],
                "detail-type": ["SnykFinding", "SnykPostureRecovered"],
            },
            sort_keys=True,
        ),
        tags=component_tags,
    )
    posture_target = aws.cloudwatch.EventTarget(
        "posture-controller-target",
        rule=posture_rule.name,
        event_bus_name=posture_bus.name,
        target_id="posture-controller",
        arn=posture_function.arn,
        opts=pulumi.ResourceOptions(depends_on=[posture_rule]),
    )
    posture_permission = aws.lambda_.Permission(
        "posture-controller-eventbridge-permission",
        statement_id="AllowEventBridgePostureEvents",
        action="lambda:InvokeFunction",
        function=posture_function.name,
        principal="events.amazonaws.com",
        source_arn=posture_rule.arn,
        opts=pulumi.ResourceOptions(depends_on=[posture_target]),
    )
    return {
        "snykScanBuildProjectName": scanner_project.name,
        "snykScanBuildProjectArn": scanner_project.arn,
        "snykScanRoleArn": scanner_role.arn,
        "snykScanSourceObjectKey": scanner_source_key,
        "postureControllerFunctionName": posture_function.name,
        "postureControllerFunctionArn": posture_function.arn,
        "postureControllerRoleArn": posture_role.arn,
        "postureControllerRuleName": posture_rule.name,
        "postureControllerRuleArn": posture_rule.arn,
        "postureControllerLogGroupName": posture_log_group.name,
        "postureControllerPermissionId": posture_permission.id,
    }
