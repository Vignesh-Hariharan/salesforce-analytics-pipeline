-- Open pipeline by stage: count, value and average age. Ordered by funnel
-- position so the consumer plots stages left to right without re-deriving order.
with open_opportunities as (
    select *
    from {{ ref('fct_opportunities') }}
    where not is_closed
)

select
    stage_name,
    min(stage_position)   as stage_position,
    count(*)              as open_count,
    sum(amount)           as stage_value,
    avg(days_open)        as avg_days_open
from open_opportunities
group by stage_name
order by stage_position
