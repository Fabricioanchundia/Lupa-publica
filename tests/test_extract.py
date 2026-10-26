import io
import zipfile
from collections.abc import Callable, Iterator
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


class ChunkedStream(httpx.SyncByteStream):
    """Sends the body in two pieces, so a slow attempt is cut halfway."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self) -> Iterator[bytes]:
        middle = len(self.data) // 2
        yield self.data[:middle]
        yield self.data[middle:]


def test_gives_up_on_attempts_that_are_too_slow(tmp_path: Path) -> None:
    full = make_zip()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if "Range" in request.headers:
            start = int(request.headers["Range"].removeprefix("bytes=").rstrip("-"))
            return httpx.Response(
                206,
                headers={"Content-Range": f"bytes {start}-{len(full) - 1}/{len(full)}"},
                stream=ChunkedStream(full[start:]),
            )
        return httpx.Response(
            200, headers={"Content-Length": str(len(full))}, stream=ChunkedStream(full)
        )

    with pytest.raises(DownloadError, match="longer than"):
        download_month(
            Month(2025, 1),
            tmp_path,
            client=client_with(handler),
            retries=2,
            backoff_seconds=0,
            max_attempt_seconds=-1,
        )

    assert calls == 2
    assert list(tmp_path.iterdir()) == []


class CutStream(httpx.SyncByteStream):
    """Sends part of the body, then drops the connection like the SERCOP server."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self) -> Iterator[bytes]:
        yield self.data
        raise httpx.RemoteProtocolError("peer closed connection")


def big_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("releases_2025_enero.json", "[" + ",".join(["{}"] * 2000) + "]")
    return buffer.getvalue()


def test_resumes_from_the_byte_where_the_connection_was_cut(tmp_path: Path) -> None:
    full = big_zip()
    half = len(full) // 2
    ranges: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ranges.append(request.headers.get("Range"))
        if "Range" not in request.headers:
            return httpx.Response(
                200, headers={"Content-Length": str(len(full))}, stream=CutStream(full[:half])
            )
        return httpx.Response(
            206,
            headers={"Content-Range": f"bytes {half}-{len(full) - 1}/{len(full)}"},
            content=full[half:],
        )

    path = download_month(Month(2025, 1), tmp_path, client=client_with(handler), backoff_seconds=0)

    assert ranges == [None, f"bytes={half}-"]
    assert path.read_bytes() == full


def test_starts_over_when_server_ignores_the_range(tmp_path: Path) -> None:
    full = big_zip()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                headers={"Content-Length": str(len(full))},
                stream=CutStream(full[: len(full) // 3]),
            )
        return httpx.Response(200, content=full)

    path = download_month(Month(2025, 1), tmp_path, client=client_with(handler), backoff_seconds=0)

    assert calls == 2
    assert path.read_bytes() == full


def test_starts_over_when_the_file_changed_on_the_server(tmp_path: Path) -> None:
    old, new = big_zip(), make_zip()
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Range"))
        if len(seen) == 1:
            return httpx.Response(
                200, headers={"Content-Length": str(len(old))}, stream=CutStream(old[:100])
            )
        if "Range" in request.headers:
            return httpx.Response(
                206,
                headers={"Content-Range": f"bytes 100-{len(new) - 1}/{len(new)}"},
                content=new[100:],
            )
        return httpx.Response(200, content=new)

    path = download_month(Month(2025, 1), tmp_path, client=client_with(handler), backoff_seconds=0)

    assert seen == [None, "bytes=100-", None]
    assert path.read_bytes() == new
