-- Stage-to-stage funnel conversion from OpportunityHistory. For each funnel
-- stage we count the distinct opportunities that ever reached it, then express
-- conversion as the share that also reached the next stage in seed order.
-- Terminal non-funnel stages (position 99, e.g. Closed Lost) are excluded.
with reached as (
    select distinct
        opportunity_id,
        stage_name
    from {{ ref('stg_stage_history') }}
),

funnel_stages as (
    select
        stage_name,
        stage_position
    from {{ ref('dim_stage') }}
    where stage_position < 99
),

reached_by_stage as (
    select
        s.stage_position,
        s.stage_name,
        count(distinct r.opportunity_id) as reached_count
    from funnel_stages s
    left join reached r on r.stage_name = s.stage_name
    group by s.stage_position, s.stage_name
),

with_next as (
    select
        stage_position,
        stage_name,
        reached_count,
        lead(stage_name) over (order by stage_position)    as next_stage_name,
        lead(reached_count) over (order by stage_position)  as next_reached_count
    from reached_by_stage
)

select
    stage_position,
    stage_name,
    next_stage_name,
    reached_count,
    next_reached_count,
    case
        when reached_count > 0 and next_stage_name is not null
        then round(next_reached_count / reached_count * 100, 1)
    end as conversion_pct
from with_next
