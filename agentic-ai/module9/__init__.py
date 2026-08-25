# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Module 9: Data Pipelines and Lineage.

Streams DevOps events through Confluent Cloud (managed Kafka), lands and
governs them in Databricks (Delta Lake + Unity Catalog), then chunks,
validates, embeds, and loads them into the Module 7 knowledge base with
full lineage metadata. Access control builds on the Module 8 identity
primitives.
"""
