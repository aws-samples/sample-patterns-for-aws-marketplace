# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/config/models.py
=========================
Model configuration for Module 9 Data Pipelines and Lineage.

Module 9 introduces no new model code: the chat model and the Titan
Embeddings v2 model are re-exported from module7/config/models.py so the
pipeline embeds with exactly the same 1024-dim vectors the Module 7
knowledge base already stores.
"""
from __future__ import annotations

from module7.config.models import (  # noqa: F401
    EMBEDDING_DIM,
    HAIKU_4_5,
    SONNET_4_6,
    TITAN_EMBED_V2,
    get_chat_bedrock_model,
    get_titan_embedding_model,
)
