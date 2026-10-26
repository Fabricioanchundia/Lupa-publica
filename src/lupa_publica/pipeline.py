"""End-to-end ingestion: download -> validate (bronze) -> load into DuckDB."""

from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import httpx

from lupa_publica.bronze import BronzeReport, DataQualityError, zip_to_jsonl
from lupa_publica.extract import DownloadError, Month, download_month
from lupa_publica.load import LoadReport, load_bronze

logger = logging.getLogger(__name__)

# Errors we expect from bad or missing data. Anything else is a bug and must crash.
EXPECTED_ERRORS = (DownloadError, DataQualityError, zipfile.BadZipFile, ValueError)


@dataclass(frozen=True)
class DataPaths:
    """Where each layer lives on disk."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw" / "bulk"

    @property
    def bronze(self) -> Path:
        return self.root / "bronze" / "releases"

    @property
    def db(self) -> Path:
        return self.root / "lupa.duckdb"


@dataclass
class IngestResult:
    """Outcome of one pipeline run."""

    months: list[BronzeReport] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    load: LoadReport | None = None

    @property
    def ok(self) -> bool:
        return not self.failures and self.load is not None


def last_months(n: int, today: date) -> list[Month]:
    """The ``n`` most recent months up to and including ``today``'s month, oldest first."""
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    year, month = today.year, today.month
    months: list[Month] = []
    for _ in range(n):
        months.append(Month(year, month))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return sorted(months)


def month_range(start: Month, end: Month) -> list[Month]:
    """Every month from ``start`` to ``end``, both included."""
    if start > end:
        raise ValueError(f"start {start.label} is after end {end.label}")
    months: list[Month] = []
    current = start
    while current <= end:
        months.append(current)
        year, month = current.year, current.month
        current = Month(year + 1, 1) if month == 12 else Month(year, month + 1)
    return months


def ingest(
    months: list[Month],
    paths: DataPaths,
    *,
    refresh: bool,
    client: httpx.Client | None = None,
) -> IngestResult:
    """Download, validate and load ``months``.

    ``refresh=True`` re-downloads files even if they exist, because SERCOP
    regenerates recent months every night. One failing month does not stop
    the others; it is reported in ``failures`` so the run can exit with an error.
    """
    result = IngestResult()
    for month in months:
        try:
            zip_path = download_month(month, paths.raw, client=client, force=refresh)
            result.months.append(zip_to_jsonl(zip_path, paths.bronze))
        except EXPECTED_ERRORS as exc:
            logger.error("%s failed: %s", month.label, exc)
            result.failures[month.label] = str(exc)

    if any(paths.bronze.glob("*.jsonl")):
        result.load = load_bronze(paths.db, paths.bronze)
    return result
