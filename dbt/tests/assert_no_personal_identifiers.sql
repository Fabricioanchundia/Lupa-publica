-- Privacy guard (ADR-0004). Fails if any natural person (or unclassified supplier)
-- keeps a name or a raw numeric identifier instead of a 64-character pseudonym.
select supplier_type, supplier_key, supplier_name
from {{ ref('stg_award_suppliers') }}
where supplier_type in ('natural_person', 'unknown')
  and (
      supplier_name is not null
      or not regexp_full_match(coalesce(supplier_key, ''), '^([0-9a-f]{64})?$')
  )
