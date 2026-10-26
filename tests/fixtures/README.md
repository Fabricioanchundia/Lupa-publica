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
- Items: repeated CPC codes, a unit name with spaces and lowercase, a missing unit,
  a price of 0 and a quantity of 0, a fractional price, and a large purchase
  (120,000 units at 450,000) that overflows DECIMAL(18) if line amounts are not widened.
- Tender: one bidder, three bidders, zero bidders, and tender periods of 3, 5 and 10 days.

If you add a case, keep it fictitious and add a test that would fail without it.
