# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/kb_sink.py
=============================
The knowledge sink: where governed chunks land and where the agent reads
them back.

One interface, three backends, chosen by environment so the module stands
alone without a pile of partner accounts to maintain:

1. **Amazon Bedrock Managed Knowledge Base** when BEDROCK_KB_ID and
   BEDROCK_KB_DATA_SOURCE_ID are set. Bedrock owns the vector store,
   indexing, embedding, and retrieval, so there is no vector database to
   provision here and nothing for this repo to create or tear down. The
   knowledge base is built outside the repo and pointed at by id.
2. **Module 7 memory contracts** when MongoDB Atlas credentials are present:
   MongoStore.upsert plus vector_search, embedded with Titan v2 through the
   Module 7 EmbeddingService. This is the continuity path for viewers who
   followed Module 7.
3. **In-process mock** otherwise, or whenever a configured backend turns out
   to be unreachable. The demo degrades instead of failing.

The pipeline code above this file does not branch on backend. Metadata
stamping, quality gates, lineage, and access control are identical in all
three cases; only the storage and retrieval calls differ.

Access control note: the row-level-security filter is applied by the
backend, not here. On the managed knowledge base it becomes a
managedSearchConfiguration metadata filter, evaluated server side before
results are returned. On Atlas it becomes a $vectorSearch pre-filter. Both
exclude unauthorized chunks before they can reach the agent's context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from module9.config.settings import KnowledgeBaseSettings, is_mock_memory

logger = logging.getLogger(__name__)

BACKEND_BEDROCK_KB = "bedrock-managed-kb"
BACKEND_MODULE7 = "module7-memory"
BACKEND_MOCK = "in-process-mock"

# Embedding attribution per backend, written into chunk metadata so
# provenance never overstates what happened.
EMBEDDING_TITAN = "amazon.titan-embed-text-v2:0"
EMBEDDING_MANAGED = "Amazon Bedrock service-managed embedding model"


@dataclass
class SinkInfo:
    """Describes the active sink, for display and for chunk metadata.

    ``backend`` is the machine identifier written into chunk metadata and
    asserted in tests. ``display_name`` is what appears on screen, using
    full service names.
    """

    backend: str
    detail: str
    embedding_model: str
    embeds_internally: bool
    display_name: str = ""


# ---------------------------------------------------------------------------
# Metadata conversion for the managed knowledge base
# ---------------------------------------------------------------------------
# Inline attributes are typed. Our Appendix B metadata carries strings,
# integers, booleans, lists, and None. None is dropped because an absent
# attribute and a null attribute are the same thing to a metadata filter.

def to_inline_attributes(metadata: dict) -> list[dict]:
    """Convert chunk metadata to Amazon Bedrock inline metadata attributes.

    Managed knowledge bases accept STRING, NUMBER, and STRING_LIST inline
    attributes. BOOLEAN is rejected at index time even though the API shape
    allows it, so booleans are encoded as the strings "true" and "false",
    which filter predictably with equals.
    """
    attributes: list[dict] = []
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, bool):
            typed = {"type": "STRING", "stringValue": "true" if value else "false"}
        elif isinstance(value, (int, float)):
            typed = {"type": "NUMBER", "numberValue": float(value)}
        elif isinstance(value, (list, tuple)):
            items = [str(v) for v in value if v is not None]
            if not items:
                continue
            typed = {"type": "STRING_LIST", "stringListValue": items}
        else:
            text = str(value)
            if not text:
                continue
            typed = {"type": "STRING", "stringValue": text}
        attributes.append({"key": key, "value": typed})
    return attributes


def to_retrieval_filter(filter_dict: dict | None) -> dict | None:
    """Compile a metadata filter dict into an Amazon Bedrock retrieval filter.

    Single key becomes equals; multiple keys become andAll of equals, which
    is how the role-derived row-level-security filter is enforced.
    """
    if not filter_dict:
        return None
    clauses = [
        {"equals": {"key": key, "value": value}}
        for key, value in sorted(filter_dict.items())
    ]
    if len(clauses) == 1:
        return clauses[0]
    return {"andAll": clauses}


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class BedrockManagedKBSink:
    """Amazon Bedrock Managed Knowledge Base sink.

    Chunks are submitted with IngestKnowledgeBaseDocuments against a custom
    data source, so this pipeline keeps ownership of chunking: one chunk in,
    one document indexed, with the data source configured for no further
    chunking. Bedrock performs the embedding with its service-managed model.
    """

    def __init__(self, settings: KnowledgeBaseSettings) -> None:
        import boto3

        settings.validate_for_live()
        self._settings = settings
        session = boto3.Session(region_name=settings.region)
        self._agent = session.client("bedrock-agent")
        self._runtime = session.client("bedrock-agent-runtime")

    def info(self) -> SinkInfo:
        return SinkInfo(
            backend=BACKEND_BEDROCK_KB,
            detail=(
                f"knowledge base {self._settings.knowledge_base_id}, "
                f"data source {self._settings.data_source_id}, "
                f"region {self._settings.region}"
            ),
            embedding_model=EMBEDDING_MANAGED,
            embeds_internally=True,
            display_name="Amazon Bedrock managed knowledge base",
        )

    def health_check(self) -> str:
        """Confirm the knowledge base and data source exist and are usable."""
        kb = self._agent.get_knowledge_base(
            knowledgeBaseId=self._settings.knowledge_base_id
        )["knowledgeBase"]
        if kb["status"] not in ("ACTIVE", "UPDATING"):
            raise RuntimeError(
                f"knowledge base status is {kb['status']}, expected ACTIVE"
            )
        self._agent.get_data_source(
            knowledgeBaseId=self._settings.knowledge_base_id,
            dataSourceId=self._settings.data_source_id,
        )
        kb_type = kb.get("knowledgeBaseConfiguration", {}).get("type", "UNKNOWN")
        return f"{kb['name']} ({kb_type}, {kb['status']})"

    def upsert_chunk(self, doc_id: str, content: str, metadata: dict) -> str:
        """Index one chunk. Re-submitting the same doc_id replaces it."""
        attributes = to_inline_attributes({**metadata, "doc_id": doc_id})
        response = self._agent.ingest_knowledge_base_documents(
            knowledgeBaseId=self._settings.knowledge_base_id,
            dataSourceId=self._settings.data_source_id,
            documents=[
                {
                    "metadata": {
                        "type": "IN_LINE_ATTRIBUTE",
                        "inlineAttributes": attributes,
                    },
                    "content": {
                        "dataSourceType": "CUSTOM",
                        "custom": {
                            "customDocumentIdentifier": {"id": doc_id},
                            "sourceType": "IN_LINE",
                            "inlineContent": {
                                "type": "TEXT",
                                "textContent": {"data": content},
                            },
                        },
                    },
                }
            ],
        )

        # The API accepts the request and reports per-document outcomes in the
        # response body, so a rejected document does not raise. Surface it as
        # an error rather than reporting a successful load that never landed.
        for detail in response.get("documentDetails", []):
            if detail.get("status") == "FAILED":
                raise RuntimeError(
                    f"Knowledge base rejected {doc_id}: "
                    f"{detail.get('statusReason', 'no reason given')}"
                )
        return f"Indexed {doc_id} in knowledge base {self._settings.knowledge_base_id}"

    def search(
        self, query: str, filter_dict: dict | None = None, top_k: int = 5
    ) -> list[dict]:
        """Retrieve with a server-side metadata filter.

        Managed knowledge bases use managedSearchConfiguration; the
        vectorSearchConfiguration used by customer-managed knowledge bases is
        rejected.
        """
        search_config: dict = {"numberOfResults": max(1, min(int(top_k), 20))}
        compiled = to_retrieval_filter(filter_dict)
        if compiled:
            search_config["filter"] = compiled

        response = self._runtime.retrieve(
            knowledgeBaseId=self._settings.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"managedSearchConfiguration": search_config},
        )

        results = []
        for item in response.get("retrievalResults", []):
            metadata = dict(item.get("metadata", {}))
            results.append(
                {
                    "id": str(metadata.get("doc_id") or metadata.get("_chunk_id", "")),
                    "score": float(item.get("score", 0.0)),
                    "content": item.get("content", {}).get("text", ""),
                    "memory_type": str(metadata.get("memory_type", "consolidated")),
                    "metadata": metadata,
                }
            )
        return results


class Module7Sink:
    """Module 7 memory contracts: Titan v2 embeddings plus MongoStore."""

    def __init__(self, mock: bool) -> None:
        self._mock = mock
        from module9.ingestion.embed import embed_chunk
        from module9.ingestion.load import get_mongo_store

        self._embed = embed_chunk
        self._store = get_mongo_store()

    def info(self) -> SinkInfo:
        return SinkInfo(
            backend=BACKEND_MOCK if self._mock else BACKEND_MODULE7,
            detail=(
                "in-process store, filter applied in memory"
                if self._mock
                else "MongoDB Atlas Vector Search, $vectorSearch pre-filter"
            ),
            embedding_model=EMBEDDING_TITAN,
            embeds_internally=False,
            display_name=(
                "in-process store (offline mock)"
                if self._mock
                else "MongoDB Atlas Vector Search"
            ),
        )

    def health_check(self) -> str:
        return self.info().detail

    def upsert_chunk(self, doc_id: str, content: str, metadata: dict) -> str:
        from module9.ingestion.load import MEMORY_TYPE

        embedding = self._embed(content)
        return self._store.upsert(doc_id, embedding, MEMORY_TYPE, content, metadata)

    def search(
        self, query: str, filter_dict: dict | None = None, top_k: int = 5
    ) -> list[dict]:
        embedding = self._embed(query)
        return self._store.vector_search(
            embedding,
            memory_type=None,
            filter_dict=filter_dict,
            top_k=max(1, min(int(top_k), 20)),
        )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def resolve_sink():
    """Return the active knowledge sink, degrading rather than failing.

    Order: a configured Bedrock managed knowledge base, then the Module 7
    memory contracts, then the in-process mock. A configured knowledge base
    that cannot be reached logs a warning and falls back, so a broken
    credential never takes the demo down.
    """
    settings = KnowledgeBaseSettings()
    if settings.configured:
        try:
            sink = BedrockManagedKBSink(settings)
            sink.health_check()
            return sink
        except Exception as exc:
            logger.warning(
                "Amazon Bedrock knowledge base %s unavailable (%s); falling back to "
                "the Module 7 memory path",
                settings.knowledge_base_id,
                exc,
            )
    return Module7Sink(mock=is_mock_memory())


def reset_sink() -> None:
    """Clear the cached sink so a later call re-resolves it."""
    resolve_sink.cache_clear()
