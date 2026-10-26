# Data Exploration — SERCOP OCDS

_Last updated: 2026-10-26_

## Sources
| Source | Endpoint | Notes |
|---|---|---|
| Search API | `/PLATAFORMA/api/search_ocds` | `year` and `search` (min 3 chars) required; `page`, `buyer`, `supplier` optional. ~10 results per page. |
| Record API | `/PLATAFORMA/api/record?ocid=<ocid>` | Full detail of one process. |
| Bulk download | `/PLATAFORMA/download?type=json&year=YYYY&month=MM&method=all` | ZIP per month. **To be explored next.** |

Base URL: `https://datosabiertos.compraspublicas.gob.ec`
License: CC BY 3.0 EC. Attribution: Servicio Nacional de Contratación Pública (SERCOP).

## Findings
1. **Official API docs are outdated.** The search response actually returns `id, ocid, year, month, method, internal_type, locality, region, suppliers, buyer, amount, budget, date, title, description`. Documented fields like `buyerName` and `single_provider` are not present.
2. **The record endpoint returns a release package** (top-level `releases`), not a record package (`records`) as documented.
3. **One compiled release per process** (`id` ends in `-compiled`), so no need to merge releases ourselves.
4. **Numbers come as strings in the search API** (`"amount": "0.000000"`, `"budget": "29915"`) but as numbers in the record API. Explicit casting is required.
5. **`amount = 0` does not mean zero cost.** In the explored example, the process only had `planning` and `tender` tags (not awarded yet). Zero amounts must be treated as missing, not as real values.
6. **`awards` and `contracts` may be absent.** All downstream fields must be nullable.
7. **Identifier inconsistencies:** buyer IDs appear as `EC-RUC-<ruc>-<code>` while the docs show `EC_RUC-...`. Needs normalization.
8. **Items carry CPC classification codes**, which will allow price comparisons within the same category.
9. **Geography is available** (`region`, `locality`), enabling province and canton dashboards. Values lack accents (`MANABI`) and need normalization.
10. **Parties can be natural persons** (e.g. individual consultants), which brings personal-data obligations.
11. **Network reliability:** use timeouts and retries; other developers report one of the domain's addresses hangs.

## Implications for the project
- The pipeline must **validate the schema** of incoming data instead of assuming the documented one.
- **Missing vs zero:** monetary zeros are converted to `NULL` unless the stage confirms a real value.
- **Red flags must be procedure-aware.** "Single bidder" only applies to competitive procedures; direct contracting invites one party by design.
- **Privacy (LOPDP):** natural persons are handled with data minimization. Exact rules will be defined in an ADR.

## Open questions
- What does the bulk ZIP contain, and how large is one month?
- How complete are `awards` and `contracts` across procedure types and years?
- What does the numeric suffix in buyer IDs (e.g. `-2668`) represent?

---

## Bulk download findings (January 2025 sample)
- **Format:** ZIP (~1.1 MB) containing a single JSON file `releases_<YYYY>_<month in Spanish>.json` (~13.6 MB uncompressed).
- **Speed:** ~65 s per month (~17 KB/s). The server is slow, so avoid full re-downloads.
- **Regenerated nightly:** the January 2025 file was dated 2026-10-25, so past months keep changing (awards and contracts are added later).
- **Structure:** JSON array of release packages, each with exactly one compiled release. Same shape as the record API, so one parser can serve both sources.
- **Volume:** 2,210 processes, 2,210 unique OCIDs (no duplicates). About 163 MB/year uncompressed, consistent with the OCP data registry.

## Profile (January 2025)
- **Stages:** 1,953 `tender,award,contract`; 87 reach `implementation`; 45 `planning` only.
- **Standard method (`tender.procurementMethod`):** selective 1,534 · direct 508 · open 117 · limited 6. The 45 planning-only processes have no tender, so 2,165 + 45 = 2,210 ✅.
- **Electronic catalogue purchases are about 77%** of processes and are mapped by SERCOP as `selective`.
- **Competitive procedures are only about 160** (reverse auction, menor cuantía, cotización, short list, insurance tender).
- **`procurementMethodDetails` mixes the procedure type and the framework agreement name.** Must be split.
- **Buyer location** is in `parties[role=buyer].address.region/locality`; 14 buyers have no region.
- **Manabí is the 2nd province by number of processes** (280; Pichincha 316).

## Coverage gaps (limitations)
- **Ínfima cuantía is not present** (API search returns 0).
- **No emergency procedure type was found.** The keyword "emergencia" only matches item descriptions, not procedure types.
- **Guayas looks under-represented** (65 processes vs 316 in Pichincha). Inconclusive; needs reconciliation against portal totals.

## Decisions derived
- **Rolling window reload:** each daily run re-downloads the last N months (N = 6 initially) and replaces them.
- **"Single bidder" applies only to competitive procedures.**
- **"Emergency overuse" and "contract splitting" are not computed from this source.** Documented as methodology limitations.
- **Keyword matches are never used as classifications.**
- **Addresses of natural-person suppliers are not stored** (LOPDP data minimization).
