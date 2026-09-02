# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/agent.py
=================
Pipeline-aware DevOps Companion factory for Module 9.

Composes the DevOps Companion via the Module 5 Domain Adaptation Engine
(the same one-call pattern Module 7 uses): PipelineDomainConfig drives the
governed-knowledge system prompt, the six pipeline tools plus governed
recall, and the PII guardrail policy.

The agent's access role is fixed at composition time. Retrieval filters
are compiled from the role by the runtime, never by the model, so the
row-level-security guarantee holds even if the agent's context window is
manipulated (v5 Section 7.2).

Usage
-----
    from module9.agent import create_pipeline_agent

    agent, session_id = create_pipeline_agent(role="DeployObserve")
    result = agent.invoke(
        {"messages": [("user", "What was the latest checkout-api deployment?")]},
        config={"configurable": {"thread_id": session_id}},
    )
"""
from __future__ import annotations

import uuid

from module9.config.models import SONNET_4_6, get_chat_bedrock_model
from module9.config.pipeline_domain import PipelineDomainConfig
from module9.identity import VALID_AGENT_ROLES, set_current_role
from module9.tools.pipeline_tools import PIPELINE_TOOLS, make_governed_recall


def create_pipeline_agent(
    role: str = "DeployObserve",
    *,
    region: str | None = None,
    verbose: bool = True,
    model_id: str = SONNET_4_6,
    session_id: str | None = None,
    streaming: bool = False,
    checkpointer=None,
) -> tuple:
    """
    Create the pipeline-aware DevOps Companion.

    Returns a (compiled_graph, session_id) tuple, matching the Module 7
    factory shape.

    Parameters
    ----------
    role : str
        Module 8 agent role for retrieval authorization: one of
        "Orchestrator", "DeployObserve", "RepositoryAnalysis",
        "InfrastructureGeneration". Fixed at composition time.
    region : str, optional
        AWS region override.
    verbose : bool
        Print configuration summary to stdout.
    model_id : str
        CRIS inference profile ID. Defaults to Claude Sonnet 4.6.
    session_id : str, optional
        Thread ID for session continuity. Auto-generated if not provided.
    streaming : bool
        Enable token-by-token streaming on the model.
    checkpointer : BaseCheckpointSaver, optional
        Session backend. Defaults to none: Module 9's focus is the data
        pipeline; wire a Module 7 checkpointer here for session continuity.

    Raises
    ------
    ValueError
        If role is not a valid Module 8 agent role.
    """
    from module5.engine.domain_adapter import DomainAdapter

    if role not in VALID_AGENT_ROLES:
        raise ValueError(
            f"role must be one of {sorted(VALID_AGENT_ROLES)}, got {role!r}"
        )
    set_current_role(role)

    config = PipelineDomainConfig(role)
    base_model = get_chat_bedrock_model(
        region=region, model_id=model_id, streaming=streaming
    )

    # Registry: six pipeline tools plus governed recall bound to the role.
    registry = dict(PIPELINE_TOOLS)
    registry["recall_semantic_memory"] = make_governed_recall(role)

    for name in config.tool_names:
        if name not in registry:
            raise ValueError(
                f"Tool '{name}' listed in PipelineDomainConfig but not found "
                f"in the tool registry. Available: {list(registry.keys())}"
            )

    adapter = DomainAdapter(registry)
    domain_agent = adapter.adapt(base_model, config, checkpointer=checkpointer)
    agent_graph = domain_agent.agent

    sid = session_id or str(uuid.uuid4())

    if verbose:
        import os

        from module9.config.settings import is_mock_confluent, is_mock_databricks
        from module9.ingestion.kb_sink import resolve_sink

        partners = (
            f"Confluent {'mock' if is_mock_confluent() else 'live'}, "
            f"Databricks {'mock' if is_mock_databricks() else 'live'}"
        )
        try:
            sink = resolve_sink().info()
            sink_label = f"{sink.display_name or sink.backend} ({sink.detail})"
        except Exception as exc:
            sink_label = f"unresolved ({exc})"

        print(f"  [Module 9 Pipeline Agent] {config.display_name}")
        print(f"  [Domain] {config.name}")
        print(f"  [Agent role] {role}")
        print(f"  [Model] {model_id}")
        print(f"  [Tools] {len(config.tool_names)}: {', '.join(config.tool_names)}")
        print(f"  [Partners] {partners}")
        print(f"  [Knowledge sink] {sink_label}")
        print(f"  [Session ID] {sid}")
        print()

    return agent_graph, sid
