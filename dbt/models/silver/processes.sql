-- Contracting processes with the buyer location resolved, keeping track of where
-- each location comes from. Official data is never silently mixed with inferred data.

select
    p.* exclude (buyer_region, buyer_locality),
    coalesce(p.buyer_region, l.region) as buyer_region,
    coalesce(p.buyer_locality, l.locality) as buyer_locality,
    case
        when p.buyer_region is not null then 'published'
        when l.region is not null then l.location_source
    end as buyer_location_source
from {{ ref('stg_processes') }} as p
left join {{ ref('int_buyer_locations') }} as l on p.buyer_id = l.buyer_id
