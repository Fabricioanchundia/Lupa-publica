-- One row per buyer with its best-known location and where that location came from.
--   same_buyer: the most frequent location the buyer itself published in other processes
--   manual:     the reviewed seed, only for buyers that never publish a location

with published as (
    select
        buyer_id,
        buyer_region as region,
        buyer_locality as locality,
        count(*) as processes
    from {{ ref('stg_processes') }}
    where buyer_region is not null
    group by all
),

most_frequent as (
    select buyer_id, region, locality
    from published
    qualify row_number() over (
        partition by buyer_id order by processes desc, region, locality
    ) = 1
),

manual as (
    select buyer_id, region, locality
    from {{ ref('buyer_locations') }}
)

select
    coalesce(f.buyer_id, m.buyer_id) as buyer_id,
    coalesce(f.region, m.region) as region,
    coalesce(f.locality, m.locality) as locality,
    case when f.buyer_id is not null then 'same_buyer' else 'manual' end as location_source
from most_frequent as f
full outer join manual as m on f.buyer_id = m.buyer_id
