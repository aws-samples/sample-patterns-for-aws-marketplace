# Module 9 Partner Environment Setup and Capture Worksheet

Provisioning guide for the two live partner environments: Confluent Cloud (Act 1,
streaming) and Databricks (Act 2, Delta Lake plus Unity Catalog lineage).

Work top to bottom. Every value you need to capture is marked **CAPTURE** and has a
matching line in the worksheet at the end. When you finish, paste the worksheet into
`agentic-ai/.env` and run the preflight check:

```bash
python -m module9.live_check
```

That command validates every credential, creates the Delta tables, and tells you
exactly which piece is missing or misconfigured. Do not wait until webinar day to
run it.

Mock mode needs none of this. `AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true`
runs the whole demo offline and is the viewer path for anyone who does not want
partner accounts.

---

## Read first: edition and licensing

**Databricks Free Edition is licensed for non-commercial use only.** The Free
Edition terms limit use to internal, personal, academic, or not-for-profit
purposes, and state that Free Edition accounts may not be used for commercial
purposes. A recorded AWS Marketplace webinar promoting partner solutions to
thousands of customers is not a defensible fit for that license, even though the
technical capability is there.

Recommendation, changed from the original design blueprint:

| Purpose | Use |
| --- | --- |
| The live demo recording and any webinar dry run | Databricks **14-day free trial**, or a Databricks workspace your org already pays for, or a Marketplace subscription. The trial is explicitly positioned for business evaluation. |
| The viewer path documented in the README | **Free Edition** is fine to recommend to learners following along for their own education, and so is mock mode. |

Practical consequence: the trial clock is 14 days. Do not start it until you have
a recording date. Tell me the date and I will work backward with you on a
provisioning schedule.

Confluent Cloud's free trial has no equivalent non-commercial restriction. Its
cloud terms allow use for your own business operations. The constraint there is
the credit window, roughly 30 to 60 days, so it also wants to be provisioned
close to the recording date, not weeks early.

---

## Prerequisites

```bash
cd /Users/worsnt/Downloads/Projects/module-9-aws-mp/sample-patterns-for-aws-marketplace/agentic-ai
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r module9/requirements.txt -r module9/requirements-live.txt
```

**Always run from the activated virtualenv.** A plain `python` picks up
whatever interpreter is first on your PATH, commonly a conda base
environment, which will not have the live partner packages. Every command in
this guide assumes `.venv` is active. `python -m module9.live_check` prints
the interpreter it is running on as its first line, and when a live package
is missing it names that interpreter and points back at `.venv` instead of
telling you to install something you already installed elsewhere.

Module 8's `secret_probe_server` imports `mcp.server.fastmcp`, which was
removed in `mcp` 2.x, and `module8/requirements.txt` does not pin `mcp` (it
arrives transitively through `agent-guard-core`). If two Module 8 identity
tests fail on a freshly built environment, pin the older line:

```bash
pip install "mcp<2.0"
```

Notes:

- `confluent-kafka` ships prebuilt wheels for macOS, so no `brew install
  librdkafka` is needed unless pip falls back to a source build.
- **macOS certificate trust.** The python.org framework builds ship without a
  populated CA trust store, which makes the Databricks SQL connector fail
  verification against a perfectly valid certificate chain, and its internal
  retries turn that into a multi-minute hang rather than a clear error. Module 9
  handles this automatically by pointing OpenSSL at certifi's bundle before the
  first connection, reusing the Module 7 helper. Just make sure `certifi` is
  installed in your virtualenv, which `module9/requirements.txt` guarantees.
  `python -m module9.live_check` prints the CA bundle in effect on the first
  line, and bounds the Databricks checks with a watchdog so a hang fails fast
  with a diagnosis instead of stalling.
- Create `agentic-ai/.env` if it does not exist. It is already gitignored.
  Never commit credentials.
- AWS credentials for Bedrock (Titan embeddings) must be on the machine, or run
  with `AGENT_MOCK_MEMORY=true` which also mocks embeddings.

---

## Partner 1: Confluent Cloud (Act 1, real-time streaming)

**When:** 2 to 5 days before the recording. Credits expire.

**Signup path:** subscribing through AWS Marketplace carries a larger credit
allotment than a direct signup. Confirm the current credit amounts on the listing
at signup time rather than trusting a number written here, since promotional
terms change.

- AWS Marketplace listing: https://aws.amazon.com/marketplace/pp/prodview-g5ujul6iovvcy
- Direct: https://confluent.cloud/signup

### Steps

1. **Create the account.** No credit card is required for the trial. If you use
   the Marketplace path, complete the subscription first so the credits land on
   the right organization.
   - **CAPTURE:** which signup path you used, and the credit expiry date shown in
     the billing page. Put a calendar reminder 3 days before it lapses.

2. **Create a Basic cluster.**
   - Cloud provider: **AWS**
   - Region: the same region you run Bedrock in, normally `us-east-1`. Matching
     regions keeps the live latency low enough that the stream beat feels instant.
   - Availability: Single zone is fine for a demo.
   - Name: `module9-demo`
   - **CAPTURE:** cluster name and region.

3. **Create the topic.**
   - Left nav: **Topics**, then **Create topic**.
   - Name: `devops-events` exactly. The code defaults to this name, and the demo
     narration references it.
   - Partitions: `1`. One partition guarantees strict ordering, which makes the
     offset story in Act 1 cleaner to narrate. Use 3 only if you want to talk
     about parallelism.
   - **Create with defaults**.

4. **Create a cluster API key.**
   - Left nav: **API keys**, then **Add key** (older console: **Data
     integration > API keys**).
   - Choose a key scoped to the cluster. Global access is acceptable for a
     throwaway demo cluster; narrate it as demo-only if it comes up, since
     production would scope to the topic.
   - The **secret is displayed once.** Copy both values immediately.
   - **CAPTURE:** `CONFLUENT_API_KEY`, `CONFLUENT_API_SECRET`.

5. **Get the bootstrap endpoint.**
   - **Cluster settings > Endpoints** (or the cluster overview page).
   - Format: `pkc-xxxxx.<region>.aws.confluent.cloud:9092`
   - **CAPTURE:** `CONFLUENT_BOOTSTRAP_SERVERS`.

### Verify Confluent alone

```bash
# preflight: checks auth and confirms the devops-events topic exists
python -m module9.live_check --confluent-only

# then the actual Act 1 beat against the real cluster
AGENT_MOCK_MEMORY=true python demos/module9_demo.py --section 2 --no-pause
```

You should see the event produced to a real partition and offset, then consumed
back within a second or two. Leave the cluster running once verified; a cold
cluster is not a thing you want to discover on stage.

---

## Partner 2: Databricks (Act 2, Delta Lake and Unity Catalog lineage)

**When:** within the 14-day trial window ending after your recording date.

**This is the highest technical risk in the whole demo.** The Act 2 governance
beat reads Unity Catalog's automatic table lineage. Verify it during setup, per
step 6, not on the day.

**Signup:** https://www.databricks.com/try-databricks (choose the trial, not Free
Edition, per the licensing note above). Signing up with your existing AWS account
through Marketplace gives you a serverless workspace immediately.

### Steps

1. **Create the workspace.** The express or serverless path is fine and fastest.
   - **CAPTURE:** workspace URL. On AWS it looks like
     `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`. That is your
     `DATABRICKS_HOST`. Include the `https://` prefix; the code strips it when
     needed.
   - Note: `*.azuredatabricks.net` is the Azure form. If you see that, you are in
     Azure Databricks, which also works but is not the AWS story this series
     tells.

2. **Confirm Unity Catalog is on.** Workspaces created after November 2023 are
   Unity Catalog enabled by default, and the trial workspace will be. In
   **Catalog** you should see a three-level namespace and a `system` catalog
   listed.
   - **CAPTURE:** whether a `system` catalog is visible at all. If it is missing
     entirely, jump to step 6's fallback.

3. **Create the catalog and schemas.**
   - **Catalog > Create catalog**, name `devops`, default storage.
   - Inside `devops`, **Create schema** `bronze`, then **Create schema** `silver`.
   - Do not create tables by hand. The pipeline creates them with the exact
     schema it needs, including the column that makes lineage work. Running
     `python -m module9.live_check` creates them for you.

4. **Create a serverless SQL warehouse.**
   - **SQL Warehouses > Create SQL warehouse**
   - Type: **Serverless**. It starts in seconds, which matters live.
   - Size: **2X-Small** is plenty for demo volume.
   - Auto stop: raise it to 30 or 60 minutes on recording day so it cannot idle
     out mid-demo.
   - Open the warehouse, go to **Connection details**, copy the **HTTP path**
     (`/sql/1.0/warehouses/xxxxxxxxxxxx`).
   - **CAPTURE:** `DATABRICKS_HTTP_PATH`, warehouse name, auto-stop setting.

5. **Create a personal access token.**
   - Top-right avatar > **Settings > Developer > Access tokens > Generate new
     token**.
   - Comment: `module9-demo`. Lifetime: long enough to cover rehearsals plus the
     recording, and no longer.
   - **Displayed once.** Copy it now.
   - **CAPTURE:** `DATABRICKS_TOKEN` (starts with `dapi`).

6. **Verify Unity Catalog lineage access. Do this now.**

   ```bash
   python -m module9.live_check --databricks-only
   ```

   That runs four checks in order: warehouse connectivity, catalog and schema
   existence, table creation, and a read against
   `system.access.table_lineage`. Interpreting the lineage result:

   - **Returns rows, or returns zero rows without error:** you are good. Zero
     rows just means no lineage has been generated in this workspace yet; the
     pipeline will generate it.
   - **Permission denied on `system.access`:** the `access` schema needs
     enabling and granting. On a trial workspace you are typically the account
     admin, so you can do it yourself: open a SQL editor and run
     `GRANT USE SCHEMA, SELECT ON SCHEMA system.access TO \`your-email\`;`
     If that fails because the schema is not enabled, enable it from the account
     console (**accounts.cloud.databricks.com > Catalog > system schemas**) or
     via the Unity Catalog system schemas API, then re-grant. Only an account
     admin or metastore admin can enable a system schema.
   - **Table or schema not found:** system tables are not enabled on this
     metastore. Enable the `access` schema as above.
   - **Still blocked after all that:** use the lineage fallback below. Do not
     burn recording day on it.

   **Lineage fallback.** Set `DATABRICKS_MOCK_LINEAGE=true` in `.env`. The Delta
   tables, versions, and every other Databricks interaction stay fully live; only
   the lineage record read is served from a deterministic local stand-in. Pair it
   with a screenshot or short screen recording of the real Unity Catalog lineage
   graph captured during a rehearsal, so the governance beat still shows the real
   product. Narrate honestly if asked.
   - **CAPTURE:** whether lineage read worked, or that you are using the
     fallback.

   **Lineage latency, important for the recording.** A readable
   `system.access.table_lineage` does not mean a freshly written edge is
   queryable. The lineage system tables are populated in batch and Databricks
   publishes no latency guarantee. On this account the table was readable and
   returned zero rows for more than ten minutes after a successful
   bronze-to-silver write. Plan accordingly:

   - **Catalog Explorer is the near-real-time view** and the better on-screen
     artifact anyway. Open **Catalog > devops > silver > deployment_events >
     Lineage** to see the graph.
   - **Pre-warm the lineage.** Run the pipeline several hours, ideally a day,
     before recording. Historical edges will then be present in the system
     table when you query it live.
   - The pipeline reports this state honestly. When the system table has no
     edge yet, chunks are stamped
     `unity_catalog_lineage_status: pending` and the demo prints the source
     table, target table, and Delta version it just wrote, rather than a blank
     or invented lineage id.
   - The near-real-time lineage REST endpoint
     (`POST /api/2.0/lineage-tracking/table-lineage`) returned
     `ENDPOINT_NOT_FOUND` on this workspace, so do not plan the beat around it
     without verifying it on yours first.

7. **Capture the lineage graph for the slide deck.** Regardless of whether the
   system table read works, after your first successful pipeline run open
   **Catalog > devops > silver > deployment_events > Lineage** and screenshot the
   bronze-to-silver graph. That visual is the strongest artifact in Act 2 and you
   want it saved rather than generated live.

### Verify Databricks alone

```bash
AGENT_MOCK_MEMORY=true python demos/module9_demo.py --section 3 --no-pause
```

Expect: bronze insert, silver insert derived from bronze, both Delta versions
incrementing, and a Unity Catalog lineage record printed.

---

## Knowledge sink: Amazon Bedrock Managed Knowledge Base

The knowledge base lives outside this repo. Module 9 only points at it by id
and never creates or deletes it. If the ids are unset, the pipeline falls
back to the Module 7 memory path, and to the in-process mock, so the module
always runs.

Managed knowledge bases need no vector database: Bedrock owns the store,
indexing, embedding, and retrieval.

### Create it once, in the console

1. Open **Amazon Bedrock AgentCore > Built-in tools > Knowledge Base** and
   choose **Create Managed Knowledge Base**.
2. Name it, for example `module9_devops_companion`.
3. Embedding model type: **Managed**. There is nothing to configure and no
   model access to request.
4. IAM permissions: **Create and use a new service role**.
5. Data source: name it, for example `module9-pipeline-chunks`, and select
   type **Custom**. A custom data source needs no bucket and no sync: the
   pipeline pushes chunks straight in.
6. Leave content parsing and chunking at their defaults. A chunking strategy
   cannot be combined with a managed embedding model, and Module 9 chunks are
   short enough that each one stays a single document.
7. Create, and wait for the knowledge base and data source to become
   available. Creation took about 80 seconds on this account.
8. Copy the knowledge base id and the data source id.

- **CAPTURE:** `BEDROCK_KB_ID`, `BEDROCK_KB_DATA_SOURCE_ID`, and the region.

### Verify

```bash
python -m module9.live_check --memory-only
```

Expect the knowledge base to report `MANAGED, ACTIVE` and the active sink to
report `bedrock-managed-kb`. If the ids are wrong or the knowledge base is
gone, the check fails clearly and the demo still runs on the fallback.

### Teardown

Delete the knowledge base, its data source, and the service role from the
console when you are finished with the series. Storage and retrieval are
billed while it exists.

## Module 7 backends (optional for the recording)

The pipeline writes through the Module 7 `MongoStore` and `Neo4jStore`. You have
two defensible choices for the recording:

- **Live Atlas plus Aura** (reuse the Module 7 free tiers). Strongest story,
  since the knowledge base is genuinely the same one from last session.
- **`AGENT_MOCK_MEMORY=true`.** Keeps live complexity to the two featured
  partners. Nothing on screen changes except that the stores are in-process.

If you go live, note the env var names, which differ from the earlier draft:

```
MONGODB_URI=mongodb+srv://...
MONGODB_DATABASE=agent_memory
MONGODB_COLLECTION=memories
MONGODB_VECTOR_INDEX=vector_index
NEO4J_URI=neo4j+s://...
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
```

The variable is `MONGODB_URI`, not `MONGO_URI`. Module 7's store reads
`MONGODB_URI` and will silently fall back to failing on connect if you set the
shorter name. Atlas also needs the `vector_index` Vector Search index defined per
the Module 7 README, and your current IP allowed in Atlas Network Access.

---

## Capture worksheet

Fill this in as you go, then paste into `agentic-ai/.env`.

```
# ---- Module 9 live mode ----
# Leave AGENT_MOCK_PIPELINE unset or false for live partners.
# AGENT_MOCK_PIPELINE=true
# Set only if Unity Catalog system-table lineage is blocked:
# DATABRICKS_MOCK_LINEAGE=true

# ---- Confluent Cloud (Act 1) ----
CONFLUENT_BOOTSTRAP_SERVERS=
CONFLUENT_API_KEY=
CONFLUENT_API_SECRET=
# CONFLUENT_TOPIC=devops-events        # default, only set if you renamed it
# CONFLUENT_GROUP_ID=module9-ingestion # default, leave alone

# ---- Databricks (Act 2) ----
DATABRICKS_HOST=
DATABRICKS_TOKEN=
DATABRICKS_HTTP_PATH=
# DATABRICKS_CATALOG=devops
# DATABRICKS_BRONZE_SCHEMA=bronze
# DATABRICKS_SILVER_SCHEMA=silver
# DATABRICKS_BRONZE_TABLE=raw_events
# DATABRICKS_SILVER_TABLE=deployment_events

# ---- Module 7 knowledge base (optional; else AGENT_MOCK_MEMORY=true) ----
# MONGODB_URI=
# MONGODB_DATABASE=agent_memory
# MONGODB_COLLECTION=memories
# MONGODB_VECTOR_INDEX=vector_index
# NEO4J_URI=
# NEO4J_USERNAME=neo4j
# NEO4J_PASSWORD=

# ---- AWS (Bedrock Titan embeddings) ----
AWS_REGION=us-east-1
# AWS_PROFILE=
```

Also record these for the runbook, not for `.env`:

| Item | Value |
| --- | --- |
| Recording date | |
| Confluent signup path (Marketplace or direct) | |
| Confluent credit expiry date | |
| Confluent cluster name and region | |
| Databricks edition (trial, paid, Free) | |
| Databricks trial expiry date | |
| SQL warehouse name and auto-stop minutes | |
| PAT expiry date | |
| Unity Catalog lineage: working or fallback | |
| Lineage screenshot saved at | |

---

## Full end-to-end live verification

Run the day before, and again the morning of.

```bash
python -m module9.live_check                     # all preflight checks green
python seed_module9_corpora.py                   # warm the three corpora
AGENT_MOCK_MEMORY=true python demos/module9_demo.py --no-pause   # or fully live
```

Sections to watch closely:

- **Section 3:** the silver write must derive from bronze, and a lineage record
  must print. This is the beat that fails silently if the tables were created by
  hand with the wrong schema.
- **Section 7:** the provenance chain must resolve to a real Kafka offset and a
  real Delta version.
- **Section 9:** the agent answers from the freshly streamed fact.

Warm-ups on recording day, in this order, 10 to 15 minutes before going live:
start the SQL warehouse and run one query, make one Bedrock call, produce one
throwaway event to Confluent, then run the full demo once end to end.

---

## Fallback ladder for recording day

Never debug a live service while recording. Drop one rung and keep moving.

| What fails | Drop to |
| --- | --- |
| Unity Catalog system-table lineage errors | `DATABRICKS_MOCK_LINEAGE=true`; Delta stays live, show the saved lineage screenshot |
| Databricks warehouse cold or token expired | `AGENT_MOCK_PIPELINE=true`; narrate the same API surface running in process |
| Confluent unreachable or topic empty | `AGENT_MOCK_PIPELINE=true` |
| Atlas or Aura unreachable | add `AGENT_MOCK_MEMORY=true` |
| Everything, or no network | `AGENT_MOCK_PIPELINE=true AGENT_MOCK_MEMORY=true python demos/module9_demo.py` |

---

## Teardown

Do this immediately after the recording and any dry run you do not need again.

**Confluent:** delete the API key, then delete the cluster (removes the topic).
If you subscribed through Marketplace, cancel the subscription so it cannot
renew.

**Databricks:** revoke the PAT under Settings > Developer, delete the SQL
warehouse, drop the `devops` catalog (`DROP CATALOG devops CASCADE`), and let the
trial lapse or cancel it explicitly.

**Module 7 backends:** if you created new Atlas or Aura resources for this
module, delete the test database and graph data. Free tiers idle harmlessly if
you are continuing the series.

**AWS:** nothing in Module 9 provisions AWS resources. The only AWS usage is
Bedrock model invocation, which is per-call with nothing to tear down.
