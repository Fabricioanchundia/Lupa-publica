"""Download monthly OCDS bulk files published by SERCOP.

The SERCOP server is slow and unreliable: it closes connections, stalls, or
trickles data. Downloads are therefore resilient (timeouts, retries, a time
budget per attempt), resumable (HTTP Range requests) and atomic.
"""

from __future__ import annotations

import logging
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BULK_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/download"
USER_AGENT = "lupa-publica/0.1 (+https://github.com/Fabricioanchundia/Lupa-publica)"
TIMEOUT = httpx.Timeout(60.0, connect=30.0)
FIRST_YEAR = 2015
# A healthy download of the largest months (~20 MB) takes under 2 minutes.
MAX_ATTEMPT_SECONDS = 600.0
CONTENT_RANGE = re.compile(r"^bytes (\d+)-\d+/(\d+)$")


class DownloadError(RuntimeError):
    """Raised when a monthly file cannot be downloaded."""


class SlowDownloadError(RuntimeError):
    """An attempt exceeded its time budget because the server is trickling data."""


class ResumeError(RuntimeError):
    """The server answered a resume request with a different file or range."""


@dataclass(frozen=True, order=True)
class Month:
    """A calendar month of SERCOP data."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year < FIRST_YEAR:
            raise ValueError(f"SERCOP OCDS data starts in {FIRST_YEAR}, got {self.year}")
        if not 1 <= self.month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {self.month}")

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass
class _Progress:
    """Size of the file announced by the server, needed to resume safely."""

    total: int | None = None


def bulk_params(month: Month) -> dict[str, str]:
    """Query parameters of the bulk download endpoint for one month."""
    return {
        "type": "json",
        "year": str(month.year),
        "month": f"{month.month:02d}",
        "method": "all",
    }


def _is_retryable(exc: Exception) -> bool:
    """Network failures, 5xx responses and broken ZIPs are temporary; 4xx are not."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(
        exc, httpx.TransportError | zipfile.BadZipFile | SlowDownloadError | ResumeError
    )


def _parse_content_range(header: str) -> tuple[int, int]:
    """``bytes 100-199/1000`` -> (start=100, total=1000)."""
    match = CONTENT_RANGE.match(header.strip())
    if match is None:
        raise ResumeError(f"unexpected Content-Range header: {header!r}")
    return int(match.group(1)), int(match.group(2))


def _fetch(
    http: httpx.Client,
    month: Month,
    partial: Path,
    progress: _Progress,
    started: float,
    max_attempt_seconds: float,
) -> None:
    """Write (or append) the server response to ``partial``."""
    offset = partial.stat().st_size if partial.exists() else 0
    resume = offset > 0 and progress.total is not None
    headers = {"Accept-Encoding": "identity"}
    if resume:
        headers["Range"] = f"bytes={offset}-"
        logger.info("%s resuming from byte %d of %s", month.label, offset, progress.total)

    with http.stream("GET", BULK_URL, params=bulk_params(month), headers=headers) as response:
        response.raise_for_status()
        if resume and response.status_code == 206:
            start, total = _parse_content_range(response.headers.get("Content-Range", ""))
            if start != offset or total != progress.total:
                raise ResumeError(f"{month.label}: the file changed on the server")
            mode = "ab"
        else:
            mode = "wb"
            length = response.headers.get("Content-Length", "")
            progress.total = int(length) if length.isdigit() else None

        with partial.open(mode) as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)
                if time.monotonic() - started > max_attempt_seconds:
                    raise SlowDownloadError(
                        f"{month.label}: attempt took longer than {max_attempt_seconds:.0f}s"
                    )


def _validate_zip(path: Path, month: Month) -> None:
    """Check the ZIP structure and the CRC of every member (catches bad resumes)."""
    with zipfile.ZipFile(path) as zf:
        bad_member = zf.testzip()
    if bad_member is not None:
        raise zipfile.BadZipFile(f"{month.label}: corrupt member {bad_member}")


def download_month(
    month: Month,
    dest_dir: Path,
    *,
    client: httpx.Client | None = None,
    force: bool = False,
    retries: int = 5,
    backoff_seconds: float = 5.0,
    max_attempt_seconds: float = MAX_ATTEMPT_SECONDS,
) -> Path:
    """Download one month as ``<dest_dir>/<YYYY-MM>.zip`` and return its path.

    - Idempotent: an existing file is reused unless ``force`` is True.
    - Atomic: data goes to a ``.part`` file, renamed only when complete and valid.
    - Resumable: after a cut, the next attempt asks only for the missing bytes.
    - Resilient: transport errors, 5xx responses, invalid ZIPs and attempts slower
      than ``max_attempt_seconds`` are retried.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"{month.label}.zip"
    if target.exists() and not force:
        logger.info("%s already downloaded, skipping", month.label)
        return target

    own_client = client is None
    http = client or httpx.Client(
        timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )
    partial = target.with_name(target.name + ".part")
    partial.unlink(missing_ok=True)
    progress = _Progress()
    try:
        for attempt in range(1, retries + 1):
            started = time.monotonic()
            try:
                size = partial.stat().st_size if partial.exists() else 0
                if progress.total is None or size < progress.total:
                    _fetch(http, month, partial, progress, started, max_attempt_seconds)
                _validate_zip(partial, month)
                partial.replace(target)
                logger.info("%s downloaded (%d bytes)", month.label, target.stat().st_size)
                return target
            except Exception as exc:
                if isinstance(exc, zipfile.BadZipFile | ResumeError):
                    partial.unlink(missing_ok=True)  # never resume on top of bad data
                    progress.total = None
                if not _is_retryable(exc) or attempt == retries:
                    raise DownloadError(f"could not download {month.label}: {exc}") from exc
                wait = backoff_seconds * attempt
                logger.warning(
                    "%s attempt %d/%d failed (%s); retrying in %.0fs",
                    month.label,
                    attempt,
                    retries,
                    exc,
                    wait,
                )
                time.sleep(wait)
    finally:
        partial.unlink(missing_ok=True)
        if own_client:
            http.close()
    raise DownloadError(f"could not download {month.label}: no attempts were made")
