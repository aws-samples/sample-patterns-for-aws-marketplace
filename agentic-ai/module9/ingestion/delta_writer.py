# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/ingestion/delta_writer.py
==================================
The Databricks seam: lands consumed events in Delta Lake (bronze, then a
normalized silver table) and reads the Unity Catalog table-level lineage
edge the write produces (v5 Section 5.3).

Why silver is written with a SELECT from bronze
-----------------------------------------------
Unity Catalog captures table-to-table lineage automatically, but only when a
single query reads one table and writes another. Two independent INSERT
statements built from the same Python dict would produce two unrelated
tables and no lineage edge, so the Act 2 governance beat would show an
empty lineage result even with everything provisioned correctly. The silver
write is therefore a real transformation:

    INSERT INTO silver SELECT <normalized columns> FROM bronze
    WHERE ingest_id = :ingest_id

That is a genuine read of bronze and write to silver, which Unity Catalog
traces at both table and column level.

The live path uses the Databricks SQL connector against a serverless SQL
warehouse. Under AGENT_MOCK_PIPELINE=true, MockLakehouse serves the same
surface from in-memory tables with monotonically increasing Delta versions.
Setting DATABRICKS_MOCK_LINEAGE=true keeps Delta fully live but serves the
lineage record locally, for workspaces where the system tables are not
readable.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from module9.config.settings import (
    DatabricksSettings,
    is_mock_databricks,
    is_mock_lineage,
)
from module9.ingestion.stream_consumer import ConsumedEvent

# Silver column order, shared by the live SQL and the mock so both tables
# have identical shape.
SILVER_COLUMNS = (
    "ingest_id",
    "event_type",
    "event_time",
    "service",
    "environment",
    "region",
    "status",
    "attributes",
)

# Lineage capture states, stamped on every chunk so provenance is honest
# about where the lineage anchor came from.
LINEAGE_CAPTURED = "captured"    # read from system.access.table_lineage
LINEAGE_PENDING = "pending"      # write succeeded, system table not yet populated
LINEAGE_SYNTHETIC = "synthetic"  # served locally via DATABRICKS_MOCK_LINEAGE or mock


@dataclass(frozen=True)
class DeltaWriteResult:
    """Outcome of landing one event: the Databricks provenance anchors."""

    bronze_table: str
    bronze_version: int
    silver_table: str
    silver_version: int
    unity_catalog_lineage_id: str
    ingest_id: str = ""
    unity_catalog_lineage_status: str = LINEAGE_PENDING


def new_ingest_id() -> str:
    """Correlation key joining one bronze row to its silver row."""
    return uuid.uuid4().hex


def normalize_event(event: dict) -> dict:
    """Bronze-to-silver normalization, the Python reference implementation.

    Bronze holds the raw payload untouched; silver holds the normalized
    schema the chunker consumes. Unknown event types still land, carrying
    their payload in attributes, so schema evolution never drops data
    (v5 Section 8.3).

    The live path expresses this same mapping in SQL so Unity Catalog can
    see the transformation. Keep the two in step: this function is the
    contract the mock and the tests assert against.
    """
    event_type = str(event.get("event_type", "unknown"))
    return {
        "event_type": event_type,
        "event_time": str(event.get("event_time", "")),
        "service": str(
            event.get("service")
            or ",".join(event.get("affected_services", []))
            or "unknown"
        ),
        "environment": str(event.get("environment", "")),
        "region": str(event.get("region", "")),
        "status": str(event.get("status") or event.get("severity") or ""),
        "attributes": json.dumps(event, sort_keys=True),
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthetic_lineage(
    source_table: str, target_table: str, target_version: int
) -> dict:
    """Deterministic lineage record, used by the mock and by the
    DATABRICKS_MOCK_LINEAGE fallback."""
    seed = f"{source_table}->{target_table}@{target_version}"
    return {
        "lineage_id": f"lin-{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}",
        "source_table_full_name": source_table,
        "target_table_full_name": target_table,
        "target_table_version": target_version,
        "entity_type": "TABLE",
        "event_time": _now(),
    }


class DatabricksLakehouse:
    """Live Databricks Delta writer over the SQL warehouse connector."""

    def __init__(self, settings: DatabricksSettings) -> None:
        settings.validate_for_live()
        self._settings = settings
        self._tables_ready = False

        # Populate the CA trust store before the first TLS handshake. Some
        # Python builds ship without one, which surfaces as a certificate
        # verification failure against a valid chain.
        from module9.config.tls import ensure_secure_ca

        ensure_secure_ca()

        from databricks import sql as databricks_sql  # type: ignore[import]

        self._connection = databricks_sql.connect(
            server_hostname=settings.hostname,
            http_path=settings.http_path,
            access_token=settings.token,
        )

    def _execute(self, statement: str, params: dict | None = None) -> list:
        with self._connection.cursor() as cursor:
            cursor.execute(statement, params or None)
            if cursor.description is None:
                return []
            return cursor.fetchall()

    def ensure_tables(self) -> None:
        """Create the bronze and silver Delta tables if they do not exist.

        Idempotent, and safe to call on every run. The catalog and the two
        schemas must already exist; see module9/PARTNER_SETUP.md.
        """
        if self._tables_ready:
            return
        s = self._settings
        self._execute(
            f"CREATE TABLE IF NOT EXISTS {s.bronze_full_name} ("
            "  ingest_id STRING,"
            "  ingest_time TIMESTAMP,"
            "  payload STRING"
            ") USING DELTA"
        )
        self._execute(
            f"CREATE TABLE IF NOT EXISTS {s.silver_full_name} ("
            "  ingest_id STRING,"
            "  event_type STRING,"
            "  event_time STRING,"
            "  service STRING,"
            "  environment STRING,"
            "  region STRING,"
            "  status STRING,"
            "  attributes STRING"
            ") USING DELTA"
        )
        self._tables_ready = True

    def table_version(self, full_name: str) -> int:
        rows = self._execute(f"DESCRIBE HISTORY {full_name} LIMIT 1")
        # DESCRIBE HISTORY returns newest first; column 0 is the version.
        return int(rows[0][0]) if rows else 0

    def write_bronze(self, raw_event: dict, ingest_id: str) -> int:
        """Land the raw event untouched; returns the new bronze version."""
        self.ensure_tables()
        self._execute(
            f"INSERT INTO {self._settings.bronze_full_name} "
            "(ingest_id, ingest_time, payload) "
            "VALUES (:ingest_id, current_timestamp(), :payload)",
            {"ingest_id": ingest_id, "payload": json.dumps(raw_event)},
        )
        return self.table_version(self._settings.bronze_full_name)

    def write_silver(self, ingest_id: str) -> int:
        """Derive the normalized silver row from bronze in one query.

        This read-then-write is what Unity Catalog traces. The column
        expressions mirror normalize_event.
        """
        self.ensure_tables()
        s = self._settings
        self._execute(
            f"INSERT INTO {s.silver_full_name} "
            "(ingest_id, event_type, event_time, service, environment, "
            " region, status, attributes) "
            "SELECT"
            "  ingest_id,"
            "  coalesce(get_json_object(payload, '$.event_type'), 'unknown'),"
            "  coalesce(get_json_object(payload, '$.event_time'), ''),"
            "  coalesce("
            "    get_json_object(payload, '$.service'),"
            "    nullif(concat_ws(',', from_json("
            "      get_json_object(payload, '$.affected_services'),"
            "      'array<string>')), ''),"
            "    'unknown'),"
            "  coalesce(get_json_object(payload, '$.environment'), ''),"
            "  coalesce(get_json_object(payload, '$.region'), ''),"
            "  coalesce(get_json_object(payload, '$.status'),"
            "           get_json_object(payload, '$.severity'), ''),"
            "  payload "
            f"FROM {s.bronze_full_name} "
            "WHERE ingest_id = :ingest_id",
            {"ingest_id": ingest_id},
        )
        return self.table_version(s.silver_full_name)

    def table_lineage(self, target_table: str | None = None) -> list[dict]:
        """Read the Unity Catalog lineage edges for the target table.

        system.access.table_lineage is populated automatically by Unity
        Catalog as data moves bronze to silver. Availability must be
        verified per workspace; set DATABRICKS_MOCK_LINEAGE=true to serve
        deterministic records locally while keeping Delta live.

        Returns records oldest first, so the newest edge is the last item.
        """
        target = target_table or self._settings.silver_full_name
        if is_mock_lineage():
            return [
                _synthetic_lineage(
                    self._settings.bronze_full_name,
                    target,
                    self.table_version(target),
                )
            ]
        rows = self._execute(
            "SELECT source_table_full_name, target_table_full_name, "
            "       entity_type, event_time "
            "FROM system.access.table_lineage "
            "WHERE target_table_full_name = :target "
            "  AND source_table_full_name IS NOT NULL "
            "ORDER BY event_time DESC LIMIT 10",
            {"target": target},
        )
        records = [
            {
                "lineage_id": _synthetic_lineage(str(r[0]), str(r[1]), 0)[
                    "lineage_id"
                ],
                "source_table_full_name": str(r[0]),
                "target_table_full_name": str(r[1]),
                # r[2] is entity_type, which is null for table-to-table
                # lineage and only populated for column-level records, so it
                # is left out of the display rather than shown as None.
                "event_time": str(r[3]),
            }
            for r in rows
        ]
        records.reverse()  # oldest first, newest last
        return records

    def read_table(self, full_name: str, last_n: int = 5) -> list[dict]:
        rows = self._execute(f"SELECT * FROM {full_name} LIMIT {int(last_n)}")
        return [dict(enumerate(r)) for r in rows]

    def truncate_tables(self) -> dict:
        """Empty the demo bronze and silver tables.

        Used by the demo prep step so a repeated run starts from a known
        state. Delta versions keep incrementing, which is correct: the
        transaction log is history, not state. Unity Catalog lineage edges
        already captured are unaffected.
        """
        self.ensure_tables()
        for table in (
            self._settings.bronze_full_name,
            self._settings.silver_full_name,
        ):
            self._execute(f"TRUNCATE TABLE {table}")
        return {
            "bronze_version": self.table_version(self._settings.bronze_full_name),
            "silver_version": self.table_version(self._settings.silver_full_name),
        }

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception:
            pass


def create_lakehouse(settings: DatabricksSettings | None = None):
    """Factory: MockLakehouse when Databricks is mocked, else live."""
    settings = settings or DatabricksSettings()
    if is_mock_databricks():
        from module9.mock.databricks_mock import MockLakehouse

        return MockLakehouse(settings)
    return DatabricksLakehouse(settings)


def land_event(
    consumed: ConsumedEvent,
    lakehouse=None,
    settings: DatabricksSettings | None = None,
) -> DeltaWriteResult:
    """Land one consumed event: bronze, then silver derived from bronze,
    then read the lineage edge the transformation produced.

    Returns the Databricks provenance anchors (Delta versions and the
    Unity Catalog lineage id) that ride on every chunk from this event.
    """
    settings = settings or DatabricksSettings()
    lakehouse = lakehouse or create_lakehouse(settings)
    ingest_id = new_ingest_id()

    bronze_version = lakehouse.write_bronze(consumed.event, ingest_id)
    silver_version = lakehouse.write_silver(ingest_id)

    # Unity Catalog lineage system tables are populated in batch, so the edge
    # for a write made seconds ago is often not queryable yet. Report that
    # state explicitly rather than emitting a blank anchor: the Delta table
    # and version are known for certain either way, and Catalog Explorer
    # shows the graph in near real time.
    lineage_records = lakehouse.table_lineage(settings.silver_full_name)
    if lineage_records:
        lineage_id = lineage_records[-1]["lineage_id"]
        status = LINEAGE_SYNTHETIC if is_mock_lineage() else LINEAGE_CAPTURED
    else:
        lineage_id = ""
        status = LINEAGE_PENDING

    return DeltaWriteResult(
        bronze_table=settings.bronze_full_name,
        bronze_version=bronze_version,
        silver_table=settings.silver_full_name,
        silver_version=silver_version,
        unity_catalog_lineage_id=lineage_id,
        ingest_id=ingest_id,
        unity_catalog_lineage_status=status,
    )
