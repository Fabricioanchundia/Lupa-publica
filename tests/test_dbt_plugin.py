import duckdb
import pytest

from lupa_publica.dbt_plugin import Plugin
from lupa_publica.privacy import KEY_ENV, pseudonymize

KEY_HEX = "ab" * 32


def connect_with_plugin() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    Plugin(name="dbt_plugin", plugin_config={}).configure_connection(con)
    return con


def test_registers_pseudonymize_in_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY_ENV, KEY_HEX)
    con = connect_with_plugin()

    row = con.execute("SELECT pseudonymize('1712345678001'), pseudonymize(NULL)").fetchone()

    assert row == (pseudonymize("1712345678001", bytes.fromhex(KEY_HEX)), None)


def test_fails_only_when_used_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(KEY_ENV, raising=False)
    con = connect_with_plugin()

    assert con.execute("SELECT 1").fetchone() == (1,)
    with pytest.raises(duckdb.Error, match=KEY_ENV):
        con.execute("SELECT pseudonymize('1712345678001')")
