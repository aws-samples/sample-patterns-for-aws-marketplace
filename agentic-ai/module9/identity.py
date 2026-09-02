# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/identity.py
====================
Access control for the ingestion and retrieval paths, built on the
Module 8 identity primitives (v5 Section 7).

Two identities, deliberately distinct:

- The **pipeline identity** writes to the knowledge base. It holds only the
  devops:pipeline:ingest scope, so it can load chunks but never retrieve
  them as an agent.
- The **agent read identities** (Orchestrator, DeployObserve,
  RepositoryAnalysis, InfrastructureGeneration) retrieve from corpora. Each
  role's policy caps which corpus scopes it may exercise: the history corpus
  (v5 Section 10.3) is readable only by Orchestrator and DeployObserve.

Enforcement is layered, matching v5 Section 7.2:

1. ``authorize_retrieval`` runs Module 8's ``authorize_agent_call`` at the
   agent boundary. A role without the corpus scope raises ``Auth0Error``
   before any query is issued.
2. ``compile_retrieval_filter`` builds the row-level-security pre-filter
   from the authorization decision, never from model output. The filter is
   applied server-side of the store by
   ``MongoStore.vector_search(filter_dict=...)`` as an Atlas $vectorSearch
   pre-filter, so unauthorized chunks are excluded before similarity
   scoring.

In mock mode (AGENT_MOCK_MODE=true, the Module 8 default) tokens come from
module8/mock/auth0_mock.py, so the whole authorization path runs offline
with the same code as the live Auth0 path.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from module8.config.models import Auth0Config
from module8.identity.auth0_client import Auth0Error  # noqa: F401 (re-exported)
from module8.identity.delegation import (
    AgentAuthorizationDecision,
    AgentAuthorizationPolicy,
    authorize_agent_call,
)
from module8.mock.auth0_mock import issue_user_token

# ---------------------------------------------------------------------------
# Scopes: one knowledge scope per corpus, one ingest scope for the pipeline
# ---------------------------------------------------------------------------

CORPUS_SCOPES: dict[str, str] = {
    "service": "devops:knowledge:service",
    "policy": "devops:knowledge:policy",
    "history": "devops:knowledge:history",
}

PIPELINE_INGEST_SCOPE = "devops:pipeline:ingest"

_ALL_CORPUS_SCOPES = frozenset(CORPUS_SCOPES.values())
_GENERAL_CORPUS_SCOPES = frozenset(
    {CORPUS_SCOPES["service"], CORPUS_SCOPES["policy"]}
)

# ---------------------------------------------------------------------------
# Module 8 authorization policies for Module 9's identities
# ---------------------------------------------------------------------------
# These are additive AgentAuthorizationPolicy instances: Module 8's own
# AGENT_POLICIES tuple is untouched. The pipeline identity is write-scoped
# and the read identities are corpus-scoped, which is the "agent identity
# vs pipeline identity" split Module 8 teaches.

PIPELINE_WRITE_POLICY = AgentAuthorizationPolicy(
    "DevOps Companion Ingestion Pipeline",
    "a2a://devops-companion/pipeline",
    "arn:aws:iam::111122223333:role/DevOpsCompanion-PipelineIngest",
    frozenset({"ingest_corpus"}),
    frozenset({PIPELINE_INGEST_SCOPE}),
    frozenset({PIPELINE_INGEST_SCOPE}),
    "Write-scoped knowledge base credential; no retrieval permission",
)

RETRIEVAL_POLICIES: dict[str, AgentAuthorizationPolicy] = {
    "Orchestrator": AgentAuthorizationPolicy(
        "DevOps Companion Orchestrator (Knowledge Read)",
        "a2a://devops-companion/orchestrator",
        "arn:aws:iam::111122223333:role/DevOpsCompanion-Orchestrator",
        frozenset({"retrieve_corpus"}),
        _ALL_CORPUS_SCOPES,
        _ALL_CORPUS_SCOPES,
        "Read-only knowledge base credential across all three corpora",
    ),
    "DeployObserve": AgentAuthorizationPolicy(
        "DevOps Companion Deploy+Observe Agent (Knowledge Read)",
        "a2a://devops-companion/deploy-observe",
        "arn:aws:iam::111122223333:role/DevOpsCompanion-DeployObserve",
        frozenset({"retrieve_corpus"}),
        _ALL_CORPUS_SCOPES,
        _ALL_CORPUS_SCOPES,
        "Read-only knowledge base credential across all three corpora",
    ),
    "RepositoryAnalysis": AgentAuthorizationPolicy(
        "DevOps Companion Repository Analysis Agent (Knowledge Read)",
        "a2a://devops-companion/analysis",
        "arn:aws:iam::111122223333:role/DevOpsCompanion-Analysis",
        frozenset({"retrieve_corpus"}),
        _GENERAL_CORPUS_SCOPES,
        _GENERAL_CORPUS_SCOPES,  # permission ceiling excludes the history corpus
        "Read-only knowledge base credential; history corpus excluded",
    ),
    "InfrastructureGeneration": AgentAuthorizationPolicy(
        "DevOps Companion Infrastructure Generation Agent (Knowledge Read)",
        "a2a://devops-companion/iac",
        "arn:aws:iam::111122223333:role/DevOpsCompanion-IaC",
        frozenset({"retrieve_corpus"}),
        _GENERAL_CORPUS_SCOPES,
        _GENERAL_CORPUS_SCOPES,  # permission ceiling excludes the history corpus
        "Read-only knowledge base credential; history corpus excluded",
    ),
}

VALID_AGENT_ROLES = frozenset(RETRIEVAL_POLICIES)


def _role_token(role: str, scopes: frozenset[str]) -> str:
    """Issue a deterministic mock token for a role via the Module 8 mock.

    In live mode the caller passes a real Auth0 token instead; this helper
    exists so mock mode exercises exactly the same authorization code path.
    """
    return issue_user_token(f"auth0|module9-{role.lower()}", sorted(scopes))[
        "access_token"
    ]


# ---------------------------------------------------------------------------
# Authorization entry points
# ---------------------------------------------------------------------------

def authorize_pipeline_write(
    corpus: str, token: str | None = None
) -> AgentAuthorizationDecision:
    """Authorize the pipeline identity to ingest into a corpus.

    Raises Auth0Error if the pipeline identity is not permitted to write.
    """
    config = Auth0Config()
    tok = token or _role_token("pipeline", PIPELINE_WRITE_POLICY.required_scopes)
    return authorize_agent_call(
        tok,
        config,
        PIPELINE_WRITE_POLICY,
        operation="ingest_corpus",
        required_scope=PIPELINE_INGEST_SCOPE,
    )


def authorize_retrieval(
    role: str, corpus: str, token: str | None = None
) -> AgentAuthorizationDecision:
    """Authorize an agent role to retrieve from a corpus.

    This is enforcement layer 1 (v5 Section 7.2): the Module 8 policy check
    at the agent boundary. Raises Auth0Error when the role's policy does not
    include the corpus scope, for example RepositoryAnalysis requesting the
    history corpus.
    """
    if role not in RETRIEVAL_POLICIES:
        raise Auth0Error(
            f"Unknown agent role {role!r}. Valid roles: {sorted(RETRIEVAL_POLICIES)}"
        )
    if corpus not in CORPUS_SCOPES:
        raise Auth0Error(
            f"Unknown corpus {corpus!r}. Valid corpora: {sorted(CORPUS_SCOPES)}"
        )
    policy = RETRIEVAL_POLICIES[role]
    config = Auth0Config()
    tok = token or _role_token(role, policy.required_scopes)
    return authorize_agent_call(
        tok,
        config,
        policy,
        operation="retrieve_corpus",
        required_scope=CORPUS_SCOPES[corpus],
    )


def compile_retrieval_filter(
    decision: AgentAuthorizationDecision, corpus: str
) -> dict:
    """Build the row-level-security pre-filter from an authorization decision.

    This is enforcement layer 2 (v5 Section 7.2): the filter is compiled
    from the validated decision, never from model output, and is applied
    server-side of the store as an Atlas $vectorSearch pre-filter. Values
    are plain equality because MongoStore wraps each entry in $eq.
    """
    if CORPUS_SCOPES[corpus] not in decision.effective_scopes:
        raise Auth0Error(
            f"Decision for {decision.agent} does not carry the "
            f"{CORPUS_SCOPES[corpus]} scope"
        )
    filter_dict: dict = {"corpus": corpus}
    if corpus == "history":
        # v5 Section 10.3: the history corpus is stamped
        # agent_scope: operations and only operations-scoped roles reach it.
        filter_dict["agent_scope"] = "operations"
    return filter_dict


def allowed_corpora(role: str) -> list[str]:
    """Return the corpora a role may retrieve from, per its Module 8 policy."""
    policy = RETRIEVAL_POLICIES.get(role)
    if policy is None:
        return []
    ceiling = policy.permission_ceiling_scopes
    return [name for name, scope in CORPUS_SCOPES.items() if scope in ceiling]


# ---------------------------------------------------------------------------
# Current-role context for the composed agent
# ---------------------------------------------------------------------------
# create_pipeline_agent() fixes the role at composition time. Tools read it
# from here so the LLM can never choose its own role.

_CURRENT_ROLE = "DeployObserve"


def set_current_role(role: str) -> None:
    global _CURRENT_ROLE
    if role not in RETRIEVAL_POLICIES:
        raise ValueError(
            f"Unknown agent role {role!r}. Valid roles: {sorted(RETRIEVAL_POLICIES)}"
        )
    _CURRENT_ROLE = role


def get_current_role() -> str:
    return _CURRENT_ROLE


# ---------------------------------------------------------------------------
# Audit records (mirrors the module8/audit/trail.py evidence-record shape)
# ---------------------------------------------------------------------------

def build_audit_record(
    pipeline_run_id: str,
    trace_point: str,
    answer: str,
    evidence_source: str,
    *,
    actor: str,
    action: str,
    required_scope: str | None = None,
    decision: str | None = None,
    token_fingerprint: str | None = None,
    details: dict | None = None,
) -> dict:
    """Build one audit evidence record for a pipeline or retrieval action.

    The dict shape mirrors module8/audit/trail.py so Module 9 lineage audit
    entries join the same evidence chain Module 8 produces.
    """
    record = {
        "workflow_execution_id": pipeline_run_id,
        "event_id": str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{pipeline_run_id}:{trace_point}")
        ),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trace_point": trace_point,
        "answer": answer,
        "evidence_source": evidence_source,
        "actor": actor,
        "action": action,
        "required_scope": required_scope,
        "decision": decision,
        "token_fingerprint": token_fingerprint,
        "details": details or {},
    }
    return record
