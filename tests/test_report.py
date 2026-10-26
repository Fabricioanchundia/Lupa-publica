import json
from pathlib import Path
from typing import Any

import pytest

from lupa_publica.load import load_bronze
from lupa_publica.report import build_report, markdown_table, render_markdown


def buyer(region: str | None) -> dict[str, Any]:
    party: dict[str, Any] = {"name": "ENTIDAD", "roles": ["buyer"]}
    if region:
        party["address"] = {"region": region}
    return party


def release(ocid: str, month: str, **extra: Any) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "id": f"{ocid}-compiled",
        "date": f"{month}-15T10:00:00-05:00",
        "tag": ["tender"],
        **extra,
    }


@pytest.fixture
def db(tmp_path: Path) -> Path:
    complete = release(
        "ocds-5wno2w-A",
        "2025-01",
        tender={"value": {"amount": 100.0}, "procurementMethod": "open"},
        awards=[{"id": "1"}],
        contracts=[{"id": "1"}],
        parties=[buyer("MANABI")],
    )
    planning_only = release("ocds-5wno2w-B", "2025-01", parties=[buyer("PICHINCHA")])
    zero_amount = release(
        "ocds-5wno2w-C",
        "2025-02",
        tender={"value": {"amount": 0}, "procurementMethod": "selective"},
        parties=[buyer(None)],
    )
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    for month, items in {"2025-01": [complete, planning_only], "2025-02": [zero_amount]}.items():
        lines = "\n".join(json.dumps(item) for item in items) + "\n"
        (bronze / f"{month}.jsonl").write_text(lines, encoding="utf-8")

    path = tmp_path / "lupa.duckdb"
    load_bronze(path, bronze)
    return path


def test_monthly_coverage(db: Path) -> None:
    report = build_report(db)

    assert report.total_processes == 3
    assert (report.first_month, report.last_month) == ("2025-01", "2025-02")
    assert report.monthly == [
        ("2025-01", 2, 50.0, 50.0, 50.0, 50.0, 50.0),
        ("2025-02", 1, 100.0, 0.0, 0.0, 0.0, 0.0),
    ]


def test_zero_amount_is_not_counted_as_a_usable_budget(db: Path) -> None:
    february = build_report(db).monthly[1]

    assert february[5] == 0.0


def test_regions_include_unknown(db: Path) -> None:
    regions = {row[0]: row[1] for row in build_report(db).regions}

    assert regions == {"MANABI": 1, "PICHINCHA": 1, "UNKNOWN": 1}


def test_markdown_contains_tables_and_disclaimer(db: Path) -> None:
    text = render_markdown(build_report(db))

    assert "| 2025-01 | 2 | 50.0 | 50.0 | 50.0 | 50.0 | 50.0 |" in text
    assert "not** statistics of public spending" in text
    assert "## Known gaps" in text


def test_markdown_table_formats_values() -> None:
    table = markdown_table(("a", "b", "c"), [(1234, 12.345, None)])

    assert table.splitlines()[-1] == "| 1,234 | 12.3 | — |"
