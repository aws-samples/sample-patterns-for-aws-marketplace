# Module 8: Agent Identity and Access Management

Module 8 follows one user-initiated DevOps Companion workflow through user
delegation, agent authorization, workload identity, audit correlation, and
credential isolation.

## What Is Live

| Boundary | Demo behavior |
|----------|---------------|
| Auth0 | Live Device Authorization Flow, access-token issuance, JWKS signature verification, and user-scope validation |
| CyberArk Agent Guard | Live MCP proxy startup, AWS Secrets Manager retrieval, protected-process injection, and request/response audit |
| Protected MCP tool | Live deterministic allowlist and credential-presence check |
| GitHub, approval, STS, CloudTrail | Representative evidence only; the demo makes no live calls to these systems |

The raw Auth0 token and injected secret are never added to audit records or
displayed in the terminal.

## Demo Sections

1. **The Identity Problem** - Identifies the user, orchestrator, specialists,
   and protected tool boundary.
2. **Delegation and Scope Narrowing** - Authenticates a user with Auth0 and
   applies deterministic agent authorization checks.
3. **Tracing the Delegation Chain** - Uses one `workflow_execution_id` to
   investigate backward from an AWS action to user delegation.
4. **Credential Isolation at the Tool Boundary** - Shows CyberArk Agent Guard
   injecting a Secrets Manager value only into a protected MCP process.

## Setup

From `agentic-ai/`:

```bash
source .venv/bin/activate
pip install -r module8/requirements.txt
```

Copy the Module 8 values from `.env.example` into `.env` and set:

```bash
AGENT_MOCK_MODE=false

# Auth0 Native Application and API
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_AUDIENCE=https://api.devops-companion.internal
AUTH0_DEVICE_CLIENT_ID=your-native-app-client-id
AUTH0_REQUIRED_SCOPES=devops:analyze devops:iac devops:deploy:staging
AUTH0_DEMO_USER_EMAILS=demo-user@example.com

# Optional read-only Auth0 dashboard inspection
# AUTH0_MGMT_TOKEN=short-lived-management-api-token

# CyberArk Agent Guard and AWS Secrets Manager
AWS_REGION=us-east-1
# AWS_PROFILE=your-aws-profile
MODULE8_AGC_SECRET_ID=devops-companion-github-token
MODULE8_AGC_SECRET_ENV=GITHUB_TOKEN
MODULE8_AGC_AUDIT_LOG=module8/generated/agent-guard-audit.log
```

For Auth0:

- Create an API whose Identifier equals `AUTH0_AUDIENCE`.
- Add the permissions listed in `AUTH0_REQUIRED_SCOPES`.
- Create a Native Application and enable Device Authorization Flow.
- Create the users listed in `AUTH0_DEMO_USER_EMAILS`.
- Optionally provide a Management API token with `read:clients`,
  `read:resource_servers`, and `read:users`.

For Agent Guard, store a safe demo value in AWS Secrets Manager in `us-east-1`.
The local Agent Guard provider used here expects that region.

```bash
aws secretsmanager create-secret \
  --region us-east-1 \
  --name devops-companion-github-token \
  --secret-string file://./private-secret-value.txt
```

## Authorization Model

Auth0 issues one user access token for the DevOps Companion API. The token's
`scope` claim contains the scopes requested and issued for that authorization
session. It may contain fewer entries than the user's full Auth0 permissions.

Each request handler validates the same token's signature, issuer, audience,
expiration, user subject, and required scope. It then checks the operation
against the receiving agent's policy and permission ceiling. The LLM does not
make this decision.

The token is authorization context. It cannot authenticate to target tools or
integrations. Agents identify themselves through their own IAM and
authenticated A2A principals, while target credentials and service policies
place a separate limit on downstream access.

| Specialist | Target credential model |
|------------|-------------------------|
| Analysis Agent | Read-only GitHub App installation token |
| IaC Agent | Separate GitHub App installation token for branches, commits, and pull requests |
| Deploy Agent | Temporary STS credentials for the approved deployment role |

In production, SDK-side checks can reject unauthorized dispatches before a
tool call. A managed boundary such as AgentCore Gateway with AgentCore Policy
can check the request again before forwarding it. Direct access paths must be
closed for the managed boundary to be authoritative.

## Correlation Model

Section 3 constructs a compact, sanitized evidence chain. Every record contains
the same `workflow_execution_id`. STS uses that value as `SourceIdentity`, and
CloudTrail carries it into actions made by the assumed role session.

The Auth0 subject, delegated scopes, and token fingerprint come from the
validated user token. GitHub events, human approval, STS role assumption, and
CloudTrail deployment records are representative.

## Agent Guard Boundary

Section 4 launches:

```text
demo process
  -> MCP client
  -> CyberArk Agent Guard MCP proxy
  -> protected MCP tool process
```

The agent requests `list_private_repositories`; it does not request the secret.
Agent Guard resolves the configured Secrets Manager reference and injects
`GITHUB_TOKEN` only into the protected process. The tool's Python allowlist
authorizes the operation, and Agent Guard records the MCP request and response.

The repository list is representative and no GitHub call is made. This proves
credential isolation and audit at the tool boundary. It does not prove that
the stored token is short-lived, automatically rotated, or zero-standing.
A production GitHub integration should mint a short-lived GitHub App
installation token for each authorized operation.

## Commands

```bash
# Full offline presentation
AGENT_MOCK_MODE=true python demos/module8_demo.py

# Auth0 configuration and tenant checks
AGENT_MOCK_MODE=false python -m module8.live_check

# Agent Guard local and AWS preflight
python -m module8.agent_guard_live check-local
python -m module8.agent_guard_live check-aws

# Full live presentation
AGENT_MOCK_MODE=false python demos/module8_demo.py

# Focused tests
python -m pytest tests/test_module8_identity.py -q
```

## Runtime Files

```text
module8/
|-- agent_guard_live.py       # Agent Guard proxy and audit verification
|-- audit/trail.py            # Compact cross-system evidence chain
|-- config/models.py          # Auth0 configuration
|-- identity/
|   |-- auth0_client.py       # Device Flow and OIDC/JWKS validation
|   |-- context.py            # Sanitized user authorization context
|   `-- delegation.py         # Agent policies and authorization checks
|-- live_check.py             # Read-only Auth0 preflight
|-- mcp/secret_probe_server.py
`-- mock/                     # Deterministic Auth0 and Agent Guard evidence
```
