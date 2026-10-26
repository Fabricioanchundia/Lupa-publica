"""Validate SERCOP monthly files and write them as line-delimited compiled releases.

This is the bronze layer: data is kept exactly as published, one compiled
release per line (the format expected by OCP's Cardinal), but only after
basic structural validation.
"""

from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

OCID_PREFIX = "ocds-5wno2w-"
MAX_ERRORS_KEPT = 20


class DataQualityError(RuntimeError):
    """Raised when a file is too broken to be trusted."""


class ReleaseHeader(BaseModel):
    """Minimum fields every compiled release must have. Other fields are kept untouched."""

    model_config = ConfigDict(extra="ignore")

    ocid: str = Field(pattern=rf"^{OCID_PREFIX}")
    id: str = Field(min_length=1)
    date: datetime
    tag: list[str] = Field(min_length=1)


@dataclass
class BronzeReport:
    """What happened while converting one monthly file."""

    month: str
    packages: int = 0
    broken_packages: int = 0
    releases: int = 0
    written: int = 0
    rejected: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def reject_ratio(self) -> float:
        total = self.releases + self.broken_packages
        return self.rejected / total if total else 0.0

    def add_error(self, message: str) -> None:
        self.rejected += 1
        if len(self.errors) < MAX_ERRORS_KEPT:
            self.errors.append(message)


def read_packages(zip_path: Path) -> list[Any]:
    """Return the JSON array stored in a SERCOP monthly ZIP."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [name for name in zf.namelist() if name.endswith(".json")]
        if len(members) != 1:
            raise DataQualityError(f"{zip_path.name}: expected 1 JSON file, found {members}")
        with zf.open(members[0]) as fh:
            data = json.load(fh)
    if not isinstance(data, list):
        raise DataQualityError(f"{zip_path.name}: expected a JSON array, got {type(data).__name__}")
    return data


def zip_to_jsonl(zip_path: Path, out_dir: Path, *, max_reject_ratio: float = 0.01) -> BronzeReport:
    """Validate ``<YYYY-MM>.zip`` and write ``<out_dir>/<YYYY-MM>.jsonl`` atomically.

    Raises DataQualityError (and writes nothing) if too many releases are invalid.
    """
    report = BronzeReport(month=zip_path.stem)
    packages = read_packages(zip_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{report.month}.jsonl"
    partial = target.with_name(target.name + ".part")
    seen: set[str] = set()

    try:
        with partial.open("w", encoding="utf-8") as out:
            for index, package in enumerate(packages):
                report.packages += 1
                releases = package.get("releases") if isinstance(package, dict) else None
                if not isinstance(releases, list):
                    report.broken_packages += 1
                    report.add_error(f"package {index}: missing 'releases' list")
                    continue
                for release in releases:
                    report.releases += 1
                    try:
                        header = ReleaseHeader.model_validate(release)
                    except ValidationError as exc:
                        first = exc.errors()[0]
                        where = ".".join(str(part) for part in first["loc"])
                        report.add_error(f"package {index}: {where}: {first['msg']}")
                        continue
                    if header.ocid in seen:
                        report.duplicates += 1
                        continue
                    seen.add(header.ocid)
                    out.write(json.dumps(release, ensure_ascii=False) + "\n")
                    report.written += 1

        if report.reject_ratio > max_reject_ratio:
            raise DataQualityError(
                f"{report.month}: {report.rejected} invalid records "
                f"({report.reject_ratio:.1%} > {max_reject_ratio:.1%}). "
                f"First errors: {report.errors[:3]}"
            )
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)

    logger.info(
        "%s: %d written, %d rejected, %d duplicates",
        report.month,
        report.written,
        report.rejected,
        report.duplicates,
    )
    return report
