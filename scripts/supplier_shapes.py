"""Privacy-safe look at supplier identifiers in bronze.releases.

Prints only the SHAPE of each identifier (every digit replaced by "D") and
aggregate counts. It never prints a real RUC, cédula or supplier name.

SERCOP supplier ids look like ``<scheme>-<tax id>-<suffix>``, e.g. EC-RUC-<13 digits>-<n>.
Ecuadorian RUC, third digit: 0-5 natural person, 6 public entity, 9 private company.

Usage: uv run python scripts/supplier_shapes.py [path/to/lupa.duckdb]
"""

from __future__ import annotations

import sys

import duckdb

SUPPLIERS = r"""
    WITH awards AS (
        SELECT unnest(
            from_json(payload, '{"awards": [{"suppliers": [{"id": "VARCHAR"}]}]}').awards
        ) AS award
        FROM bronze.releases
    ),
    ids AS (SELECT unnest(award.suppliers).id AS supplier_id FROM awards)
    SELECT
        supplier_id,
        regexp_extract(supplier_id, '^([A-Z-]+)-[0-9]+-[0-9]+$', 1) AS scheme,
        regexp_extract(supplier_id, '^[A-Z-]+-([0-9]+)-[0-9]+$', 1) AS tax_id,
        regexp_extract(supplier_id, '^[A-Z-]+-[0-9]+-([0-9]+)$', 1) AS suffix
    FROM ids
"""

SHAPES_SQL = f"""
    SELECT regexp_replace(coalesce(supplier_id, '<null>'), '[0-9]', 'D', 'g') AS shape,
           count(*) AS awards
    FROM ({SUPPLIERS})
    GROUP BY 1 ORDER BY 2 DESC LIMIT 15
"""  # noqa: S608

TYPES_SQL = f"""
    SELECT
        coalesce(nullif(scheme, ''), '<unparsed>') AS scheme,
        CASE
            WHEN length(tax_id) <> 13 THEN 'tax id with ' || length(tax_id) || ' digits'
            WHEN substr(tax_id, 3, 1) IN ('0', '1', '2', '3', '4', '5') THEN 'natural person'
            WHEN substr(tax_id, 3, 1) = '6' THEN 'public entity'
            WHEN substr(tax_id, 3, 1) = '9' THEN 'private company'
            ELSE 'other third digit (' || substr(tax_id, 3, 1) || ')'
        END AS taxpayer_type,
        count(*) AS awards,
        count(DISTINCT tax_id) AS distinct_tax_ids
    FROM ({SUPPLIERS})
    GROUP BY 1, 2 ORDER BY 3 DESC
"""  # noqa: S608

STABILITY_SQL = f"""
    WITH pairs AS (SELECT DISTINCT tax_id, suffix FROM ({SUPPLIERS}) WHERE tax_id <> '')
    SELECT 'tax ids with more than one suffix' AS check_name,
           count(*) AS n
    FROM (SELECT tax_id FROM pairs GROUP BY 1 HAVING count(*) > 1)
    UNION ALL
    SELECT 'suffixes shared by more than one tax id', count(*)
    FROM (SELECT suffix FROM pairs GROUP BY 1 HAVING count(*) > 1)
    UNION ALL
    SELECT 'distinct tax ids', count(DISTINCT tax_id) FROM pairs
    UNION ALL
    SELECT 'distinct full supplier ids', count(*) FROM pairs
"""  # noqa: S608


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/lupa.duckdb"
    config = {"memory_limit": "1GB", "threads": "2"}
    with duckdb.connect(db_path, read_only=True, config=config) as con:
        print("== Supplier identifier shapes (digits hidden) ==")
        con.sql(SHAPES_SQL).show()
        print("\n== Suppliers by scheme and taxpayer type ==")
        con.sql(TYPES_SQL).show()
        print("\n== Is the suffix a stable supplier key? ==")
        con.sql(STABILITY_SQL).show()


if __name__ == "__main__":
    main()
