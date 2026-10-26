import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from lupa_publica.extract import DownloadError, Month, download_month


def make_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("releases_2025_enero.json", "[]")
    return buffer.getvalue()


def client_with(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_month_with_expected_params(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["year"] == "2025"
        assert request.url.params["month"] == "01"
        assert request.url.params["type"] == "json"
        return httpx.Response(200, content=make_zip())

    path = download_month(Month(2025, 1), tmp_path, client=client_with(handler))

    assert path == tmp_path / "2025-01.zip"
    assert zipfile.is_zipfile(path)


def test_skips_existing_file_without_network(tmp_path: Path) -> None:
    existing = tmp_path / "2025-01.zip"
    existing.write_bytes(make_zip())

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network must not be called")

    assert download_month(Month(2025, 1), tmp_path, client=client_with(handler)) == existing


def test_retries_on_server_error(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=make_zip())

    download_month(Month(2025, 1), tmp_path, client=client_with(handler), backoff_seconds=0)

    assert calls == 2


def test_does_not_retry_client_errors(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    with pytest.raises(DownloadError):
        download_month(Month(2025, 1), tmp_path, client=client_with(handler), backoff_seconds=0)

    assert calls == 1


def test_invalid_zip_leaves_no_files(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>Error del servidor</html>")

    with pytest.raises(DownloadError):
        download_month(
            Month(2025, 1), tmp_path, client=client_with(handler), retries=2, backoff_seconds=0
        )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(("year", "month"), [(2014, 1), (2025, 0), (2025, 13)])
def test_month_rejects_invalid_values(year: int, month: int) -> None:
    with pytest.raises(ValueError):
        Month(year, month)
