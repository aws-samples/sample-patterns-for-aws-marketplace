# Module 12 Demo

This directory contains the implementation of the Module 12 Security and
Observability demo for the DevOps Companion.

The deployed demo uses these boundaries:

- One AgentCore Runtime request runs real Analysis, IaC, and Deployment
  Strands agents backed by Bedrock model calls. Their deliberately small replies
  are mocked status messages; they generate no code or real infrastructure.
- A fail-closed Strands `before_tool_call` intervention enforces trusted
  workflow state before the framework executes a consequential tool.
- An AgentCore Gateway request interceptor reloads externally governed state
  before Gateway evaluates the dedicated MCP tool request.
- AWS Lambda tools provide safe deterministic behavior.
- DynamoDB and S3 hold workflow, posture, and evidence state.
- EventBridge carries Snyk posture events.
- Honeycomb receives OpenTelemetry traces when its ingest credential
  is present in the Runtime's Secrets Manager entry.

## How Snyk findings are enforced

The offline demo parses a checked-in, Snyk CLI-shaped report for a manifest
containing `lodash@4.17.15`. The recorded November 1, 2026 scan contains eight
current findings: five high and three medium. The highest-severity,
most-constraining finding is `SNYK-JS-LODASH-15869625` (Arbitrary Code
Injection), and the aggregate remediation floor is `lodash@4.18.1`. The package
is never installed or executed; only its manifest, lock metadata, and normalized
scan result are used.

The publisher writes normalized finding evidence to S3 and emits a trusted
EventBridge posture event. The posture controller records
`snyk_posture=quarantine` in DynamoDB. The demo's containment policy treats
high and critical findings as quarantine-worthy.

There are two enforcement layers in one execution path:

1. The Companion Runtime reads that trusted posture and supplies it as
   host-owned Strands invocation state. A `before_tool_call` intervention
   evaluates the deterministic policy and returns typed `Proceed` or `Deny`.
   Strands short-circuits a denied call before the Runtime can invoke the
   external deployment tool. The security handler uses `on_error="deny"` so
   evaluation failures are fail-closed.
2. AgentCore Gateway has an authorization policy attached in `ENFORCE` mode.
   Before evaluation, a request interceptor replaces posture, approval,
   reviewed-digest, and environment fields with authoritative DynamoDB values.
   Gateway permits read-only MCP actions and permits `apply_infrastructure` or
   `rollback_infrastructure` only when those values, the Runtime-attested session
   taint and proposed digest, and the exact principal/action/resource boundary
   pass.

When the Strands intervention returns `Proceed`, the Runtime signs an MCP
request and routes `apply_infrastructure` through the deployed Gateway. Gateway
must authorize that request before the Lambda-backed simulation records it.
Section 2 also asks the deployed Runtime to make explicit Gateway probes while
quarantine is active: a read-only tool must succeed and the deployment tool must
be denied. This keeps both normal execution and presenter probes on the
Runtime's IAM identity. Gateway authorization rejects other callers. The
Gateway is pinned to the stateless MCP `2026-07-28` protocol so each probe can
be evaluated independently.

The three agents run sequentially inside the same AgentCore Runtime request and
runtime session. They do not need agent-to-agent handoff for this demo. The
Analysis agent uses `us.openai.gpt-5.6-luna`, the IaC agent uses
`us.openai.gpt-5.6-terra`, and the Deployment agent uses
`us.openai.gpt-5.6-sol`. Each prompt requests only a short fictional
acknowledgement. Session taint and the proposed artifact digest are computed by
the trusted Runtime workflow. Posture, approvals, the reviewed digest, and
environment are stored outside the model loop and reloaded by the Gateway
interceptor. None of these authorization inputs come from agent replies.

In deployed AWS mode, the demo driver starts a dedicated CodeBuild project that
runs `snyk test` against the same fixture lockfile. It also runs `snyk monitor`
to create or update a persistent Snyk project named
`DevOps Companion Tool Supply Chain`, with target reference `module12-demo`.
CodeBuild obtains
`SNYK_TOKEN` directly from Secrets Manager; the token is not managed by Pulumi,
passed by the driver, or available to the AgentCore Runtime. Exit code `1` is
intentionally accepted as "vulnerabilities found" so the report is still
published; other scanner failures stop the build. A clean or below-threshold
report takes the digest-recovery path instead of producing a false quarantine.

The two Snyk commands serve different purposes. The JSON from `snyk test`
drives the AWS posture and quarantine flow. `snyk monitor` publishes the same
dependency snapshot to the Snyk control plane so a presenter can show the
project and findings in the Snyk web console. No GitHub integration or separate
repository is required.

This is a software-supply-chain scan of a fixture lockfile representing the
deployment tool used by the DevOps Companion. It is not a scan of a Companion
workflow execution, model output, or the user's repository. The scan establishes
whether that tool remains trustworthy; a later workflow execution consumes the
resulting posture in both the Strands intervention and AgentCore Gateway
authorization when deciding whether the tool may be invoked.

## How Honeycomb tracing works

The AgentCore Runtime configures the OpenTelemetry SDK before it constructs the
first Strands agent. One `devops_companion.workflow` span represents the live
Runtime request. Beneath it, the trace connects:

- the Analysis, IaC, and Deployment agent stages;
- Strands model-invocation and tool-lifecycle spans;
- deterministic taint classification and policy decisions;
- simulated tool activity; and
- the signed AgentCore Gateway request, including its allow or deny outcome.

The Runtime accepts an incoming W3C trace context when AgentCore supplies one
and injects the current context into its outgoing Gateway request.

Section 3 uses Honeycomb as the behavioral investigation surface. It compares
successful and denied workflows, identifies the signals that distinguish them,
and measures the observed interval between quarantine and recovery.

In Honeycomb Query Builder, choose **Paste Query** and paste:

```json
{
  "calculations": [
    {
      "op": "COUNT"
    }
  ],
  "filters": [
    {
      "column": "name",
      "op": "=",
      "value": "policy.authorize"
    }
  ],
  "breakdowns": [
    "policy.decision",
    "policy.rule"
  ],
  "time_range": 86400
}
```

This is the serialized form of a query that visualizes `COUNT`, filters where
`name = "policy.authorize"`, and groups by `policy.decision` and `policy.rule`.

In the Overview table, find a `DENY` row. Under `policy.decision`, open the
three-dot menu beside `DENY` and choose **BubbleUp outliers**. On the BubbleUp
tab, confirm that the selection is `policy.decision = DENY` and the baseline is
all other events in the query. The comparison should independently surface
repository taint, pending financial approval, quarantined Snyk posture, and the
corresponding policy rules.

BubbleUp's **High** and **Medium** difference labels describe how strongly a
field distinguishes the selected workflows from their baseline. They are not
security severity ratings. For a focused Snyk investigation, return to
Overview. Under `policy.rule`, open the three-dot menu beside
`deny_quarantined_posture` and choose **BubbleUp outliers**.

When the full demo has run Section 2, Section 3 also provides a Honeycomb Query
Math query for the **observed quarantine window**. It subtracts the timestamp of
the first workflow that observed quarantined posture from the final allowed
workflow that observed healthy posture after recovery. This uses existing
workflow telemetry and does not add a new duration field. It measures the
observed enforcement window rather than the exact control-plane transition
duration. When `MODULE12_HONEYCOMB_UI_URL` is configured, the screen includes a
clickable Honeycomb Query Template link that opens and runs the pre-filled
duration query. Compact, line-wrapped, paste-ready JSON remains available as a
fallback.

Repeat the focused comparison for `deny_tainted_deployment` or
`deny_financial_approval` to investigate those denial paths independently.

## Run the demo

The presenter entry point is `demos/module12_demo.py`. Without deployment
configuration it runs the deterministic local workflow and does not require
AWS credentials:

```bash
source .venvs/module12/bin/activate

python demos/module12_demo.py
python demos/module12_demo.py --section 1
python demos/module12_demo.py --section 2
python demos/module12_demo.py --section 3
python demos/module12_demo.py --no-pause
```

Pass the deployed Pulumi stack to exercise the AgentCore Runtime, AWS-hosted
posture controller, AgentCore Gateway enforcement probe, and DynamoDB
evidence:

```bash
python demos/module12_demo.py --seed --seed-repetitions 4 --stack module12-demo
python demos/module12_demo.py --section 1 --stack module12-demo
python demos/module12_demo.py --section 2 --stack module12-demo
python demos/module12_demo.py --section 3 --stack module12-demo
python demos/module12_demo.py --stack module12-demo
```

Use `--outputs path/to/outputs.json` instead of `--stack` when Pulumi is not
available on the presenter machine. Set `MODULE12_HONEYCOMB_UI_URL` to the
Honeycomb environment URL to display it on the Honeycomb investigation screen.

### Local Honeycomb simulation

When Section 3 runs without a deployed stack, it builds an in-memory
Honeycomb-style dataset from the workflow's OpenTelemetry spans and
normalized outcome fields. The presenter can demonstrate:

- a wide policy event with workflow, posture, taint, approval, digest, and
  decision dimensions;
- a query over all denied policy decisions;
- a BubbleUp-style comparison of denied and successful workflows.

This is intentionally a local teaching simulation, not an emulator of
Honeycomb's storage or query engine. It makes no external network calls and
does not claim that Honeycomb received the events.

## Deployment quick start

The deployment uses Python 3.13 in `.venvs/module12`; `mise` is optional local
tooling and is not a project dependency. Install AWS CLI v2 and the Pulumi CLI
before continuing. Run these commands from `agentic-ai/`.

```bash
mise exec python@3.13 -- python -m venv .venvs/module12
source .venvs/module12/bin/activate
python -m pip install -r module12/requirements.txt -r module12/requirements-pulumi.txt

export AWS_PROFILE=your-aws-cli-profile
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION="$AWS_REGION"
aws sts get-caller-identity

python -m module12.infrastructure.bootstrap.state_backend --dry-run
python -m module12.infrastructure.bootstrap.state_backend
```

Confirm that `get-caller-identity` reports the account where Module 12 should be
created before continuing. When using workload credentials instead of a local
AWS CLI profile, omit `AWS_PROFILE`. The demo also accepts `--profile` and
`--region` for deployed runs.

Use either `pulumi login --local` or the printed S3 backend before initializing
the stack. For either backend, create a local passphrase file before initializing
the stack so Pulumi can encrypt secret configuration consistently:

```bash
read -rs 'PULUMI_PASSPHRASE?Pulumi config passphrase: '; print
export PULUMI_CONFIG_PASSPHRASE_FILE=/tmp/module12-pulumi-passphrase
(umask 077 && printf '%s' "$PULUMI_PASSPHRASE" > "$PULUMI_CONFIG_PASSPHRASE_FILE")
unset PULUMI_PASSPHRASE

pulumi -C module12/infrastructure/pulumi stack init module12-demo
pulumi -C module12/infrastructure/pulumi preview --stack module12-demo
pulumi -C module12/infrastructure/pulumi up --stack module12-demo
```

### Configure the Honeycomb ingest credential

In Honeycomb, choose the environment that will hold the demo traces and create
an Ingest Key with **Send Events**. If
`module12-security-observability` does not exist yet, either create it first or
temporarily grant **Create Datasets** so the first trace can create it. The
Runtime does not need a Honeycomb management or query credential.

Pulumi stores the complete Ingest Key as encrypted secret configuration, writes
it to Secrets Manager, and injects the secret ARN into AgentCore Runtime. Set
the key and service/dataset name before deploying:

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

Pulumi encrypts `honeycombIngestKey` in stack configuration and marks the
Secrets Manager value as secret. The Runtime receives only the Secrets Manager
ARN. For an EU Honeycomb environment, also set `honeycombEndpoint` to
`https://api.eu1.honeycomb.io/v1/traces`.

When `enableGatewayTracing` is true, AWS-managed Gateway root and policy
authorization spans are forwarded asynchronously from `aws/spans` to
Honeycomb. Their original trace and parent IDs are preserved, so Honeycomb
joins the authoritative Gateway decision beneath the Runtime's existing
Gateway client span.

Run the driver to send live traces:

```bash
export MODULE12_HONEYCOMB_UI_URL='https://ui.honeycomb.io/...'

python demos/module12_demo.py \
  --seed --seed-repetitions 4 \
  --section 3 --stack module12-demo
```

Four repetitions create twenty governed workflow traces while keeping the seed
operation under the Module 12 driver. Increase the value when BubbleUp needs a
larger comparison dataset; every workflow still performs the three
intentionally small live Bedrock model calls.

Store a Snyk service-account token as the raw secret value after the first
deployment. This prompt does not echo the token or place it in shell history:

```bash
read -rs 'SNYK_TOKEN?Snyk service-account token: '; print
printf '%s' "$SNYK_TOKEN" |
  aws secretsmanager put-secret-value \
    --secret-id m12-module12-demo/snyk \
    --secret-string file:///dev/stdin >/dev/null
unset SNYK_TOKEN
```

You do not need to create the Snyk project manually. The first successful AWS
Section 2 scan creates it in the default organization associated with the
stored token. In Snyk, open **Projects**, select
**DevOps Companion Tool Supply Chain**, and confirm the `module12-demo` target
reference.

Then run Section 2. The driver starts CodeBuild, waits for the scan, reads the
normalized S3 evidence, waits for DynamoDB posture to become `quarantine`, and
pauses on the Snyk project screen before continuing through the Runtime and
AgentCore Gateway enforcement checks:

```bash
python demos/module12_demo.py \
  --section 2 --stack module12-demo
```

Use `--no-pause` only for automated smoke tests or captured output.

The deployment creates the security and observability foundation, Companion
Runtime, Gateway, policy controls, dedicated Snyk CodeBuild scanner, and
deterministic Lambda tools. The environment deployment path remains simulated.
Review the non-destructive teardown plan with:

```bash
python -m module12.teardown --stack module12-demo --dry-run
```

After the stack is retired and its encrypted configuration is no longer needed,
remove the temporary passphrase file:

```bash
rm -f "$PULUMI_CONFIG_PASSPHRASE_FILE"
unset PULUMI_CONFIG_PASSPHRASE_FILE
```

## Demo sections

1. Framework and tool-boundary enforcement: the model proposes, policy disposes.
2. Snyk: quarantine the Companion tool supply chain.
3. Honeycomb: investigate behavior across workflows.

## Initial scenario

The Companion reads a repository and generates AWS infrastructure. A poisoned
repository result marks the session as tainted. The model may still propose an
environment deployment, but the enforcement layers deny the call. A recorded Snyk
finding can independently quarantine the deployment tool, after which
AgentCore Gateway denies deployment while leaving read-only analysis available.
