# Module 9 Talk Track: Data Pipelines and Lineage

Presenter script for the live webinar. The nine section budgets below total
22 minutes, plus a 2 minute recap, so plan on 22 to 25 minutes of demo
inside the session. If you need to recover time, Section 5 (quality gates)
and Section 6 (freshness) compress most easily to a minute each without
losing a beat; Sections 1, 2, 3, and 9 carry the narrative and should not be
rushed. Every beat has a builds-on-prior-modules callout
and a standalone path, so the demo lands for returning viewers and
newcomers alike.

Single-sentence takeaway to deliver at least twice:

> An agent is only as trustworthy as the pipeline behind it: stream the
> event with Confluent, govern it with Databricks, load it into the
> knowledge base with its lineage intact, and every answer the agent gives
> can be traced back to the exact source it came from.

## Before the webinar

Work the provisioning checklist 2 to 5 days out (credit windows are 30 to
60 days; do not provision months early):

1. **Confluent Cloud:** Basic cluster in the same region as Bedrock; topic
   `devops-events`; cluster API key/secret in `.env`. Prefer the AWS
   Marketplace subscription for the larger credit pool. Smoke test:
   `python -m module9.producers.devops_event_producer`.
2. **Databricks:** trial or paid workspace, not Free Edition, which is
   licensed for non-commercial use; catalog `devops`, schemas `bronze` and
   `silver`; serverless SQL warehouse; personal access token. Confirm
   `system.access.table_lineage` is readable. This is the single highest
   technical risk to Act 2: if the lineage system table is not available,
   set `DATABRICKS_MOCK_LINEAGE=true` (Delta stays live) and show a
   screenshot of the Unity Catalog lineage graph captured during rehearsal.
   Full steps and a credential worksheet are in `PARTNER_SETUP.md`.
3. **Knowledge sink:** point `BEDROCK_KB_ID` and
   `BEDROCK_KB_DATA_SOURCE_ID` at the managed knowledge base, or reuse the
   Module 7 Atlas and Aura tiers, or run with `AGENT_MOCK_MEMORY=true`. All
   three work; the demo reports which one is active during prep.
4. **Activate the virtualenv first.** Everything below assumes it:

   ```bash
   cd agentic-ai
   source .venv/bin/activate
   ```

   A plain `python` picks up whatever is first on your PATH, commonly a
   conda base environment, which will not have the partner packages.
   `python -m module9.live_check` prints the interpreter it is using on its
   first line, so check that line if anything looks oddly unavailable.

5. Run `python -m module9.live_check` until every line is green. The demo
   seeds the corpora itself, so `seed_module9_corpora.py` is only needed if
   you want to warm live stores separately.

   The demo prepares its own environment on every full run: it health checks
   both partners, degrades either one to mock if unreachable, skips the topic
   backlog, truncates the demo Delta tables, purges the previous run's
   knowledge base documents, seeds the corpora and waits for them to be
   retrievable, and warms the compute. For the final recording add
   `--fresh-topic` once so Act 1 opens at offset 0.

   **Recording a session that streams later:** add `--redact-dates`. Calendar
   dates in displayed output are shown as the placeholder `YYYY-MM-DD`, so
   nothing on screen pins the recording to a day. Times of day are kept and
   the stored records are untouched, and the demo prints a visible one-line
   notice saying exactly that, so the redaction is never mistaken for real
   data. The pipeline run id carries no date either. Relative language
   ("today", "1084 hours old") is genuinely relative to run time, so it stays
   true whenever the recording streams. Full command for the take:
   `python demos/module9_demo.py --fresh-topic --redact-dates`.

6. Full rehearsal the day before AND the morning of, using the same command
   you will use live: `python demos/module9_demo.py`. Do not add `--live`:
   it clears `AGENT_MOCK_MEMORY`, which `.env` sets deliberately so the
   lineage graph runs in process, and the run would then try to reach a
   MongoDB Atlas and Neo4j Aura you are not running.

Fallback rule: never debug a live service on stage. Most degradation is now
automatic, so in practice you keep talking:

- Confluent or Databricks unreachable: nothing to do. The prep step detects
  it, switches that one partner to its in-process equivalent, prints `MOCK`
  next to it, and leaves the other partner live.
- Knowledge base, Atlas, or Neo4j unreachable: nothing to do either. The
  sink falls back and prep says which backend is active.
- Unity Catalog lineage read fails or shows `pending`: `DATABRICKS_MOCK_LINEAGE=true`
  keeps Delta Lake live and synthesizes only the lineage record. Or show the
  Catalog Explorer tab, which is near real time.
- Databricks warehouse cold: it is warmed during prep, but if a query stalls,
  the fallback above applies.
- Total network loss: `python demos/module9_demo.py --mock`, which also
  ignores a configured knowledge base, and is the identical newcomer path.
  With no `.env` present, the env-var form does the same thing:
  `AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py`.

## How to drive the demo live

Start it once with `python demos/module9_demo.py` and press Enter to advance
each beat. You do not run a command per section. The `Run: --section N`
lines below are for rehearsing or re-recording a single beat in isolation;
a single-section run health checks and warms but does not reset partner
state, so it will not disturb whatever you are inspecting.

## Section 1: The Stale Agent Problem (2 min)

Run: `python demos/module9_demo.py` (no flags: it prepares the environment
itself, then walks all nine sections)

The run opens with a short preparation readout. If anyone asks, it health
checks both partners, clears the previous run's state, seeds the corpora,
and warms the compute. If a partner were unreachable it would say so and
switch that layer to an in-process equivalent.

SAY: "Here is the DevOps Companion you have watched us build since Module
1. In Module 7 we gave it memory. Today I am going to show you why memory
is not enough. checkout-api shipped a release to production this
afternoon, and this version of the agent has no idea. Watch what it says."

**Important for this beat:** the agent on screen is deliberately the
*pre-Module 9* agent. It can retrieve, but it has no freshness signal and
no provenance, which is exactly why it does not hedge. Section 9 runs the
governed agent for the contrast.

The agent confidently describes the previous release, v1.18.2. Point at the
freshness check that follows: the newest chunk in the history corpus is
over a thousand hours old against a 26-hour SLA.

SAY: "Notice what did NOT happen. Retrieval did not fail. Scores looked
healthy. The agent is not hallucinating; it is faithfully reporting stale
knowledge. This failure mode is quiet, and that is what makes it
dangerous. Data quality has to be engineered in, not tested out."

Standalone callout: "If today is your first session: everything you will
see runs on your laptop with one flag, `--mock`, and zero accounts."

## Section 2: Act 1, Confluent (3 min)

Run: `--section 2`. If live, have the Confluent Cloud topic UI open in a
browser tab and show the message arriving.

SAY: "Act 1: get the event moving the moment it happens. We produce the
deployment record to a Kafka topic on Confluent Cloud. The module teaches
this as the real-time stream consumption pattern, with Amazon Kinesis as
the AWS-native default. Confluent is the managed Kafka alternative, and
the choice is worth making deliberately: Kinesis for the least operational
overhead on an AWS-centric stack, Confluent when you already run Kafka,
need independent replaying consumers, or want Schema Registry enforcing
event contracts so a malformed producer using the registry cannot publish
events that break the agreed contract."

Accuracy guardrail if challenged: Schema Registry enforces the contract at
the serialization layer, so a producer that bypasses the serializer can
still write arbitrary bytes. Confluent Cloud offers broker-side schema
validation as a topic setting on the higher cluster tiers if you need
server-side enforcement. Do not claim the registry alone makes malformed
events impossible.

Point at the delivery report: "Topic, partition 0, offset. Remember that
offset number. It is about to follow this event through the entire
pipeline, all the way into the agent's answer."

Point at the viewer consumer group: "A second consumer group read the same
event without disturbing the pipeline's position. That is core to the Kafka
consumer model: every reader keeps its own offsets and can replay from any
point."

Accuracy guardrail: do not imply Kinesis cannot do independent consumers. It
can, through multiple KCL applications with their own checkpoints and through
enhanced fan-out. The honest distinction is the mechanism, Kafka's
consumer-group offsets versus Kinesis shard iterators and fan-out, not
whether independent readers are possible.

## Section 3: Act 2, Delta Lake and Unity Catalog (3 min)

Run: `--section 3`. If live, open the Unity Catalog lineage graph for
`devops.silver.deployment_events` after the write.

SAY: "Act 2 belongs to Databricks. The consumer lands the raw event
exactly as it arrived in a bronze Delta table, then writes the normalized
row to silver. Two things happened that nobody had to build. First, every
Delta write incremented a table version; that version is our second
provenance anchor. Second, Unity Catalog watched the data move from bronze
to silver and recorded the lineage edge automatically. Your knowledge
base's source tables now sit under the same governance model as the rest
of your data estate."

**Branch on what the screen shows.** The lineage system tables are
populated in batch, so one of two things appears:

- A lineage record with a source table, a target table, and an event time.
  Say: "there it is, captured automatically."
- `status: pending` with the source table, target table, and Delta version
  the pipeline just wrote. Say: "the lineage system table is batch
  populated, so this edge is not queryable yet. Catalog Explorer shows the
  graph in near real time," then switch to the browser tab. Running the
  pipeline the day before makes the queryable case far more likely.

Builds-on callout: "Module 7 viewers: the pipeline writes through the same
memory contracts you saw last session. Today the knowledge base behind them
is an Amazon Bedrock managed knowledge base, so there is no vector database
to run: Bedrock owns the store, the indexing, and the retrieval, and our
pipeline owns everything upstream of it. Swap that final knowledge base
sink for MongoDB Atlas and not a line of pipeline code changes. To be
clear, everything you just watched in Databricks stays exactly the same:
it is the knowledge base behind the pipeline that is pluggable, not the
lakehouse in front of it."

## Section 4: The Lineage Metadata Schema (2 min)

Run: `--section 4`

SAY: "Here is the chunk the pipeline hands to the knowledge base, rendered
from the structured record into natural language, one record per chunk,
which is the chunking guidance for structured records. And here is
everything that rides with it." Scroll the metadata dict slowly.

SAY: "Source URI down to the Kafka offset. Pipeline run id for debugging.
Content hash for dedup and incremental refresh. Chunking strategy,
embedding model, and the access stamps: access_level, allowed_agent_roles,
agent_scope. This dict is the difference between a searchable text blob
and governed knowledge. Every field here comes straight from the module's
lineage schema reference."

If anyone asks why `embedding_model` names a service-managed model rather
than Titan: the managed knowledge base owns embedding, so the metadata
records what actually happened rather than claiming a call the pipeline did
not make. Point out that this is the honest-provenance principle applied to
our own pipeline. On the Module 7 path the same field reads
`amazon.titan-embed-text-v2:0`.

## Section 5: Data Quality Gates (3 min)

Run: `--section 5`

SAY: "Now we try to poison the well. A malformed event arrives: service
name of one character, empty fields. The gates reject it before embedding:
below the 50-token minimum, no structure worth keeping. No tokens spent,
no noise in retrieval. Then the second case: the same good record arrives
twice. The content hash matches, so the pipeline skips it. That is not
just dedup; it is the incremental refresh mechanism. Unchanged content is
never re-embedded, which is what keeps a weekly full extract affordable."

Mention-only: "On the live path, Databricks Delta Live Tables expectations
enforce schema and null checks at the lakehouse layer too, and the module
covers Astronomer for pipeline observability."

## Section 6: Freshness Strategies (2 min)

Run: `--section 6`

SAY: "Three corpora, three refresh strategies, on purpose. Service docs
change on a weekly cadence: scheduled full refresh with hash-based skip.
Policy runbooks change after incidents: event-driven, under ten minutes of
lag. History is generated by the system itself: streaming plus a nightly
consolidation sync. The dashboard turns 'probably current' into a measured
property with an SLA and an alarm. The Section 1 failure gets caught here,
before a user ever sees a stale answer."

## Section 7: Lineage, Why Did the Agent Say This? (2 min)

Run: `--section 7`

SAY: "Compliance asks: which source produced this answer? Two lineage
layers answer it. Unity Catalog holds the table-level story in the
lakehouse. And the pipeline wrote a chunk-level graph through the Module 7
graph contract: Source FEEDS Dataset POPULATES Corpus SERVES Agent. Join
that with the chunk metadata and you get the full chain: answer, chunk,
corpus, Delta version, Kafka offset. On an AWS-native stack the same query
is SQL over Glue Data Catalog and Athena."

Accuracy note: in this run the graph store is in-process, because we are
not running Neo4j Aura today. Say "the same graph contract you saw in
Module 7, backed by Aura in production" rather than implying Aura is live.
The three edges on screen are real, written by the pipeline through that
contract.

## Section 8: Access Control (2 min)

Run: `--section 8`

SAY: "Module 8 viewers, this is your session applied to data. Two
identities: the pipeline writes under a write-scoped principal that cannot
retrieve anything, and each agent role reads under a scoped policy. Watch
the PII guardrail first: an on-call engineer's email arrived inside the
alarm text, and it is redacted before embedding, so raw PII never lands in
long-term storage."

SAY: "Now two roles ask for the history corpus. Deploy+Observe is
authorized: the policy check passes and its filter compiles to corpus
history, agent_scope operations. Repository Analysis is denied twice
over: the Module 8 policy check raises before any query runs, and even a
crafted query would compile a filter that the knowledge base applies server
side, so operations-scoped chunks never come back. Row-level security is
not an honor system; the model cannot talk its way past a filter it never
controls."

Mention-only: "AgentCore Identity is the AWS-native home for this pattern
as you productionize."

## Section 9: The Full Loop (3 min)

Run: `--section 9`

SAY: "A new release ships while we are talking: checkout-api v2.4.1. The
whole pipeline runs end to end: produce, consume, bronze, silver, chunk,
gates, embed, load. Then we ask the same question from Section 1." The
agent answers with v2.4.1 and usually volunteers the Kafka offset and Delta
version in its own words.

Point at the pipeline summary: consumed 1, stored 1, rejected 0, skipped 0.
That is one new fact, accepted once.

SAY: "And here is the part that makes this production-grade rather than a
demo trick: provenance. The answer traces to the history corpus, to the
silver Delta table at a specific version, to the Kafka topic at a specific
offset. Check the numbers the agent just quoted against the provenance
panel: they match. From answer back to origin, every hop recorded."

Close with the takeaway sentence, then: "Module 10 is the other side of
this boundary: the requests flowing INTO your agent, gateways, routing,
and rate limiting. See you there."

## Recap slide bullets

- Five data access patterns; today was knowledge base ingestion plus
  real-time streams.
- Confluent: managed Kafka, consumer groups, replay, schema governance.
- Databricks: Delta versions, automatic Unity Catalog lineage, quality
  expectations.
- Every chunk carries the full lineage schema plus offset and version
  anchors.
- Freshness is an SLA, quality is a gate, access is an identity-compiled
  filter.
- The knowledge base is swappable: a Bedrock managed knowledge base with no
  vector store to run, MongoDB Atlas, or an in-process store, with no
  change to the pipeline above it.
- Everything you saw runs offline: `--mock`, zero accounts.
