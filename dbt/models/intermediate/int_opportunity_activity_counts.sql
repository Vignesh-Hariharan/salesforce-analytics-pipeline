with activities as (
    select * from {{ ref('stg_activities') }}
)

select
    opportunity_id,
    count(*) as total_activities
from activities
group by opportunity_id
