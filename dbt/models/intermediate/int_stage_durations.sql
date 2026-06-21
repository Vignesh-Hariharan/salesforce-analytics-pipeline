-- Average days an opportunity sits in each stage, derived from consecutive
-- OpportunityHistory rows ordered by entry time. The final stage of each
-- opportunity is measured up to the current timestamp.
with history as (
    select * from {{ ref('stg_stage_history') }}
),

sequenced as (
    select
        opportunity_id,
        stage_name,
        entered_at,
        lead(entered_at) over (
            partition by opportunity_id
            order by entered_at
        ) as next_entered_at
    from history
)

select
    stage_name,
    avg(
        datediff('day', entered_at, coalesce(next_entered_at, current_timestamp()))
    ) as avg_days_in_stage
from sequenced
group by stage_name
