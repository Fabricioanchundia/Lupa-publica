"""Download monthly OCDS bulk files published by SERCOP.

The SERCOP server is slow (~17 KB/s) and regenerates every month nightly,
so downloads must be resilient (timeouts, retries) and atomic.
"""

from __future__ import annotations

import logging
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BULK_URL = "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/download"
USER_AGENT = "lupa-publica/0.1 (+https://github.com/Fabricioanchundia/Lupa-publica)"
TIMEOUT = httpx.Timeout(300.0, connect=30.0)
FIRST_YEAR = 2015


class DownloadError(RuntimeError):
    """Raised when a monthly file cannot be downloaded."""


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
    return isinstance(exc, httpx.TransportError | zipfile.BadZipFile)


def download_month(
    month: Month,
    dest_dir: Path,
    *,
    client: httpx.Client | None = None,
    force: bool = False,
    retries: int = 3,
    backoff_seconds: float = 5.0,
) -> Path:
    """Download one month as ``<dest_dir>/<YYYY-MM>.zip`` and return its path.

    - Idempotent: an existing file is reused unless ``force`` is True.
    - Atomic: data goes to a ``.part`` file, renamed only when complete and valid.
    - Resilient: transport errors, 5xx responses and invalid ZIPs are retried.
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
    try:
        for attempt in range(1, retries + 1):
            try:
                with http.stream("GET", BULK_URL, params=bulk_params(month)) as response:
                    response.raise_for_status()
                    with partial.open("wb") as fh:
                        for chunk in response.iter_bytes():
                            fh.write(chunk)
                if not zipfile.is_zipfile(partial):
                    raise zipfile.BadZipFile(f"{month.label}: response is not a ZIP file")
                partial.replace(target)
                logger.info("%s downloaded (%d bytes)", month.label, target.stat().st_size)
                return target
            except Exception as exc:
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
