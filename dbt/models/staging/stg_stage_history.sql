with source as (
    select * from {{ source('raw', 'raw_stage_history') }}
)

select
    history_id,
    opportunity_id,
    stage_name,
    cast(entered_at as timestamp_ntz) as entered_at
from source
