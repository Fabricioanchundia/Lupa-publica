# ADR-0004: Pseudonymize suppliers who are natural persons

- **Status:** Accepted
- **Date:** 2026-10-26

## Context
- Every award names its suppliers. SERCOP ids look like `<scheme>-<tax id>-<registry suffix>`, e.g. `EC-RUC-<13 digits>-<n>` (explored with `scripts/supplier_shapes.py`, which prints only id shapes and counts).
- The third digit of a 13-digit RUC gives the taxpayer type: 0-5 natural person (the RUC is their cédula + `001`), 6 public entity, 9 private company.
- In 24 months (342,282 processes): **15,266 of 23,950 suppliers (64%) are natural persons**, with about 81,000 awards. Companies win 75% of the awards.
- About 2,000 awards have tax ids of 14 or 15 digits and 10 have no parseable id. We cannot tell whether these are persons.
- The registry suffix is almost 1:1 with the tax id (1 exception in 23,950), but the tax id is the real-world identity, so it is the key.
- SERCOP data is public by law. Lupa Pública adds something SERCOP does not: **risk signals**. Showing a named person next to a red flag can harm them over a statistical signal that may be wrong. Ecuador's personal data law (LOPDP) requires data minimization and proportionality.

## Decision
- **Bronze** (raw, local, never published) keeps the data exactly as received.
- **Silver** (`stg_award_suppliers`):
  - private companies and public entities keep their **RUC and name**;
  - natural persons get `supplier_key = HMAC-SHA256(secret key, tax id)` and **no name**;
  - ids we cannot classify (`unknown`) are treated as personal: pseudonym if there is a tax id, no name.
  - The raw id and the cédula are never written to silver or later layers.
- The HMAC is a Python function registered in DuckDB by a dbt-duckdb plugin (`lupa_publica.dbt_plugin`), because DuckDB has no HMAC. The key comes from `LUPA_PSEUDONYM_KEY` (64 hex characters), never from SQL, so it is not in compiled SQL, logs or the repository.
- A dbt test (`assert_no_personal_identifiers`) fails the build if any natural person keeps a name or a non-pseudonymized id.
- **Public outputs** (gold, web) show companies by name and RUC, and natural persons only as `Natural person #<first characters of the pseudonym>`. Every row keeps its `ocid`, so anyone can verify a case at the source (SERCOP) without Lupa Pública republishing identities.

## Consequences
- ✅ Supplier concentration and other indicators still work: the same person always gets the same key.
- ✅ A leaked silver table or dashboard does not expose cédulas or names of persons.
- ✅ The privacy rule is tested on every build, not just documented.
- ⚠️ The key must be kept safe and stable (password manager now, CI secret later). A new key changes every pseudonym; old public links to a pseudonym would break.
- ⚠️ Pseudonymized data is **still personal data** under the LOPDP (it is not anonymous): silver stays private and access-controlled.
- ⚠️ DuckDB Python functions need `numpy`, now a direct dependency.
- ⚠️ Sole proprietors appear as natural persons, even when they act like small businesses. This is the conservative choice.

## Alternatives considered
- **Show everyone by name, as SERCOP does:** combined with risk signals, disproportionate harm to individuals.
- **Plain SHA-256 of the cédula:** not safe. There are only a few million possible cédulas, so anyone can hash them all and reverse the table in minutes.
- **Drop natural persons entirely:** we would lose 64% of suppliers and could not detect concentration toward individuals.
- **Hash in SQL with a key from dbt `env_var()`:** the key would end up in compiled SQL and logs under `target/`.
