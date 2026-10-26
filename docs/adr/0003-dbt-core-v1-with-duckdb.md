# ADR-0003: Use dbt Core v1 (dbt-duckdb) for transformations

- **Status:** Accepted
- **Date:** 2026-10-26

## Context
- We need SQL transformations from the bronze JSON into typed silver tables, with data tests and documentation.
- dbt v2 (Rust engine) is now the default for new installs and ships its own pinned DuckDB driver.
- The pipeline (Python, DuckDB 2.0) and dbt write to the same file, `data/lupa.duckdb`.

## Decision
- Use **dbt Core 1.12 with dbt-duckdb**, installed and locked with uv, so dbt and the pipeline use **the same DuckDB version** on the same database file.
- CI runs `dbt parse` and `dbt parse --use-v2-parser` on every PR, so the project stays compatible with v2.
- Parse each release **once** with `from_json` into a struct of the needed fields. Extracting fields one by one with `->>` re-parsed the document per column and ran out of memory on 24 months (342,282 processes).

## Consequences
- ✅ One DuckDB version for the whole project, reproducible from `uv.lock`.
- ✅ `stg_processes` builds in about 2 seconds, and 7 data tests pass on real data.
- ⚠️ We do not get v2 features yet (static analysis, column-level lineage). Revisit when v2's bundled DuckDB matches ours, or when we need those features.

## Alternatives considered
- **dbt v2 with the built-in adapter:** a different DuckDB version from the pipeline on the same file, no extension loading with the bundled driver, and very new.
- **Plain SQL scripts run from Python:** no tests, no lineage, no documentation.
