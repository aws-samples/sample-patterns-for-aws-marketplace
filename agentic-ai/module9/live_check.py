# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/live_check.py
======================
Preflight validation for the Module 9 live partner environments.

Verifies Confluent Cloud and Databricks credentials, creates the Delta
tables the pipeline needs, and reports whether Unity Catalog lineage is
readable. Run this during provisioning and again the morning of the
recording. Never wait for the demo to discover a broken credential.

Usage:
    python -m module9.live_check                 # everything configured
    python -m module9.live_check --confluent-only
    python -m module9.live_check --databricks-only
    python -m module9.live_check --produce       # also do a Kafka round trip

Exit code is 0 when every check passes, 1 otherwise. Secrets are masked in
all output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

from module9.config.settings import (
    ConfluentSettings,
    DatabricksSettings,
    is_mock_lineage,
    is_mock_memory,
    is_mock_pipeline,
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    warning: bool = False


def _missing_package_hint() -> str:
    """Explain a missing live dependency in terms of the interpreter in use.

    The usual cause is not a missing install but the wrong Python: a conda
    base environment or the system interpreter instead of the project
    virtualenv. Naming the running interpreter makes that obvious.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(root, ".venv", "bin", "python")
    running_in_venv = os.path.abspath(sys.prefix) == os.path.join(root, ".venv")

    hint = (
        f"live extras are not installed for this interpreter "
        f"({sys.executable}). Install them with:\n"
        "         pip install -r module9/requirements.txt "
        "-r module9/requirements-live.txt"
    )
    if not running_in_venv and os.path.exists(venv_python):
        hint += (
            "\n         Or use the project virtualenv, which already has them:\n"
            "         source .venv/bin/activate && python -m module9.live_check"
        )
    return hint


def _mask(secret: str) -> str:
    """Show only enough of a credential to confirm which one is loaded."""
    if not secret:
        return "(not set)"
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-2:]} ({len(secret)} chars)"


def _run_with_timeout(fn, seconds: int, label: str) -> list[CheckResult]:
    """Run a check group under a watchdog.

    A misconfigured warehouse or a TLS failure inside a driver that retries
    internally can hang for many minutes. A preflight tool must fail fast
    and say what to look at instead.
    """
    import threading

    box: dict = {}

    def runner() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:  # surface driver errors as a failed check
            box["result"] = [CheckResult(label, False, str(exc))]

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        return [
            CheckResult(
                label,
                False,
                f"timed out after {seconds}s. Common causes: the SQL warehouse "
                "is stopped or still starting, the HTTP path points at a "
                "deleted warehouse, or TLS verification is failing inside the "
                "driver. Check the warehouse state in the Databricks console.",
            )
        ]
    return box.get("result", [CheckResult(label, False, "no result returned")])


def _load_dotenv() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k not in os.environ:
                    os.environ[k] = v


# ---------------------------------------------------------------------------
# Confluent
# ---------------------------------------------------------------------------

def check_confluent(produce_roundtrip: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []
    settings = ConfluentSettings()

    try:
        settings.validate_for_live()
        results.append(
            CheckResult(
                "Confluent configuration",
                True,
                f"bootstrap={settings.bootstrap_servers} "
                f"topic={settings.topic} key={_mask(settings.api_key)}",
            )
        )
    except ValueError as exc:
        results.append(CheckResult("Confluent configuration", False, str(exc)))
        return results

    try:
        from confluent_kafka.admin import AdminClient  # type: ignore[import]
    except ImportError:
        results.append(
            CheckResult("confluent-kafka installed", False, _missing_package_hint())
        )
        return results

    try:
        admin = AdminClient(settings.client_config())
        started = time.monotonic()
        metadata = admin.list_topics(timeout=15)
        elapsed = round(time.monotonic() - started, 2)
        broker_count = len(metadata.brokers)
        results.append(
            CheckResult(
                "Confluent authentication",
                True,
                f"{broker_count} broker(s) reachable in {elapsed}s",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult(
                "Confluent authentication",
                False,
                f"{exc}; check CONFLUENT_API_KEY, CONFLUENT_API_SECRET, "
                "and that the cluster is running",
            )
        )
        return results

    if settings.topic in metadata.topics:
        topic_meta = metadata.topics[settings.topic]
        results.append(
            CheckResult(
                f"topic {settings.topic}",
                True,
                f"{len(topic_meta.partitions)} partition(s)",
            )
        )
    else:
        results.append(
            CheckResult(
                f"topic {settings.topic}",
                False,
                f"not found on the cluster; create it in the Confluent console "
                f"(Topics > Create topic), or set CONFLUENT_TOPIC to match",
            )
        )
        return results

    if not produce_roundtrip:
        results.append(
            CheckResult(
                "produce and consume round trip",
                True,
                "skipped; pass --produce to send one real test event",
            )
        )
        return results

    try:
        from module9.ingestion.stream_consumer import KafkaStreamSource
        from module9.producers.devops_event_producer import produce_event

        probe_settings = ConfluentSettings()
        probe_settings.group_id = f"module9-livecheck-{int(time.time())}"

        report = produce_event(settings=settings)
        source = KafkaStreamSource(probe_settings)
        events = source.poll_events(max_records=1, timeout=10.0)
        source.close()

        if events:
            results.append(
                CheckResult(
                    "produce and consume round trip",
                    True,
                    f"produced to offset {report['offset']}, consumed "
                    f"{events[0].source_uri}",
                )
            )
        else:
            results.append(
                CheckResult(
                    "produce and consume round trip",
                    False,
                    f"produced to offset {report['offset']} but the consumer "
                    "read nothing within 10s",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult("produce and consume round trip", False, str(exc))
        )

    return results


# ---------------------------------------------------------------------------
# Databricks
# ---------------------------------------------------------------------------

def _classify_lineage_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "permission" in message or "denied" in message or "privilege" in message:
        return (
            "permission denied on system.access. Grant it from a SQL editor: "
            "GRANT USE SCHEMA, SELECT ON SCHEMA system.access TO `you@example.com`. "
            "If that fails, enable the access system schema from the account "
            "console first (account admin required)."
        )
    if "not found" in message or "does not exist" in message or "table_or_view" in message:
        return (
            "system.access.table_lineage does not exist, so system tables are "
            "not enabled on this metastore. Enable the access schema from the "
            "account console, or fall back to DATABRICKS_MOCK_LINEAGE=true."
        )
    return f"{exc}; fall back to DATABRICKS_MOCK_LINEAGE=true if unresolved"


def check_databricks() -> list[CheckResult]:
    results: list[CheckResult] = []
    settings = DatabricksSettings()

    try:
        settings.validate_for_live()
        results.append(
            CheckResult(
                "Databricks configuration",
                True,
                f"host={settings.hostname} warehouse={settings.http_path} "
                f"token={_mask(settings.token)}",
            )
        )
    except ValueError as exc:
        results.append(CheckResult("Databricks configuration", False, str(exc)))
        return results

    try:
        import databricks.sql  # type: ignore[import]  # noqa: F401
    except ImportError:
        results.append(
            CheckResult(
                "databricks-sql-connector installed", False, _missing_package_hint()
            )
        )
        return results

    from module9.ingestion.delta_writer import DatabricksLakehouse

    try:
        started = time.monotonic()
        lakehouse = DatabricksLakehouse(settings)
        lakehouse._execute("SELECT 1")
        elapsed = round(time.monotonic() - started, 1)
        note = (
            f"warehouse responded in {elapsed}s"
            if elapsed < 20
            else f"warehouse responded in {elapsed}s (cold start; pre-warm "
            "before the recording)"
        )
        results.append(CheckResult("SQL warehouse connectivity", True, note))
    except Exception as exc:
        results.append(
            CheckResult(
                "SQL warehouse connectivity",
                False,
                f"{exc}; check DATABRICKS_HOST, DATABRICKS_HTTP_PATH, "
                "DATABRICKS_TOKEN, and that the warehouse is running",
            )
        )
        return results

    try:
        schemas = lakehouse._execute(f"SHOW SCHEMAS IN {settings.catalog}")
        names = {str(row[0]) for row in schemas}
        missing = {settings.bronze_schema, settings.silver_schema} - names
        if missing:
            results.append(
                CheckResult(
                    "catalog and schemas",
                    False,
                    f"catalog {settings.catalog} is missing schema(s) "
                    f"{sorted(missing)}; create them in Catalog Explorer",
                )
            )
        else:
            results.append(
                CheckResult(
                    "catalog and schemas",
                    True,
                    f"{settings.catalog} has {settings.bronze_schema} and "
                    f"{settings.silver_schema}",
                )
            )
    except Exception as exc:
        results.append(
            CheckResult(
                "catalog and schemas",
                False,
                f"{exc}; create catalog {settings.catalog} with schemas "
                f"{settings.bronze_schema} and {settings.silver_schema}",
            )
        )
        return results

    try:
        lakehouse.ensure_tables()
        bronze_version = lakehouse.table_version(settings.bronze_full_name)
        silver_version = lakehouse.table_version(settings.silver_full_name)
        results.append(
            CheckResult(
                "Delta tables",
                True,
                f"{settings.bronze_full_name} v{bronze_version}, "
                f"{settings.silver_full_name} v{silver_version}",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult(
                "Delta tables",
                False,
                f"{exc}; the token needs CREATE TABLE on both schemas",
            )
        )
        return results

    if is_mock_lineage():
        results.append(
            CheckResult(
                "Unity Catalog lineage",
                True,
                "DATABRICKS_MOCK_LINEAGE=true, so lineage records are served "
                "locally and Delta stays live. Unset it to test the real "
                "system table.",
                warning=True,
            )
        )
    else:
        try:
            rows = lakehouse._execute(
                "SELECT source_table_full_name, target_table_full_name "
                "FROM system.access.table_lineage LIMIT 5"
            )
            results.append(
                CheckResult(
                    "Unity Catalog lineage",
                    True,
                    f"system.access.table_lineage readable "
                    f"({len(rows)} sample row(s); zero is fine before the "
                    "first pipeline run)",
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    "Unity Catalog lineage", False, _classify_lineage_error(exc)
                )
            )

    lakehouse.close()
    return results


# ---------------------------------------------------------------------------
# Module 7 knowledge base and Bedrock
# ---------------------------------------------------------------------------

def check_knowledge_sink() -> list[CheckResult]:
    """Report the active knowledge sink and validate a configured KB."""
    from module9.config.settings import KnowledgeBaseSettings
    from module9.ingestion.kb_sink import (
        BACKEND_BEDROCK_KB,
        BedrockManagedKBSink,
        resolve_sink,
    )

    results: list[CheckResult] = []
    settings = KnowledgeBaseSettings()

    if not settings.configured:
        detail = (
            "BEDROCK_KB_ID / BEDROCK_KB_DATA_SOURCE_ID not set, so the "
            "Module 7 memory path is used"
        )
        if settings.knowledge_base_id or settings.data_source_id:
            detail += ". One of the two is set; both are required."
        results.append(CheckResult("Amazon Bedrock Knowledge Base", True, detail, warning=True))
    else:
        try:
            described = BedrockManagedKBSink(settings).health_check()
            results.append(
                CheckResult(
                    "Amazon Bedrock Knowledge Base",
                    True,
                    f"{described}, region {settings.region}",
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    "Amazon Bedrock Knowledge Base",
                    False,
                    f"{str(exc)[:160]}; check BEDROCK_KB_ID, "
                    "BEDROCK_KB_DATA_SOURCE_ID, and the region",
                )
            )

    try:
        info = resolve_sink().info()
        note = "" if info.backend == BACKEND_BEDROCK_KB else " (fallback)"
        results.append(
            CheckResult(
                "Active knowledge sink",
                True,
                f"{info.display_name or info.backend}{note}: {info.detail}; embeddings via "
                f"{info.embedding_model}",
            )
        )
    except Exception as exc:
        results.append(CheckResult("Active knowledge sink", False, str(exc)[:140]))
    return results


def check_memory_backends() -> list[CheckResult]:
    results: list[CheckResult] = []

    if is_mock_memory():
        results.append(
            CheckResult(
                "Module 7 knowledge base",
                True,
                "AGENT_MOCK_MEMORY=true, so Atlas, Aura, and Titan embeddings "
                "are mocked in process",
                warning=True,
            )
        )
        return results

    if os.getenv("MONGO_URI") and not os.getenv("MONGODB_URI"):
        results.append(
            CheckResult(
                "MongoDB Atlas",
                False,
                "MONGO_URI is set but Module 7 reads MONGODB_URI; rename it",
            )
        )
    elif not os.getenv("MONGODB_URI"):
        results.append(
            CheckResult(
                "MongoDB Atlas",
                False,
                "MONGODB_URI not set; set it or run with AGENT_MOCK_MEMORY=true",
            )
        )
    else:
        try:
            from module7.memory.mongo_store import MongoStore

            store = MongoStore()
            count = store._col.count_documents({}, limit=1)
            results.append(
                CheckResult(
                    "MongoDB Atlas",
                    True,
                    f"connected; collection reachable (sample count {count})",
                )
            )
        except Exception as exc:
            results.append(
                CheckResult(
                    "MongoDB Atlas",
                    False,
                    f"{exc}; check MONGODB_URI and Atlas Network Access allowlist",
                )
            )

    if not os.getenv("NEO4J_URI"):
        results.append(
            CheckResult(
                "Neo4j Aura",
                False,
                "NEO4J_URI not set; set it or run with AGENT_MOCK_MEMORY=true",
            )
        )
    else:
        try:
            from module7.memory.neo4j_store import Neo4jStore

            store = Neo4jStore()
            store._driver.verify_connectivity()
            results.append(CheckResult("Neo4j Aura", True, "connectivity verified"))
        except Exception as exc:
            results.append(
                CheckResult(
                    "Neo4j Aura",
                    False,
                    f"{exc}; check NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD",
                )
            )

    try:
        from module9.ingestion.embed import embed_chunk

        vector = embed_chunk(
            "Module 9 live check: a deployment event was recorded for the "
            "checkout-api service in the production environment today."
        )
        results.append(
            CheckResult(
                "Amazon Bedrock Titan embeddings",
                True,
                f"embed returned {len(vector)} dimensions",
            )
        )
    except Exception as exc:
        results.append(
            CheckResult(
                "Amazon Bedrock Titan embeddings",
                False,
                f"{exc}; check AWS credentials and Amazon Bedrock model access for "
                "amazon.titan-embed-text-v2:0",
            )
        )

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight check for the Module 9 live partner environments."
    )
    parser.add_argument("--confluent-only", action="store_true",
                        help="Check Confluent Cloud only.")
    parser.add_argument("--databricks-only", action="store_true",
                        help="Check Databricks only.")
    parser.add_argument("--memory-only", action="store_true",
                        help="Check the Module 7 backends and Amazon Bedrock only.")
    parser.add_argument("--produce", action="store_true",
                        help="Also produce and consume one real test event.")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()

    _load_dotenv()

    # Populate the CA trust store before any TLS connection is attempted.
    from module9.config.tls import ensure_secure_ca

    ca_path = ensure_secure_ca()

    if is_mock_pipeline():
        print(
            "AGENT_MOCK_PIPELINE=true is set, so the live partners are bypassed "
            "entirely.\nUnset it in your environment and .env before running "
            "this check.",
            file=sys.stderr,
        )
        return 1

    run_all = not (args.confluent_only or args.databricks_only or args.memory_only)
    results: list[tuple[str, list[CheckResult]]] = []

    if run_all or args.confluent_only:
        results.append(("Confluent Cloud (Act 1)", check_confluent(args.produce)))
    if run_all or args.databricks_only:
        results.append((
            "Databricks (Act 2)",
            _run_with_timeout(check_databricks, 150, "Databricks checks"),
        ))
    if run_all or args.memory_only:
        results.append(("Knowledge sink", check_knowledge_sink()))
        results.append(("Memory backends and Amazon Bedrock", check_memory_backends()))

    failed = any(not r.ok for _, group in results for r in group)

    if args.json:
        print(json.dumps(
            {
                section: [
                    {"name": r.name, "ok": r.ok, "warning": r.warning,
                     "detail": r.detail}
                    for r in group
                ]
                for section, group in results
            },
            indent=2,
        ))
        return 1 if failed else 0

    print("Module 9 live environment check")
    print(f"  Python:    {sys.executable}")
    if ca_path:
        print(f"  CA bundle: {ca_path}")
    for section, group in results:
        print(f"\n{section}")
        for r in group:
            if not r.ok:
                icon = "FAIL"
            elif r.warning:
                icon = "NOTE"
            else:
                icon = "OK  "
            print(f"  [{icon}] {r.name}: {r.detail}")

    print()
    if failed:
        print("One or more checks failed. Fix the FAIL lines above, then re-run.")
        print("See module9/PARTNER_SETUP.md for the provisioning steps.")
    else:
        print("All checks passed. Next: python seed_module9_corpora.py, then")
        print("python demos/module9_demo.py --no-pause for a full rehearsal.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
