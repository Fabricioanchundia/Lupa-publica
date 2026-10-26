# ADR-0001: Ingest SERCOP data from monthly bulk files with a rolling window

- **Status:** Accepted
- **Date:** 2026-10-26

## Context
- SERCOP publishes OCDS data through a search API, a record API and monthly bulk ZIP files.
- The APIs return about 10 results per page and their documentation is outdated (see `docs/data-exploration.md`). The bulk files contain every process of a month as compiled releases.
- **Past months are regenerated nightly:** the January 2025 file was dated 2026-10-25, because processes receive awards and contracts after they start.
- **The server is unreliable.** On 2026-10-26 we observed two failure modes in a single run:
  - a download cut after 110 KB of 9.7 MB (connection closed);
  - a download that stalled for 5 minutes without sending data (silent hang).

  Retries succeeded in both cases; the second attempt took 9 seconds.

## Decision
1. The pipeline uses **only the monthly bulk files**. The APIs are used for manual exploration.
2. Two modes:
   - `lupa ingest --months N` (nightly): **re-downloads the last N months** (default 6), because they keep changing.
   - `lupa backfill --from YYYY-MM --to YYYY-MM` (one-off): loads history and **skips files that already exist**.
3. Downloads are resilient:
   - timeouts of 30 s to connect and 60 s without receiving data;
   - up to 5 attempts with linear backoff;
   - retries only on network errors, HTTP 5xx and invalid ZIPs (never on 4xx);
   - atomic writes (`.part` file renamed only when complete);
   - the ZIP is validated before it is accepted.
4. **One failing month does not stop the run**, but the run exits with code 1 so the scheduler raises an alert.

## Consequences
- ✅ Recent changes are captured, and the nightly cost is bounded (about 6 files).
- ✅ Partial or corrupt files never reach the data.
- ⚠️ Changes to processes older than N months are missed until history is reloaded. A periodic full refresh will be decided in a later ADR.
- ⚠️ Run time depends on SERCOP availability.

## Alternatives considered
- **Paginating the search API:** too many requests, and its response format differs from the documentation.
- **OCP Kingfisher Collect:** robust, but adds a Scrapy-based stack. Kept as a reference implementation.
