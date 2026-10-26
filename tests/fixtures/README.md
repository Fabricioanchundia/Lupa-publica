# Test fixtures

`bronze/2025-01.jsonl` holds 8 **synthetic** contracting processes in SERCOP's OCDS
format. CI loads them with `scripts/load_fixture.py` and runs `dbt build` on them, so
every dbt test (including the privacy test from ADR-0004) runs on every pull request.

- Every person and company is fictitious. Supplier and buyer ids use province code
  `00`, which does not exist in Ecuador, so they can never match a real cédula or RUC.
- The only real id is one public entity from `dbt/seeds/buyer_locations.csv`, used to
  test the manual location seed. It is a public institution, not a person.
- Each process covers an edge case: a natural person under two id schemes, a consortium
  (company + person), a public company as supplier, malformed and unparseable ids,
  an award of 0 (unknown amount), several awards in one process, a buyer without an
  address, and a process without awards.

If you add a case, keep it fictitious and add a test that would fail without it.
