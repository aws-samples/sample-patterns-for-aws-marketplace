"""Create the optional S3-backed Pulumi state bucket for Module 12.

The foundation stack cannot create the bucket that stores its own Pulumi
state, so this small boto3 bootstrap is intentionally separate. Local state
remains supported and is the default for offline work.

Usage:
    AWS_REGION=us-east-1 \
      python -m module12.infrastructure.bootstrap.state_backend --dry-run
    AWS_REGION=us-east-1 \
      python -m module12.infrastructure.bootstrap.state_backend
    pulumi login s3://<bucket>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError


PROJECT = "module12-security-observability"


@dataclass(frozen=True)
class StateBackend:
    bucket: str
    region: str
    account_id: str


def _code(error: ClientError) -> str:
    return error.response.get("Error", {}).get("Code", "")


def _tls_policy(bucket: str) -> str:
    arn = f"arn:aws:s3:::{bucket}"
    return json.dumps(
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


def resolve_backend(session: boto3.Session, prefix: str = "m12-pulumi-state") -> StateBackend:
    sts = session.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    region = session.region_name or "us-east-1"
    return StateBackend(f"{prefix}-{account_id}-{region}", region, account_id)


def ensure_backend(
    session: boto3.Session,
    backend: StateBackend,
    *,
    dry_run: bool = False,
    out=print,
) -> list[str]:
    """Ensure the state bucket's safety controls; return planned changes."""
    s3 = session.client("s3", region_name=backend.region)
    actions: list[str] = []
    try:
        s3.head_bucket(Bucket=backend.bucket, ExpectedBucketOwner=backend.account_id)
        exists = True
    except ClientError as error:
        if _code(error) not in {"404", "NoSuchBucket"}:
            raise RuntimeError(
                f"state bucket {backend.bucket} exists but is not accessible in "
                f"account {backend.account_id}"
            ) from error
        exists = False

    if not exists:
        actions.append(f"create versioned encrypted state bucket {backend.bucket}")
        if dry_run:
            return actions
        create_args = {"Bucket": backend.bucket, "ObjectOwnership": "BucketOwnerEnforced"}
        if backend.region != "us-east-1":
            create_args["CreateBucketConfiguration"] = {
                "LocationConstraint": backend.region
            }
        s3.create_bucket(**create_args)
    else:
        try:
            tags = {
                item["Key"]: item["Value"]
                for item in s3.get_bucket_tagging(Bucket=backend.bucket)["TagSet"]
            }
        except ClientError as error:
            if _code(error) != "NoSuchTagSet":
                raise
            tags = {}
        if tags.get("Project") not in {None, PROJECT}:
            raise RuntimeError(
                f"refusing to adopt state bucket {backend.bucket}: "
                f"Project tag is {tags.get('Project')!r}"
            )

    desired_tags = {"Project": PROJECT, "Purpose": "pulumi-state"}
    actions.append(f"set tags on {backend.bucket}: {desired_tags}")
    actions.append(f"block public access on {backend.bucket}")
    actions.append(f"enable versioning on {backend.bucket}")
    actions.append(f"enable AES256 default encryption on {backend.bucket}")
    actions.append(f"deny non-TLS access to {backend.bucket}")
    if dry_run:
        return actions

    s3.put_bucket_tagging(
        Bucket=backend.bucket,
        Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in desired_tags.items()]},
    )
    s3.put_public_access_block(
        Bucket=backend.bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_versioning(
        Bucket=backend.bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    s3.put_bucket_encryption(
        Bucket=backend.bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    },
                    "BucketKeyEnabled": True,
                }
            ]
        },
    )
    s3.put_bucket_policy(Bucket=backend.bucket, Policy=_tls_policy(backend.bucket))
    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print actions without changing AWS")
    parser.add_argument("--prefix", default="m12-pulumi-state")
    args = parser.parse_args(argv)

    session = boto3.Session()
    try:
        backend = resolve_backend(session, args.prefix)
        actions = ensure_backend(session, backend, dry_run=args.dry_run)
    except (ClientError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    verb = "Would" if args.dry_run else "Did"
    for action in actions:
        print(f"{verb}: {action}")
    print(f"Backend: s3://{backend.bucket}")
    print(f"Login:   pulumi login s3://{backend.bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
