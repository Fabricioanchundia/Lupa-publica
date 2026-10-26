import io
import json
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from lupa_publica.extract import Month
from lupa_publica.pipeline import DataPaths, ingest, last_months, month_range


def monthly_zip(month: str) -> bytes:
    """A tiny SERCOP-like monthly file with one process."""
    year, mm = month.split("-")
    package = {
        "releases": [
            {
                "ocid": f"ocds-5wno2w-TEST-{month}",
                "id": f"TEST-{month}-compiled",
                "date": f"{year}-{mm}-15T10:00:00-05:00",
                "tag": ["tender"],
            }
        ]
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(f"releases_{year}_mes.json", json.dumps([package]))
    return buffer.getvalue()


def fake_sercop(missing: set[str] | None = None) -> tuple[httpx.Client, list[str]]:
    """A fake SERCOP server; months in ``missing`` answer 404. Returns client and call log."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        month = f"{request.url.params['year']}-{request.url.params['month']}"
        calls.append(month)
        if missing and month in missing:
            return httpx.Response(404)
        return httpx.Response(200, content=monthly_zip(month))

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_last_months_crosses_year_boundary() -> None:
    assert last_months(3, date(2026, 1, 15)) == [
        Month(2025, 11),
        Month(2025, 12),
        Month(2026, 1),
    ]


def test_last_months_rejects_zero() -> None:
    with pytest.raises(ValueError):
        last_months(0, date(2026, 1, 15))


def test_month_range_includes_both_ends() -> None:
    months = month_range(Month(2025, 11), Month(2026, 2))

    assert [m.label for m in months] == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_month_range_rejects_inverted_range() -> None:
    with pytest.raises(ValueError):
        month_range(Month(2026, 2), Month(2025, 11))


def test_ingest_runs_end_to_end(tmp_path: Path) -> None:
    client, _ = fake_sercop()
    paths = DataPaths(tmp_path)

    result = ingest([Month(2025, 1), Month(2025, 2)], paths, refresh=False, client=client)

    assert result.ok
    assert result.load is not None
    assert result.load.rows_per_month == {"2025-01": 1, "2025-02": 1}
    assert paths.db.exists()


def test_one_failing_month_does_not_stop_the_others(tmp_path: Path) -> None:
    client, _ = fake_sercop(missing={"2025-02"})

    result = ingest(
        [Month(2025, 1), Month(2025, 2), Month(2025, 3)],
        DataPaths(tmp_path),
        refresh=False,
        client=client,
    )

    assert not result.ok
    assert set(result.failures) == {"2025-02"}
    assert result.load is not None
    assert result.load.rows_per_month == {"2025-01": 1, "2025-03": 1}


def test_refresh_downloads_again_but_backfill_does_not(tmp_path: Path) -> None:
    months = [Month(2025, 1)]
    client, calls = fake_sercop()

    ingest(months, DataPaths(tmp_path), refresh=False, client=client)
    ingest(months, DataPaths(tmp_path), refresh=False, client=client)
    assert calls == ["2025-01"]

    ingest(months, DataPaths(tmp_path), refresh=True, client=client)
    assert calls == ["2025-01", "2025-01"]
