"""Load the synthetic CI fixture (tests/fixtures/bronze) into a DuckDB file for dbt.

Usage: uv run python scripts/load_fixture.py [path/to/database.duckdb]
"""

from __future__ import annotations

import sys
from pathlib import Path

from lupa_publica.load import load_bronze

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bronze"


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/ci.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    report = load_bronze(db_path, FIXTURE_DIR)
    print(f"loaded {report.rows} fixture processes into {db_path}")


if __name__ == "__main__":
    main()
