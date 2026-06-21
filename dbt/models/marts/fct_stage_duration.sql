-- Average time in each stage, ordered longest first for the time-in-stage chart.
with durations as (
    select * from {{ ref('int_stage_durations') }}
),

stages as (
    select
        stage_name,
        stage_position
    from {{ ref('dim_stage') }}
)

select
    d.stage_name,
    s.stage_position,
    d.avg_days_in_stage
from durations d
left join stages s on s.stage_name = d.stage_name
order by d.avg_days_in_stage desc
