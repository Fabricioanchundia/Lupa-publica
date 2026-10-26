import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from lupa_publica.bronze import DataQualityError, zip_to_jsonl


def release(ocid: str = "ocds-5wno2w-TEST-1", **extra: Any) -> dict[str, Any]:
    return {
        "ocid": ocid,
        "id": f"{ocid}-compiled",
        "date": "2025-01-15T10:00:00-05:00",
        "tag": ["tender"],
        **extra,
    }


def package(*releases: dict[str, Any]) -> dict[str, Any]:
    return {"version": "1.1", "releases": list(releases)}


def write_zip(path: Path, payload: Any) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("releases_2025_enero.json", json.dumps(payload))
    return path


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_writes_one_release_per_line(tmp_path: Path) -> None:
    src = write_zip(
        tmp_path / "2025-01.zip",
        [package(release("ocds-5wno2w-A")), package(release("ocds-5wno2w-B"))],
    )

    report = zip_to_jsonl(src, tmp_path / "bronze")

    lines = read_lines(tmp_path / "bronze" / "2025-01.jsonl")
    assert [line["ocid"] for line in lines] == ["ocds-5wno2w-A", "ocds-5wno2w-B"]
    assert report.written == 2
    assert report.rejected == 0


def test_keeps_full_release_and_accents(tmp_path: Path) -> None:
    src = write_zip(
        tmp_path / "2025-01.zip",
        [package(release(buyer={"name": "GAD MUNICIPAL DE MANTA", "region": "MANABÍ"}))],
    )

    zip_to_jsonl(src, tmp_path / "bronze")

    text = (tmp_path / "bronze" / "2025-01.jsonl").read_text(encoding="utf-8")
    assert "MANABÍ" in text
    assert read_lines(tmp_path / "bronze" / "2025-01.jsonl")[0]["buyer"]["name"] == (
        "GAD MUNICIPAL DE MANTA"
    )


def test_drops_duplicate_ocids(tmp_path: Path) -> None:
    src = write_zip(
        tmp_path / "2025-01.zip",
        [package(release("ocds-5wno2w-A")), package(release("ocds-5wno2w-A"))],
    )

    report = zip_to_jsonl(src, tmp_path / "bronze")

    assert report.written == 1
    assert report.duplicates == 1


def test_rejects_invalid_release_when_tolerated(tmp_path: Path) -> None:
    broken = release()
    del broken["ocid"]
    src = write_zip(tmp_path / "2025-01.zip", [package(release()), package(broken)])

    report = zip_to_jsonl(src, tmp_path / "bronze", max_reject_ratio=1.0)

    assert report.written == 1
    assert report.rejected == 1
    assert "ocid" in report.errors[0]


def test_fails_loudly_and_writes_nothing_when_too_many_errors(tmp_path: Path) -> None:
    broken = release(ocid="not-an-ocds-id")
    src = write_zip(tmp_path / "2025-01.zip", [package(release()), package(broken)])

    with pytest.raises(DataQualityError):
        zip_to_jsonl(src, tmp_path / "bronze")

    assert list((tmp_path / "bronze").iterdir()) == []


def test_rejects_file_that_is_not_an_array(tmp_path: Path) -> None:
    src = write_zip(tmp_path / "2025-01.zip", {"releases": []})

    with pytest.raises(DataQualityError, match="JSON array"):
        zip_to_jsonl(src, tmp_path / "bronze")
