"""dbt-duckdb plugin: registers the SQL function ``pseudonymize(text)``.

DuckDB has no HMAC function, so we register a Python one. The key is read from the
environment here, so it never appears in compiled SQL, dbt logs or the repository.
Configured in dbt/profiles.yml under ``plugins``.
"""

from __future__ import annotations

from typing import Any

import duckdb
from dbt.adapters.duckdb.plugins import BasePlugin

from lupa_publica.privacy import MissingKeyError, load_key, pseudonymize


class Plugin(BasePlugin):
    def configure_connection(self, conn: duckdb.DuckDBPyConnection) -> None:
        try:
            key, problem = load_key(), ""
        except MissingKeyError as exc:
            key, problem = b"", str(exc)

        def _pseudonymize(value: str) -> str:
            # Fail only when a model actually needs the key, so models that
            # do not use it (and `dbt parse` in CI) work without the secret.
            if not key:
                raise MissingKeyError(problem)
            return pseudonymize(value, key)

        conn.create_function(
            "pseudonymize", _pseudonymize, [duckdb.sqltype("VARCHAR")], duckdb.sqltype("VARCHAR")
        )

    def initialize(self, plugin_config: dict[str, Any]) -> None:
        """No configuration needed; the key comes from the environment."""
