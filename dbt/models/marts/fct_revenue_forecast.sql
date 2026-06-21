-- Weighted pipeline forecast by open stage. Joins open pipeline to governed win
-- probabilities from fct_stage_win_probability.
with open_pipeline as (
    select
        stage_name,
        sum(amount) as stage_value,
        count(*)    as open_count
    from {{ ref('fct_opportunities') }}
    where not is_closed
      and amount > 0
    group by stage_name
),

weights as (
    select * from {{ ref('fct_stage_win_probability') }}
),

stages as (
    select stage_name, stage_position
    from {{ ref('dim_stage') }}
)

select
    p.stage_name,
    s.stage_position,
    p.open_count,
    p.stage_value,
    coalesce(w.weight, 0.25)               as weight,
    w.weight_source,
    coalesce(w.sample_size, 0)             as sample_size,
    p.stage_value * coalesce(w.weight, 0.25) as weighted_value
from open_pipeline p
left join weights w on w.stage_name = p.stage_name
left join stages s on s.stage_name = p.stage_name
order by s.stage_position
