# ADR-0002: Store the bronze layer as JSONL files loaded into DuckDB

- **Status:** Accepted
- **Date:** 2026-10-26

## Context
- Each monthly file is a JSON array of release packages, each with exactly one compiled release. We observed 30,460 processes in 4 months with 0 structural errors.
- Requirements:
  - keep the data exactly as published;
  - validate its structure;
  - query it with SQL;
  - run on a 16 GB laptop and on free CI runners;
  - stay compatible with Open Contracting Partnership tools.

## Decision
1. Validate every release with a minimal Pydantic model (`ocid` with the SERCOP prefix, `id`, `date`, `tag`). **A month fails if more than 1% of its releases are invalid**, and nothing is written for it.
2. Write one compiled release per line in `data/bronze/releases/YYYY-MM.jsonl`. This is the input format of OCP Cardinal.
3. Rebuild `bronze.releases` in a single-file DuckDB database (`data/lupa.duckdb`) from all JSONL files on every run:
   - a few typed columns: `ocid`, `release_id`, `release_date`, `source_month`, `loaded_at`;
   - the full release as a JSON column (`payload`).
4. No database server.

## Consequences
- ✅ **Idempotent:** rebuilding produces the same table.
- ✅ **Small and fast:** 91 MB of JSONL became a 7.6 MB database.
- ✅ **Cardinal can read the bronze files directly** to cross-check our risk indicators.
- ✅ **New fields added by SERCOP do not break loading;** they stay in `payload`.
- ⚠️ The full rebuild grows with history. Revisit (incremental load per month) if it takes more than a few minutes.
- ⚠️ Queries over the JSON payload are slower than over typed columns. Silver models in dbt (Phase 4) will flatten the fields we need.

## Alternatives considered
- **Parquet directly:** requires fixing a schema up front, before we know the data well.
- **PostgreSQL:** a server to operate and pay for. Too much for an analytical workload.
- **pandas in memory:** limited by RAM as history grows.
