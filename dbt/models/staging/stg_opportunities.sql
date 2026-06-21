with source as (
    select * from {{ source('raw', 'raw_opportunities') }}
)

select
    opportunity_id,
    opportunity_name,
    cast(amount as number(18, 2))   as amount,
    stage_name,
    cast(created_date as date)      as created_date,
    cast(close_date as date)        as close_date,
    cast(is_closed as boolean)      as is_closed,
    cast(is_won as boolean)         as is_won,
    owner_id,
    coalesce(owner_name, 'Unknown') as owner_name
from source
