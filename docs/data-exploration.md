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
