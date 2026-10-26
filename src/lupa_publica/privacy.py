"""Pseudonymization of personal identifiers (see docs/adr/0004-supplier-privacy.md).

Natural persons are identified by their cédula inside the RUC. We replace it with a
keyed hash (HMAC-SHA256): stable, so the same person can still be counted, but not
reversible without the secret key. A plain SHA-256 would NOT be safe: there are only a
few million possible cédulas, so anyone could hash them all and look ours up.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping

KEY_ENV = "LUPA_PSEUDONYM_KEY"
MIN_KEY_BYTES = 32


class MissingKeyError(RuntimeError):
    """The pseudonymization key is not configured or is too weak."""


def load_key(environ: Mapping[str, str] = os.environ) -> bytes:
    """Read the secret key (hex) from the environment and validate it."""
    value = environ.get(KEY_ENV, "").strip()
    if not value:
        raise MissingKeyError(
            f"{KEY_ENV} is not set. Generate one with: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise MissingKeyError(f"{KEY_ENV} must be a hex string") from exc
    if len(key) < MIN_KEY_BYTES:
        raise MissingKeyError(f"{KEY_ENV} must be at least {MIN_KEY_BYTES} bytes (64 hex chars)")
    return key


def pseudonymize(value: str, key: bytes) -> str:
    """Stable, non-reversible pseudonym for ``value`` (64 hex characters)."""
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
