-- Funnel conversion, ready to plot: one row per stage transition with the
-- conversion percentage to the next stage.
select
    stage_position,
    stage_name,
    next_stage_name,
    reached_count,
    next_reached_count,
    conversion_pct
from {{ ref('int_stage_conversions') }}
where conversion_pct is not null
order by stage_position
