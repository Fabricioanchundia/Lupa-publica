import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from lupa_publica.load import load_bronze


def release(ocid: str, month: str, **extra: Any) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "id": f"{ocid}-{month}-compiled",
        "date": f"{month}-15T10:00:00-05:00",
        "tag": ["tender"],
        **extra,
    }


def write_jsonl(path: Path, releases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(item, ensure_ascii=False) for item in releases)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def bronze_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "bronze"
    write_jsonl(
        folder / "2025-01.jsonl",
        [
            release("ocds-5wno2w-A", "2025-01", tender={"value": {"amount": 100.5}}),
            release("ocds-5wno2w-B", "2025-01", buyer={"name": "GAD MUNICIPAL DE MANTA"}),
        ],
    )
    write_jsonl(folder / "2025-02.jsonl", [release("ocds-5wno2w-A", "2025-02")])
    return folder


def test_loads_all_months(tmp_path: Path, bronze_dir: Path) -> None:
    report = load_bronze(tmp_path / "lupa.duckdb", bronze_dir)

    assert report.files == 2
    assert report.rows == 3
    assert report.rows_per_month == {"2025-01": 2, "2025-02": 1}


def test_reports_processes_repeated_across_months(tmp_path: Path, bronze_dir: Path) -> None:
    report = load_bronze(tmp_path / "lupa.duckdb", bronze_dir)

    assert report.distinct_ocids == 2
    assert report.cross_month_duplicates == 1


def test_keeps_payload_queryable(tmp_path: Path, bronze_dir: Path) -> None:
    db = tmp_path / "lupa.duckdb"
    load_bronze(db, bronze_dir)

    with duckdb.connect(str(db), read_only=True) as con:
        rows = con.execute(
            "SELECT payload ->> '$.tender.value.amount', payload ->> '$.buyer.name' "
            "FROM bronze.releases WHERE source_month = '2025-01' ORDER BY ocid"
        ).fetchall()

    assert rows == [("100.5", None), (None, "GAD MUNICIPAL DE MANTA")]


def test_is_idempotent(tmp_path: Path, bronze_dir: Path) -> None:
    db = tmp_path / "lupa.duckdb"

    first = load_bronze(db, bronze_dir)
    second = load_bronze(db, bronze_dir)

    assert first == second


def test_fails_when_there_is_nothing_to_load(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_bronze(tmp_path / "lupa.duckdb", tmp_path / "empty")
