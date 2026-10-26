-- One row per contracting process, with the fields we use most, extracted once
-- from the raw JSON. Values are cleaned but not interpreted: no risk logic here.
--
-- Performance note: from_json parses each release ONCE into a struct that keeps
-- only the fields listed below. Extracting fields one by one with ->> re-parses
-- the whole document for every column and ran out of memory on 24 months of data.

with releases as (
    select
        ocid,
        source_month,
        release_date,
        from_json(payload, '{
            "tag": ["VARCHAR"],
            "buyer": {"id": "VARCHAR", "name": "VARCHAR"},
            "parties": [{"roles": ["VARCHAR"], "address": {"region": "VARCHAR", "locality": "VARCHAR"}}],
            "tender": {
                "title": "VARCHAR",
                "procurementMethod": "VARCHAR",
                "procurementMethodDetails": "VARCHAR",
                "value": {"amount": "VARCHAR", "currency": "VARCHAR"},
                "numberOfTenderers": "VARCHAR",
                "tenderers": [{"id": "VARCHAR"}],
                "tenderPeriod": {"startDate": "VARCHAR", "endDate": "VARCHAR", "durationInDays": "VARCHAR"}
            },
            "awards": [{"id": "VARCHAR"}],
            "contracts": [{"id": "VARCHAR"}]
        }') as release
    from {{ source('bronze', 'releases') }}
),

parsed as (
    select
        ocid,
        source_month,
        release_date,
        release.tag as tags,
        release.buyer.id as buyer_id,
        trim(release.buyer.name) as buyer_name,
        -- The buyer's address lives in the parties list, not in the buyer object.
        list_filter(
            release.parties, lambda party: list_contains(party.roles, 'buyer')
        )[1] as buyer_party,
        release.tender.procurementMethod as procurement_method,
        trim(release.tender.procurementMethodDetails) as procurement_method_details,
        trim(release.tender.title) as tender_title,
        try_cast(release.tender.value.amount as decimal(18, 2)) as tender_amount_raw,
        release.tender.value.currency as tender_currency,
        -- Only counts: tenderer ids can be natural persons (ADR-0004) and are not needed here.
        try_cast(release.tender.numberOfTenderers as integer) as number_of_tenderers,
        len(release.tender.tenderers) as tenderer_list_count,
        try_cast(release.tender.tenderPeriod.startDate as timestamptz) as tender_period_start,
        try_cast(release.tender.tenderPeriod.endDate as timestamptz) as tender_period_end,
        try_cast(release.tender.tenderPeriod.durationInDays as integer) as tender_duration_days,
        coalesce(len(release.awards), 0) as award_count,
        coalesce(len(release.contracts), 0) as contract_count
    from releases
)

select
    ocid,
    source_month,
    release_date,
    tags,
    buyer_id,
    buyer_name,
    nullif(trim(buyer_party.address.region), '') as buyer_region,
    nullif(trim(buyer_party.address.locality), '') as buyer_locality,
    procurement_method,
    procurement_method_details,
    tender_title,
    -- SERCOP publishes 0 when the amount is unknown: treat it as missing, not as free.
    case when tender_amount_raw > 0 then tender_amount_raw end as tender_amount,
    tender_currency,
    number_of_tenderers,
    tenderer_list_count,
    tender_period_start,
    tender_period_end,
    tender_duration_days,
    award_count,
    contract_count,
    award_count > 0 as has_award,
    contract_count > 0 as has_contract
from parsed
