# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/config/pipeline_domain.py
==================================
PipelineDomainConfig extends Module 5's DomainConfig to compose the
DevOps Companion with governed-knowledge pipeline tools, mirroring how
module7/config/memory_domain.py composes memory onto a base agent.
"""
from __future__ import annotations

from module5.engine.domain_adapter import DomainConfig, GuardrailPolicy
from module9.config.corpora import HISTORY_CORPUS
from module9.prompts.system_prompts import build_pipeline_prompt_layers

_PIPELINE_TOOL_NAMES = [
    "recall_semantic_memory",
    "run_ingestion",
    "check_freshness",
    "get_provenance",
    "assert_quality",
    "list_corpora",
    "explain_staleness",
]


class PipelineDomainConfig(DomainConfig):
    """
    Domain configuration for the pipeline-aware DevOps Companion.

    Extends Module 5's DomainConfig with:
    - Governed-knowledge system prompt (recall with corpus filters, cite
      provenance, warn on staleness)
    - Six pipeline tools plus the Module 7 semantic recall tool
    - The same PII anonymization guardrail Module 7 enforces on writes
    - The history CorpusConfig on the dormant Bedrock KB seam

    Parameters
    ----------
    agent_role : str
        The Module 8 agent role this composition runs as (for example
        "DeployObserve" or "RepositoryAnalysis"). Retrieval filters are
        compiled from this role, not from model output.
    """

    def __init__(self, agent_role: str = "DeployObserve") -> None:
        if not agent_role or not isinstance(agent_role, str):
            raise ValueError(
                f"agent_role must be a non-empty string, got: {agent_role!r}"
            )
        super().__init__(
            name="pipeline_devops",
            display_name="DevOps Companion (Governed Knowledge)",
            prompt_layers=build_pipeline_prompt_layers(),
            tool_names=list(_PIPELINE_TOOL_NAMES),
            guardrail_policy=GuardrailPolicy(
                pii_handling="ANONYMIZE",
                pii_entities=["NAME", "EMAIL", "PHONE", "AWS_ACCESS_KEY"],
            ),
            corpus_config=HISTORY_CORPUS.corpus_config,
        )
        # Pipeline-specific metadata (not part of base DomainConfig)
        self.agent_role = agent_role
        self.corpora: list[str] = ["service", "policy", "history"]
        self.memory_type: str = "consolidated"  # reused; corpus field disambiguates
        self.neo4j_node_types: list[str] = ["Source", "Dataset", "Corpus", "Agent"]
