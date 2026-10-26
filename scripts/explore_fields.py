"""Explore which fields SERCOP actually publishes inside tender, awards, contracts and parties.

Usage: uv run python scripts/explore_fields.py [path/to/lupa.duckdb]

Reads a random sample of processes in small batches and counts field names in Python.
Only field NAMES and a few categorical values are printed: never names, RUCs or contacts.
(Doing this in SQL ran out of memory: awards can carry hundreds of items each.)
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter

import duckdb

DB = sys.argv[1] if len(sys.argv) > 1 else "data/lupa.duckdb"
SAMPLE_SIZE = 5000

fields: dict[str, Counter[str]] = {}
values: dict[str, Counter[str]] = {}
items_per_award: list[int] = []


def count_keys(where: str, obj: object) -> None:
    if isinstance(obj, dict):
        fields.setdefault(where, Counter()).update(obj.keys())


def count_value(where: str, value: object) -> None:
    values.setdefault(where, Counter())[str(value)] += 1


con = duckdb.connect(DB, read_only=True, config={"memory_limit": "1GB", "threads": 2})
cursor = con.execute(f"SELECT payload FROM bronze.releases USING SAMPLE {SAMPLE_SIZE} ROWS")  # noqa: S608

while batch := cursor.fetchmany(500):
    for (payload,) in batch:
        release = json.loads(payload)
        tender = release.get("tender") or {}
        count_keys("tender.tenderPeriod", tender.get("tenderPeriod"))
        for tenderer in tender.get("tenderers") or []:
            count_keys("tender.tenderers[]", tenderer)
        count_value("tender.competitive", tender.get("competitive"))
        for award in release.get("awards") or []:
            count_value("awards[].status", award.get("status"))
            items = award.get("items") or []
            items_per_award.append(len(items))
            for item in items:
                count_keys("awards[].items[]", item)
                unit = item.get("unit") or {}
                count_keys("awards[].items[].unit", unit)
                count_keys("awards[].items[].unit.value", unit.get("value"))
                count_keys("awards[].items[].classification", item.get("classification"))
        for contract in release.get("contracts") or []:
            count_value("contracts[].status", contract.get("status"))
        for party in release.get("parties") or []:
            count_keys("parties[].identifier", party.get("identifier"))

print(f"== Fields inside key objects (sample of {SAMPLE_SIZE:,} processes) ==")
for where, counter in fields.items():
    print(f"\n{where}")
    for name, n in counter.most_common():
        print(f"   {name:<20} {n:>9,}")

print("\n== Values of categorical fields ==")
for where, counter in values.items():
    print(f"\n{where}")
    for value, n in counter.most_common():
        print(f"   {value:<20} {n:>9,}")

if items_per_award:
    ordered = sorted(items_per_award)
    print("\n== Items per award ==")
    print(f"   awards: {len(ordered):,}")
    print(f"   mean: {statistics.mean(ordered):.1f}   median: {statistics.median(ordered)}")
    print(f"   p99: {ordered[int(len(ordered) * 0.99) - 1]}   max: {ordered[-1]}")
