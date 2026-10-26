-- One row per award (adjudicación). A process can have several awards.
-- Suppliers are modelled separately in stg_award_suppliers (privacy rules apply there).

with awards as (
    select
        ocid,
        source_month,
        unnest(from_json(payload, '{
            "awards": [{
                "id": "VARCHAR",
                "status": "VARCHAR",
                "date": "VARCHAR",
                "value": {"amount": "VARCHAR", "currency": "VARCHAR"},
                "suppliers": [{"id": "VARCHAR"}]
            }]
        }').awards) as award
    from {{ source('bronze', 'releases') }}
)

select
    ocid,
    source_month,
    award.id as award_id,
    award.status as award_status,
    try_cast(award.date as timestamptz) as award_date,
    -- Same rule as tender_amount: 0 means unknown, not free.
    case
        when try_cast(award.value.amount as decimal(18, 2)) > 0
            then try_cast(award.value.amount as decimal(18, 2))
    end as award_amount,
    award.value.currency as award_currency,
    coalesce(len(award.suppliers), 0) as supplier_count
from awards
