# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/mock/databricks_mock.py
================================
In-memory Databricks mock: Delta tables with monotonically increasing
versions and deterministic Unity Catalog lineage records.

MockLakehouse mirrors the live surface in ingestion/delta_writer.py exactly,
including the bronze-to-silver derivation: write_silver looks the bronze row
up by ingest_id and normalizes it, which is the in-memory equivalent of the
live INSERT ... SELECT that Unity Catalog traces.
"""
from __future__ import annotations

# Module-level lakehouse state so producer, pipeline, and demo sections
# observe the same tables within one process.
_TABLES: dict[str, "MockDeltaTable"] = {}
_LINEAGE: list[dict] = []


def reset() -> None:
    """Clear all tables and lineage records (test isolation)."""
    _TABLES.clear()
    _LINEAGE.clear()


class MockDeltaTable:
    """A Delta table as a list of row dicts with a version counter.

    Every committed write increments the version by one, matching Delta
    Lake's transaction log semantics.
    """

    def __init__(self, full_name: str) -> None:
        self.full_name = full_name
        self.rows: list[dict] = []
        self.version = 0

    def insert(self, row: dict) -> int:
        """Insert one row as a single commit; returns the new table version."""
        self.rows.append(dict(row))
        self.version += 1
        return self.version


def _get_table(full_name: str) -> MockDeltaTable:
    if full_name not in _TABLES:
        _TABLES[full_name] = MockDeltaTable(full_name)
    return _TABLES[full_name]


class MockLakehouse:
    """Mirrors the live Databricks read/write surface in delta_writer.py."""

    def __init__(self, settings) -> None:
        self._settings = settings

    def ensure_tables(self) -> None:
        """Create both tables so versions and reads behave like the live path."""
        _get_table(self._settings.bronze_full_name)
        _get_table(self._settings.silver_full_name)

    def write_bronze(self, raw_event: dict, ingest_id: str) -> int:
        """Land the raw event in the bronze Delta table; returns the version."""
        import json
        from module9.ingestion.delta_writer import _now

        table = _get_table(self._settings.bronze_full_name)
        return table.insert(
            {
                "ingest_id": ingest_id,
                "ingest_time": _now(),
                "payload": json.dumps(raw_event),
            }
        )

    def write_silver(self, ingest_id: str) -> int:
        """Derive the silver row from the bronze row with the same ingest_id.

        Records the Unity Catalog table-level lineage edge the equivalent
        live INSERT ... SELECT would generate.
        """
        import json
        from module9.ingestion.delta_writer import (
            _synthetic_lineage,
            normalize_event,
        )

        bronze = _get_table(self._settings.bronze_full_name)
        source_row = next(
            (r for r in reversed(bronze.rows) if r.get("ingest_id") == ingest_id),
            None,
        )
        if source_row is None:
            raise ValueError(
                f"No bronze row with ingest_id {ingest_id!r}; "
                "write_bronze must run before write_silver"
            )

        normalized = normalize_event(json.loads(source_row["payload"]))
        normalized["ingest_id"] = ingest_id

        table = _get_table(self._settings.silver_full_name)
        version = table.insert(normalized)
        _LINEAGE.append(
            _synthetic_lineage(
                self._settings.bronze_full_name,
                self._settings.silver_full_name,
                version,
            )
        )
        return version

    def table_lineage(self, target_table: str | None = None) -> list[dict]:
        """Return lineage records oldest first, newest last.

        Mirrors a SELECT against system.access.table_lineage filtered by
        target table full name.
        """
        target = target_table or self._settings.silver_full_name
        return [
            record
            for record in _LINEAGE
            if record["target_table_full_name"] == target
        ]

    def read_table(self, full_name: str, last_n: int = 5) -> list[dict]:
        """Return the last N rows of a table (demo display helper)."""
        return list(_get_table(full_name).rows[-last_n:])

    def table_version(self, full_name: str) -> int:
        return _get_table(full_name).version

    def truncate_tables(self) -> dict:
        """Empty both tables, mirroring the live truncate surface."""
        self.ensure_tables()
        for name in (
            self._settings.bronze_full_name,
            self._settings.silver_full_name,
        ):
            table = _get_table(name)
            table.rows.clear()
            table.version += 1
        return {
            "bronze_version": self.table_version(self._settings.bronze_full_name),
            "silver_version": self.table_version(self._settings.silver_full_name),
        }

    def close(self) -> None:
        return None
