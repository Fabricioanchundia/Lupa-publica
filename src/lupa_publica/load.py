"""Load bronze JSONL files into DuckDB.

The table is rebuilt from all monthly files on every run. That keeps the load
idempotent: running it twice gives exactly the same table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

CREATE_RELEASES = r"""
CREATE OR REPLACE TABLE bronze.releases AS
SELECT
    json ->> '$.ocid' AS ocid,
    json ->> '$.id' AS release_id,
    CAST(json ->> '$.date' AS TIMESTAMPTZ) AS release_date,
    regexp_extract(filename, '(\d{4}-\d{2})\.jsonl$', 1) AS source_month,
    json AS payload,
    current_timestamp AS loaded_at
FROM read_ndjson_objects(?, filename = true)
"""


@dataclass(frozen=True)
class LoadReport:
    """Summary of the bronze table after a load."""

    files: int
    rows: int
    distinct_ocids: int
    rows_per_month: dict[str, int]

    @property
    def cross_month_duplicates(self) -> int:
        """Processes that appear in more than one monthly file."""
        return self.rows - self.distinct_ocids


def load_bronze(db_path: Path, jsonl_dir: Path) -> LoadReport:
    """Rebuild ``bronze.releases`` in ``db_path`` from every ``*.jsonl`` in ``jsonl_dir``."""
    files = sorted(str(path) for path in jsonl_dir.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no .jsonl files found in {jsonl_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        con.execute(CREATE_RELEASES, [files])
        totals = con.execute(
            "SELECT count(*), count(DISTINCT ocid) FROM bronze.releases"
        ).fetchone()
        per_month = con.execute(
            "SELECT source_month, count(*) FROM bronze.releases GROUP BY 1 ORDER BY 1"
        ).fetchall()

    if totals is None:
        raise RuntimeError("could not read totals from bronze.releases")
    report = LoadReport(
        files=len(files),
        rows=int(totals[0]),
        distinct_ocids=int(totals[1]),
        rows_per_month={str(month): int(count) for month, count in per_month},
    )
    logger.info(
        "bronze.releases: %d rows from %d files (%d processes in more than one month)",
        report.rows,
        report.files,
        report.cross_month_duplicates,
    )
    return report
