# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/config/settings.py
===========================
Environment configuration for the Module 9 pipeline integrations.

Confluent Cloud (Act 1) and Databricks (Act 2) settings are read from
environment variables and never hard-coded. Setting AGENT_MOCK_PIPELINE=true
swaps both partner integrations for the in-process mocks in module9/mock,
mirroring the Module 7 AGENT_MOCK_MEMORY convention. The two flags layer:
AGENT_MOCK_PIPELINE mocks Confluent and Databricks, AGENT_MOCK_MEMORY mocks
the Module 7 MongoDB Atlas and Neo4j backends. Set both for a fully offline
run with no credentials.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def is_mock_pipeline() -> bool:
    """Whether Confluent and Databricks are served by in-process mocks."""
    return os.getenv("AGENT_MOCK_PIPELINE", "").lower() == "true"


def is_mock_memory() -> bool:
    """Whether the Module 7 memory backends are mocked (existing flag)."""
    return os.getenv("AGENT_MOCK_MEMORY", "").lower() == "true"


def is_mock_confluent() -> bool:
    """Whether Confluent alone is mocked.

    Granular flag so the demo can degrade one partner without the other:
    if Confluent is unreachable on stage, Databricks can stay live.
    AGENT_MOCK_PIPELINE implies both.
    """
    return (
        os.getenv("CONFLUENT_MOCK", "").lower() == "true" or is_mock_pipeline()
    )


def is_mock_databricks() -> bool:
    """Whether Databricks alone is mocked. AGENT_MOCK_PIPELINE implies both."""
    return (
        os.getenv("DATABRICKS_MOCK", "").lower() == "true" or is_mock_pipeline()
    )


def is_mock_lineage() -> bool:
    """Whether Unity Catalog lineage reads are served locally.

    Narrow fallback for workspaces where the system tables are not
    readable: Delta writes, versions, and every other Databricks
    interaction stay live, and only the lineage record read is synthesized.
    Implied by AGENT_MOCK_PIPELINE, which mocks Databricks entirely.
    """
    return (
        os.getenv("DATABRICKS_MOCK_LINEAGE", "").lower() == "true"
        or is_mock_databricks()
    )


@dataclass
class ConfluentSettings:
    """Confluent Cloud connection settings for the devops-events topic.

    All values come from environment variables. The API key and secret are
    cluster-scoped credentials created in the Confluent Cloud console; they
    must never be committed to version control.
    """

    bootstrap_servers: str = field(
        default_factory=lambda: os.getenv("CONFLUENT_BOOTSTRAP_SERVERS", "")
    )
    api_key: str = field(default_factory=lambda: os.getenv("CONFLUENT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("CONFLUENT_API_SECRET", ""))
    topic: str = field(default_factory=lambda: os.getenv("CONFLUENT_TOPIC", "devops-events"))
    group_id: str = field(
        default_factory=lambda: os.getenv("CONFLUENT_GROUP_ID", "module9-ingestion")
    )

    def client_config(self) -> dict:
        """Return the confluent-kafka client configuration for Confluent Cloud.

        Client logging is held at error level and broker metrics push is
        disabled, so librdkafka's informational lines do not interleave with
        the demo output on screen.
        """
        return {
            "bootstrap.servers": self.bootstrap_servers,
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": self.api_key,
            "sasl.password": self.api_secret,
            "log_level": 3,
            "enable.metrics.push": False,
        }

    def validate_for_live(self) -> None:
        """Raise ValueError listing any settings missing for the live path."""
        missing = [
            name
            for name, value in (
                ("CONFLUENT_BOOTSTRAP_SERVERS", self.bootstrap_servers),
                ("CONFLUENT_API_KEY", self.api_key),
                ("CONFLUENT_API_SECRET", self.api_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Confluent live mode requires environment variables: "
                + ", ".join(missing)
                + ". Set AGENT_MOCK_PIPELINE=true to run without Confluent Cloud."
            )


@dataclass
class KnowledgeBaseSettings:
    """Amazon Bedrock Managed Knowledge Base settings for the pipeline sink.

    The knowledge base is provisioned outside this repo, in the console or by
    whatever IaC you already use, and pointed at here by id. Nothing in
    Module 9 creates or destroys it. If the id is unset, the pipeline falls
    back to the Module 7 memory contracts, and to the in-process mock under
    AGENT_MOCK_MEMORY, so the module always stands alone.
    """

    knowledge_base_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_KB_ID", "")
    )
    data_source_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_KB_DATA_SOURCE_ID", "")
    )
    region: str = field(
        default_factory=lambda: os.getenv("BEDROCK_KB_REGION", "")
        or os.getenv("AWS_REGION", "us-east-1")
    )

    @property
    def configured(self) -> bool:
        """True when both the knowledge base and its data source are set."""
        return bool(self.knowledge_base_id and self.data_source_id)

    def validate_for_live(self) -> None:
        missing = [
            name
            for name, value in (
                ("BEDROCK_KB_ID", self.knowledge_base_id),
                ("BEDROCK_KB_DATA_SOURCE_ID", self.data_source_id),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Amazon Bedrock Knowledge Base sink requires environment variables: "
                + ", ".join(missing)
                + ". Leave them unset to use the Module 7 memory contracts."
            )


@dataclass
class DatabricksSettings:
    """Databricks workspace settings for the Delta Lake landing zone.

    The live path uses a serverless SQL warehouse (DATABRICKS_HTTP_PATH) and
    a personal access token. Unity Catalog lineage is read from the
    system.access.table_lineage system table.
    """

    host: str = field(default_factory=lambda: os.getenv("DATABRICKS_HOST", ""))
    token: str = field(default_factory=lambda: os.getenv("DATABRICKS_TOKEN", ""))
    http_path: str = field(default_factory=lambda: os.getenv("DATABRICKS_HTTP_PATH", ""))
    catalog: str = field(default_factory=lambda: os.getenv("DATABRICKS_CATALOG", "devops"))
    bronze_schema: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_BRONZE_SCHEMA", "bronze")
    )
    silver_schema: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_SILVER_SCHEMA", "silver")
    )
    bronze_table: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_BRONZE_TABLE", "raw_events")
    )
    silver_table: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_SILVER_TABLE", "deployment_events")
    )

    @property
    def hostname(self) -> str:
        """Bare workspace hostname, with any scheme or trailing slash removed."""
        return (
            self.host.replace("https://", "").replace("http://", "").rstrip("/")
        )

    @property
    def bronze_full_name(self) -> str:
        return f"{self.catalog}.{self.bronze_schema}.{self.bronze_table}"

    @property
    def silver_full_name(self) -> str:
        return f"{self.catalog}.{self.silver_schema}.{self.silver_table}"

    def validate_for_live(self) -> None:
        """Raise ValueError listing any settings missing for the live path."""
        missing = [
            name
            for name, value in (
                ("DATABRICKS_HOST", self.host),
                ("DATABRICKS_TOKEN", self.token),
                ("DATABRICKS_HTTP_PATH", self.http_path),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Databricks live mode requires environment variables: "
                + ", ".join(missing)
                + ". Set AGENT_MOCK_PIPELINE=true to run without Databricks."
            )
