"""Coverage report: what the published data contains, and what it does not.

The report is the factual basis of the methodology page. It describes the
SERCOP OCDS bulk files; it is not a statistic of public spending.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

TOTALS_SQL = "SELECT count(*), min(source_month), max(source_month) FROM bronze.releases"

MONTHLY_SQL = """
SELECT
    source_month,
    count(*) AS processes,
    round(100.0 * count(*) FILTER (WHERE (payload -> '$.tender') IS NOT NULL) / count(*), 1),
    round(100.0 * count(*) FILTER (
        WHERE coalesce(json_array_length(payload -> '$.awards'), 0) > 0) / count(*), 1),
    round(100.0 * count(*) FILTER (
        WHERE coalesce(json_array_length(payload -> '$.contracts'), 0) > 0) / count(*), 1),
    round(100.0 * count(*) FILTER (
        WHERE TRY_CAST(payload ->> '$.tender.value.amount' AS DOUBLE) > 0) / count(*), 1),
    round(100.0 * count(*) FILTER (
        WHERE (payload ->> '$.tender.procurementMethod') = 'open') / count(*), 1)
FROM bronze.releases
GROUP BY source_month
ORDER BY source_month
"""

REGIONS_SQL = """
WITH buyers AS (
    SELECT r.ocid, p.value AS party
    FROM bronze.releases AS r, json_each(r.payload, '$.parties') AS p
    WHERE list_contains(CAST(p.value -> '$.roles' AS VARCHAR[]), 'buyer')
)
SELECT
    coalesce((party ->> '$.address.region'), 'UNKNOWN') AS region,
    count(DISTINCT ocid) AS processes,
    round(100.0 * count(DISTINCT ocid) / (SELECT count(*) FROM bronze.releases), 1)
FROM buyers
GROUP BY 1
ORDER BY 2 DESC, 1
"""

MONTHLY_HEADERS = (
    "Month",
    "Processes",
    "% with tender",
    "% with award",
    "% with contract",
    "% tender amount > 0",
    "% open method",
)
REGION_HEADERS = ("Buyer region", "Processes", "% of all processes")

DISCLAIMER = (
    "> These figures describe what SERCOP publishes in its OCDS bulk files. "
    "They are **not** statistics of public spending: a high number of processes "
    "does not mean high spending, and missing data does not mean wrongdoing."
)

KNOWN_GAPS = """\
- **Ínfima cuantía** purchases are not published in this source.
- **Emergency procedures** cannot be identified as a procedure type.
- **Processes changed after the rolling window** (e.g. contract amendments) are only \
captured when history is reloaded (see ADR-0001).
- **Guayas** looked under-represented in early samples; compare its share above with \
its population before drawing conclusions."""


@dataclass(frozen=True)
class CoverageReport:
    """Facts about the content of ``bronze.releases``."""

    generated_at: datetime
    total_processes: int
    first_month: str
    last_month: str
    monthly: list[tuple[Any, ...]]
    regions: list[tuple[Any, ...]]


def build_report(db_path: Path) -> CoverageReport:
    """Query the bronze table (read-only) and collect the coverage figures."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        totals = con.execute(TOTALS_SQL).fetchone()
        monthly = con.execute(MONTHLY_SQL).fetchall()
        regions = con.execute(REGIONS_SQL).fetchall()

    if totals is None or not totals[0]:
        raise ValueError(f"bronze.releases in {db_path} is empty")
    return CoverageReport(
        generated_at=datetime.now(UTC),
        total_processes=int(totals[0]),
        first_month=str(totals[1]),
        last_month=str(totals[2]),
        monthly=monthly,
        regions=regions,
    )


def _format(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render rows as a GitHub-flavoured Markdown table."""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(_format(value) for value in row) + " |" for row in rows]
    return "\n".join(lines)


def render_markdown(report: CoverageReport) -> str:
    """The full report as a Markdown document."""
    return "\n".join(
        [
            "# Data coverage report",
            "",
            f"_Generated on {report.generated_at:%Y-%m-%d %H:%M} UTC from `bronze.releases`: "
            f"{report.total_processes:,} processes, {report.first_month} to "
            f"{report.last_month}._",
            "",
            DISCLAIMER,
            "",
            "## By month",
            "",
            markdown_table(MONTHLY_HEADERS, report.monthly),
            "",
            "- **% with award / contract:** processes that already have that stage published.",
            "- **% tender amount > 0:** processes with a usable estimated budget.",
            "- **% open method:** OCDS `procurementMethod = open` (competitive procedures).",
            "",
            "## By buyer region",
            "",
            markdown_table(REGION_HEADERS, report.regions),
            "",
            "## Known gaps",
            "",
            KNOWN_GAPS,
            "",
        ]
    )
