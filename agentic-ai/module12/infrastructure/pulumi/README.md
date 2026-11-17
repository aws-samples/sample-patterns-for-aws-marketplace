# Module 12 Pulumi foundation

This Pulumi program creates the Module 12 security and observability
foundation: durable evidence, logging, workflow state, the Companion Runtime,
Gateway, governance policy, request interceptor, and deterministic Lambda
tools. The environment deployment path remains simulation-only.

## Runtime and dependencies

The repository does not require `mise`; it is only a convenient local tool for
selecting Python 3.13. Install AWS CLI v2 and the Pulumi CLI before continuing.
Run these commands from `agentic-ai/`:

```bash
mise exec python@3.13 -- python -m venv .venvs/module12
source .venvs/module12/bin/activate
python -m pip install -r module12/requirements.txt -r module12/requirements-pulumi.txt

export AWS_PROFILE=your-aws-cli-profile
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION="$AWS_REGION"
aws sts get-caller-identity
```

Confirm that the command reports the account where Module 12 should be created.
When using workload credentials instead of a local AWS CLI profile, omit
`AWS_PROFILE`.

## Pulumi state

Local state is suitable for offline previews:

```bash
pulumi login --local
```

For AWS-backed state, bootstrap a separate versioned and encrypted bucket.
The bucket is separate because a Pulumi stack cannot create the bucket that
stores its own state:

```bash
python -m module12.infrastructure.bootstrap.state_backend --dry-run
python -m module12.infrastructure.bootstrap.state_backend
pulumi login s3://<printed-bucket>
```

For either backend, create a local passphrase file before initializing the
stack so Pulumi can encrypt secret configuration consistently:

```bash
read -rs 'PULUMI_PASSPHRASE?Pulumi config passphrase: '; print
export PULUMI_CONFIG_PASSPHRASE_FILE=/tmp/module12-pulumi-passphrase
(umask 077 && printf '%s' "$PULUMI_PASSPHRASE" > "$PULUMI_CONFIG_PASSPHRASE_FILE")
unset PULUMI_PASSPHRASE

pulumi -C module12/infrastructure/pulumi stack init module12-demo
```

## Preview and deploy

The following commands use the verified AWS profile, Region, and Pulumi
passphrase configured above:

```bash
pulumi -C module12/infrastructure/pulumi preview --stack module12-demo
pulumi -C module12/infrastructure/pulumi up --stack module12-demo
```

The stack exports the bucket, ECR repository, log groups, workflow, governance,
and posture tables, EventBridge bus, secret ARNs, the Gateway request
interceptor, the dedicated Snyk CodeBuild scanner, and least-privilege role
ARNs. The Runtime can read but cannot write the governance and posture tables.
The interceptor reloads those values before Gateway authorization, and the
Gateway accepts invocation only from the Module 12 Runtime role.

Create a Honeycomb Ingest Key with **Send Events**. If the service/dataset does
not exist yet, create it first or temporarily include **Create Datasets**.
Copy the complete Ingest Key shown once, then store it as encrypted Pulumi
configuration. Pulumi writes that value into Secrets Manager during deployment:

```bash
read -rs 'HONEYCOMB_INGEST_KEY?Honeycomb Ingest Key: '; print

pulumi -C module12/infrastructure/pulumi \
  config set --secret honeycombIngestKey "$HONEYCOMB_INGEST_KEY" \
  --stack module12-demo

pulumi -C module12/infrastructure/pulumi \
  config set honeycombDataset module12-security-observability \
  --stack module12-demo

pulumi -C module12/infrastructure/pulumi \
  config set enableGatewayTracing true \
  --stack module12-demo

unset HONEYCOMB_INGEST_KEY

pulumi -C module12/infrastructure/pulumi up --stack module12-demo
```

For an EU Honeycomb environment, set `honeycombEndpoint` to
`https://api.eu1.honeycomb.io/v1/traces` before deploying.

When `enableGatewayTracing` is true, the stack enables AWS-managed tracing for
the DevOps Companion Gateway. A scoped CloudWatch Logs subscription forwards
only the Gateway root span and authoritative policy-authorization span to a
small Lambda exporter. The exporter preserves their trace and parent IDs so
Honeycomb joins them beneath the Runtime's existing Gateway client span.

Store the raw Snyk token after deployment:

```bash
read -rs 'SNYK_TOKEN?Snyk service-account token: '; print
printf '%s' "$SNYK_TOKEN" |
  aws secretsmanager put-secret-value \
    --secret-id m12-module12-demo/snyk \
    --secret-string file:///dev/stdin >/dev/null
unset SNYK_TOKEN
```

The AWS Section 2 driver starts the scanner and waits for the quarantine event:

```bash
python demos/module12_demo.py \
  --section 2 --stack module12-demo
```

The scan runs both `snyk test` and `snyk monitor`. The former supplies the JSON
evidence used by the posture controller; the latter creates or updates the
console-visible Snyk project **DevOps Companion Tool Supply Chain** under target
reference `module12-demo`. The project is created automatically in the default
organization associated with the stored token.

Use `--no-pause` only for automated smoke tests or captured output.

## Teardown

Review the plan before taking any destructive action:

```bash
python -m module12.teardown --stack module12-demo --dry-run
```

The plan is intentionally non-destructive. The evidence bucket uses
`force_destroy=false`, and the state bucket must be removed separately only
after every stack that uses it has been retired.

After the stack is retired and its encrypted configuration is no longer needed,
remove the temporary passphrase file:

```bash
rm -f "$PULUMI_CONFIG_PASSPHRASE_FILE"
unset PULUMI_CONFIG_PASSPHRASE_FILE
```
