with source as (
    select * from {{ source('raw', 'raw_activities') }}
)

select
    activity_id,
    opportunity_id,
    coalesce(activity_type, 'Task') as activity_type,
    cast(activity_date as date)     as activity_date,
    owner_id
from source
