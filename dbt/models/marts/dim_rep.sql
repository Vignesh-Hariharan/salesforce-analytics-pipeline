{{ config(materialized='table') }}

-- One row per opportunity owner. Owner names can change on reassignment; the
-- most recently loaded name wins, keyed on the stable owner_id.
with owners as (
    select
        owner_id,
        owner_name
    from {{ ref('stg_opportunities') }}
    where owner_id is not null
),

deduplicated as (
    select
        owner_id,
        max(owner_name) as owner_name
    from owners
    group by owner_id
)

select
    cast({{ dbt_utils.generate_surrogate_key(['owner_id']) }} as varchar) as rep_key,
    cast(owner_id as varchar)   as owner_id,
    cast(owner_name as varchar) as owner_name
from deduplicated
