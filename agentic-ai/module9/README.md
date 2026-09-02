# Module 9: Data Pipelines and Lineage

Feeding agents accurate, fresh, and governed knowledge. A raw operational
event becomes provenance-tracked knowledge the DevOps Companion can safely
answer from, featuring two partners: **Confluent** (managed Kafka streaming)
and **Databricks** (Delta Lake + Unity Catalog lineage).

## The two-act narrative

- **Act 1, Confluent:** a production deployment event is produced to the
  Confluent Cloud Kafka topic `devops-events` and consumed live. This is the
  real-time stream consumption pattern and the managed-Kafka alternative to
  Amazon Kinesis.
- **Act 2, Databricks:** the consumer lands the event in Delta Lake (bronze,
  then silver), Unity Catalog captures the table-level lineage automatically,
  and the pipeline chunks, validates, embeds (Amazon Titan Text Embeddings
  v2, 1024-dim, via the Module 7 `EmbeddingService`), and loads into the
  Module 7 knowledge base: `MongoStore` semantic memory plus a `Neo4jStore`
  lineage graph. The agent answers a question about the deployment and traces
  its answer back to the exact Kafka offset and Delta table version.

Access control builds on the Module 8 identity primitives: a write-scoped
pipeline identity ingests, corpus-scoped agent roles retrieve, and the
role-compiled metadata filter runs inside the vector store as row-level
security.

## Quickstart (no cloud accounts, no credentials)

```bash
cd agentic-ai
python3.12 -m venv .venv
source .venv/bin/activate          # run everything from the virtualenv
pip install -r module9/requirements.txt

# the full guided demo, fully offline
python demos/module9_demo.py --mock

# equivalent when no .env is present (a fresh checkout resolves to mocks)
AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py

# jump to a single beat (for example the quality gates)
AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py --section 5

# non-interactive full loop
AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py --section 9 --no-pause

# run the tests (no credentials)
AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true pytest tests/test_module9_*.py -v
```

## The demo prepares itself

A full run calls `module9/demo_prep.py` before Section 1, so every run opens
identically with nothing to remember:

- **Health check** on each live partner.
- **Automatic degradation.** If Confluent or Databricks is unreachable, only
  that partner switches to its in-process mock, and the screen says so.
  Granular flags (`CONFLUENT_MOCK`, `DATABRICKS_MOCK`) mean one outage does
  not cost both.
- **Backlog skip.** Advances the ingestion consumer group to the end of the
  topic, so the demo consumes only what it produces rather than replaying
  rehearsal leftovers. No messages are deleted.
- **Lakehouse reset.** Truncates the demo bronze and silver tables so row
  counts reflect this run only.
- **Warm-up.** Wakes the SQL warehouse and the embedding endpoint so the
  first on-stage call is not cold.
- **Process state reset**, so running the demo twice in a session behaves
  like a fresh start.

Flags: `--no-prep` skips it entirely, `--no-reset` health checks and warms
without touching partner state, and `--fresh-topic` deletes and recreates
the Kafka topic so offsets restart at 0 (destructive and slower; use before
a final recording). A single-section run health checks and warms but does
not reset, so state you are inspecting is left alone.

`--redact-dates` shows calendar dates in displayed output as the placeholder
`YYYY-MM-DD`, for recording a session that streams later. Times of day are
kept, the stored records are unchanged, and a visible notice says so on
screen. Intended for recordings, not for hiding anything: the placeholder is
obviously a placeholder rather than a plausible substitute date.

The two mock flags layer:

| Flag | What it mocks |
| --- | --- |
| `AGENT_MOCK_PIPELINE=true` | Confluent (in-process topic) and Databricks (in-memory Delta tables + deterministic Unity Catalog lineage) |
| `AGENT_MOCK_MEMORY=true` | Module 7 backends: MongoDB Atlas, Neo4j Aura, and the Titan embedding call |
| `AGENT_MOCK_MODE=true` | Module 8 Auth0 identity (defaults to true) |
| `DATABRICKS_MOCK_LINEAGE=true` | Only the Unity Catalog lineage read. Delta Lake stays live. Narrow fallback for workspaces where the system tables are not readable. |

Set both pipeline and memory flags for a fully offline run. With only
`AGENT_MOCK_PIPELINE=true`, embedding and the knowledge base stay live.

## Demo sections

| Section | Beat |
| --- | --- |
| 1 | The stale agent problem: confident answer from outdated knowledge |
| 2 | Act 1: produce and consume the event with Confluent |
| 3 | Act 2: land in Delta Lake bronze/silver, Unity Catalog lineage |
| 4 | The lineage metadata schema (v5 Appendix B), every field populated |
| 5 | Data quality gates reject a bad batch before embedding |
| 6 | Freshness strategies and SLAs per corpus |
| 7 | Lineage: trace an answer back to offset and Delta version |
| 8 | Access control at ingestion and retrieval (Module 8) |
| 9 | Full loop: ingest to governed answer with provenance |

## What is real vs mocked

| Component | Real integration | Mock (`AGENT_MOCK_PIPELINE=true`) |
| --- | --- | --- |
| Event production | `confluent-kafka` `Producer.produce()` to Confluent Cloud, SASL_SSL | in-process ordered topic, same `produce()` surface |
| Stream consumption | `confluent-kafka` `Consumer.poll()` with consumer groups | same `poll()` surface, synthetic partition/offset |
| Delta landing | Databricks SQL connector to a serverless SQL warehouse | in-memory tables with monotonic Delta versions |
| Unity Catalog lineage | `system.access.table_lineage` | deterministic lineage records, same shape |
| Quality gates | same Python assertions + Databricks DLT expectations on the lakehouse | same Python assertions |
| Embedding | Bedrock `amazon.titan-embed-text-v2:0` via Module 7 `EmbeddingService` | deterministic pseudo-vector under `AGENT_MOCK_MEMORY` |
| Knowledge base | Module 7 `MongoStore` (Atlas Vector Search) + `Neo4jStore` (Aura) | Module 7 `MockMongo` / `MockNeo4j` under `AGENT_MOCK_MEMORY` |
| Identity | Module 8 Auth0 device-code flow | Module 8 `auth0_mock` under `AGENT_MOCK_MODE` |

## The knowledge sink

Where governed chunks land, and where the agent reads them back. One
interface in `module9/ingestion/kb_sink.py`, three backends resolved by
environment, so the module stands alone without a pile of partner accounts
to keep alive:

| Backend | Selected when | Notes |
| --- | --- | --- |
| Amazon Bedrock Managed Knowledge Base | `BEDROCK_KB_ID` and `BEDROCK_KB_DATA_SOURCE_ID` are set | Bedrock owns the vector store, indexing, embedding, and retrieval. Nothing to provision here. Row-level security is a server-side `managedSearchConfiguration` metadata filter. |
| Module 7 memory contracts | MongoDB Atlas credentials present | `MongoStore.upsert` plus `vector_search`, embedded with Titan v2 through the Module 7 `EmbeddingService`. Continuity path for Module 7 viewers. |
| In-process mock | nothing configured, or a configured backend is unreachable | The demo degrades rather than failing. |

The knowledge base is provisioned **outside this repo** and pointed at by
id. Module 9 never creates or deletes it. Measured behavior on a managed
knowledge base with service-managed embeddings: ingest to retrievable in
about 6 seconds, and metadata filters enforced server side.

Two constraints worth knowing, both discovered by testing rather than
documented prominently:

- A chunking strategy cannot be set alongside a managed embedding model, so
  the knowledge base applies its default chunking. Module 9 chunks are short
  enough to land whole, so one pipeline chunk stays one document.
- Inline metadata attributes accept STRING, NUMBER, and STRING_LIST.
  BOOLEAN is rejected at index time, so booleans are written as the strings
  `"true"` and `"false"`.

`IngestKnowledgeBaseDocuments` reports per-document outcomes in the response
body instead of raising, so the sink inspects `documentDetails` and raises on
`FAILED`. Without that, a rejected document looks like a successful load.

## Module 7 integration seams (no Module 7 files edited)

- **Write:** `MongoStore().upsert(doc_id, embedding, memory_type, content,
  metadata)` with `memory_type="consolidated"` and a `corpus` metadata field
  (no new memory type; Module 9 stays additive).
- **Read:** `MongoStore().vector_search(embedding, filter_dict=...)`; the
  filter is compiled from the caller's Module 8 role and applied as an Atlas
  `$vectorSearch` pre-filter, which is the row-level security enforcement
  point.
- **Lineage graph:** `Neo4jStore().create_relationship(...)` builds
  `Source -> Dataset -> Corpus -> Agent` with FEEDS / POPULATES / SERVES
  edges in the same graph as Module 7's relationship memory.
- **Embedding:** `module7.memory.embeddings.EmbeddingService`, unchanged.
- **Guardrail:** every chunk passes `anonymize_pii` / `anonymize_metadata`
  before embedding.

## Lineage metadata

Every chunk carries the full v5 Appendix B schema (`source_uri`,
`source_type`, `source_modified`, `ingested_at`, `pipeline_run_id`,
`content_hash`, `embedding_model`, `chunking_strategy`, `chunk_index`,
`chunk_count`, `parent_chunk_id`, `domain`, `access_level`,
`allowed_agent_roles`, `is_deprecated`, `deprecated_at`) plus the partner
provenance anchors (`kafka_topic`, `kafka_partition`, `kafka_offset`,
`delta_table`, `delta_version`, `unity_catalog_lineage_id`) and the access
extension (`agent_scope`, `owner_team`).

`get_provenance(doc_id)` joins this metadata with the lineage graph to
answer "why did the agent say this?" all the way back to the Kafka offset.

## Live setup

Follow `PARTNER_SETUP.md` for step-by-step provisioning with a credential
capture worksheet, then validate everything with one command:

```bash
python -m module9.live_check              # all partners
python -m module9.live_check --databricks-only
python -m module9.live_check --produce    # include a real Kafka round trip
```

`live_check` verifies credentials, creates the Delta tables the pipeline
needs, and reports whether Unity Catalog lineage is readable, with the exact
remediation for each failure. `MODULE9_TALK_TRACK.md` carries the on-stage
runbook and fallback ladder. In short:

1. **Confluent Cloud:** create a Basic cluster (same region as Bedrock),
   topic `devops-events`, and a cluster API key. Prefer subscribing through
   AWS Marketplace for the larger credit allotment. Set
   `CONFLUENT_BOOTSTRAP_SERVERS`, `CONFLUENT_API_KEY`,
   `CONFLUENT_API_SECRET` in `.env`.
2. **Databricks:** create catalog `devops` with schemas `bronze` and
   `silver`, a serverless SQL warehouse, and a personal access token. The
   pipeline creates the tables itself. Verify
   `system.access.table_lineage` is readable during provisioning: this is
   the highest technical risk to the live Act 2. Set `DATABRICKS_HOST`,
   `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`. Note that Free Edition is
   licensed for non-commercial use, so use a trial or paid workspace for
   any recorded or promotional demo; see `PARTNER_SETUP.md`.
3. **Knowledge sink:** point `BEDROCK_KB_ID` and
   `BEDROCK_KB_DATA_SOURCE_ID` at a managed knowledge base (recommended, no
   vector store to run), or reuse the Module 7 Atlas and Aura free tiers, or
   keep `AGENT_MOCK_MEMORY=true`.
4. **Corpora:** the demo seeds them during preparation and waits for them to
   be retrievable, so `python seed_module9_corpora.py` is only needed to
   warm live stores separately.
5. Install the live extras:
   `pip install -r module9/requirements-live.txt`, and run every command
   from the activated `.venv` so the partner packages are on the path.

Security notes:

- Credentials live in `.env` (gitignored), never in code.
- `module9/app.py` binds to 127.0.0.1 and has no authentication: it is a
  local demo server only. Production exposure goes through authenticated
  infrastructure (Module 10) with IAM auth on every endpoint.
- The pipeline identity is write-scoped and distinct from the agent read
  identities, mirroring how live IAM principals should be split.
- Tear down webinar resources when done: the Confluent cluster and topic,
  the Databricks workspace tables and token, and any test data in Atlas
  and Aura.

## What's scoped out

| Concern | Where it's covered |
| --- | --- |
| Exposing the agent to external callers (gateways, routing, rate limits) | Module 10 |
| AgentCore Gateway / AgentCore Identity for governed real-time access | Mention-only here (v5 Section 4.3); the access-control seams in `module9/identity.py` are where they plug in |
| Multimodal content ingestion (images, audio, video) | Out of scope for this two-partner text pipeline (v5 Section 2.5) |
| Pipeline observability platform (Astronomer), Matillion and Boomi connectors | v5 context only; not in the build |
| Production observability dashboards | Module 12 |

## File tree

```
module9/
  agent.py                  DevOps Companion via Module 5 DomainAdapter
  app.py                    local HTTP server, port 8089
  identity.py               Module 8 policies: pipeline vs agent identities
  live_check.py             preflight validation of the live partner setup
  PARTNER_SETUP.md          provisioning guide + credential worksheet
  config/
    settings.py             Confluent + Databricks env config
    models.py               re-exports Module 7 model factories
    corpora.py              the three corpora (service, policy, history)
    pipeline_domain.py      PipelineDomainConfig (extends Module 5)
  producers/
    devops_event_producer.py  Act 1 producer (real + mock)
  ingestion/
    stream_consumer.py      Confluent read seam
    delta_writer.py         Databricks Delta + Unity Catalog seam
    chunk.py                fixed / semantic / hierarchical chunking
    quality.py              gates: min-token, structural, dedup, embed-dim
    embed.py                wraps Module 7 EmbeddingService (Titan v2)
    load.py                 guardrail -> metadata -> embed -> MongoStore
    lineage.py              Neo4j graph + provenance queries
    freshness.py            per-corpus SLA verdicts
    pipeline_run.py         orchestrates the five stages
  tools/
    pipeline_tools.py       six @tool defs + governed recall factory
  prompts/
    system_prompts.py       four-layer governed-knowledge prompt
  mock/
    confluent_mock.py       in-process Kafka topic
    databricks_mock.py      in-memory Delta + Unity Catalog lineage
    sample_events.py        deterministic relative-dated events
    seed_corpora_data.py    tiny per-corpus seed docs
    module7_contract.py     vendored fallback for standalone checkouts
demos/module9_demo.py       9-section runner (--section, --mock, --no-pause)
tests/test_module9_*.py     60 tests, all pass offline
seed_module9_corpora.py     idempotent live seeder
```
