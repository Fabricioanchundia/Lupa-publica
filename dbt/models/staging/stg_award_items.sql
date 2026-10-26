-- One row per item of an award: what was bought, how much, and at what unit price.
-- Basis for the "unusual unit price" indicator (compare prices of the same CPC code
-- and the same unit). Item descriptions are free text and are left out on purpose:
-- they are large and we compare by CPC code instead.

with awards as (
    select
        ocid,
        source_month,
        unnest(from_json(payload, '{
            "awards": [{
                "id": "VARCHAR",
                "items": [{
                    "quantity": "VARCHAR",
                    "unit": {"name": "VARCHAR", "value": {"amount": "VARCHAR", "currency": "VARCHAR"}},
                    "classification": {"id": "VARCHAR", "scheme": "VARCHAR"}
                }]
            }]
        }').awards) as award
    from {{ source('bronze', 'releases') }}
),

items as (
    select
        ocid,
        source_month,
        award.id as award_id,
        -- Position of the item inside the award (1, 2, ...): item ids are not reliable.
        generate_subscripts(award.items, 1) as item_index,
        unnest(award.items) as item
    from awards
),

parsed as (
    select
        ocid,
        source_month,
        award_id,
        item_index,
        nullif(trim(item.classification.id), '') as cpc_code,
        item.classification.scheme as classification_scheme,
        try_cast(item.quantity as decimal(18, 4)) as quantity,
        nullif(upper(trim(item.unit.name)), '') as unit_name,
        try_cast(item.unit.value.amount as decimal(18, 4)) as unit_price_raw,
        item.unit.value.currency as currency
    from items
)

select
    ocid,
    source_month,
    award_id,
    item_index,
    cpc_code,
    classification_scheme,
    quantity,
    unit_name,
    -- 0 means unknown, as with every other amount.
    case when unit_price_raw > 0 then unit_price_raw end as unit_price,
    currency,
    -- Multiply in DECIMAL(38): two DECIMAL(18, 4) overflow on large purchases
    -- (e.g. 120,000 units at 450,000 each) and the whole build would fail.
    case
        when unit_price_raw > 0 and quantity > 0
            then cast(
                cast(unit_price_raw as decimal(38, 4)) * cast(quantity as decimal(38, 4))
                as decimal(38, 4)
            )
    end as line_amount
from parsed
