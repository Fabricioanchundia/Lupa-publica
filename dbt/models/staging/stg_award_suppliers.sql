-- One row per supplier of an award, with privacy applied (ADR-0004):
--   * companies and public entities keep their RUC and name (public business data);
--   * natural persons get a pseudonym (HMAC) and no name;
--   * identifiers we cannot classify are treated as personal, just in case.
-- The raw identifier and the cédula never leave this model.

with awards as (
    select
        ocid,
        source_month,
        unnest(from_json(payload, '{
            "awards": [{"id": "VARCHAR", "suppliers": [{"id": "VARCHAR", "name": "VARCHAR"}]}]
        }').awards) as award
    from {{ source('bronze', 'releases') }}
),

suppliers as (
    select
        ocid,
        source_month,
        award.id as award_id,
        unnest(award.suppliers) as supplier
    from awards
),

parsed as (
    -- SERCOP ids look like <scheme>-<tax id>-<registry suffix>, e.g. EC-RUC-<13 digits>-<n>.
    select
        ocid,
        source_month,
        award_id,
        nullif(regexp_extract(supplier.id, '^([A-Z-]+)-[0-9]+-[0-9]+$', 1), '') as scheme,
        nullif(regexp_extract(supplier.id, '^[A-Z-]+-([0-9]+)-[0-9]+$', 1), '') as tax_id,
        nullif(trim(supplier.name), '') as name
    from suppliers
),

typed as (
    -- Third digit of a 13-digit RUC: 0-5 natural person, 6 public entity, 9 private company.
    select
        *,
        case
            when length(tax_id) <> 13 or tax_id is null then 'unknown'
            when substr(tax_id, 3, 1) in ('0', '1', '2', '3', '4', '5') then 'natural_person'
            when substr(tax_id, 3, 1) = '6' then 'public_entity'
            when substr(tax_id, 3, 1) = '9' then 'private_company'
            else 'unknown'
        end as supplier_type
    from parsed
)

select
    ocid,
    source_month,
    award_id,
    scheme as supplier_scheme,
    supplier_type,
    case
        when supplier_type in ('private_company', 'public_entity') then tax_id
        else pseudonymize(tax_id)
    end as supplier_key,
    case
        when supplier_type in ('private_company', 'public_entity') then name
    end as supplier_name
from typed
