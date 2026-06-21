-- Historical win rate per stage: of the closed opportunities that ever entered
-- a stage, the share that were ultimately won. sample_size is carried through so
-- downstream models can decide whether to trust the rate or fall back to the
-- documented default weight.
with first_touch as (
    select distinct
        opportunity_id,
        stage_name
    from {{ ref('stg_stage_history') }}
),

closed_opps as (
    select
        opportunity_id,
        is_won
    from {{ ref('stg_opportunities') }}
    where is_closed
)

select
    ft.stage_name,
    count(*)                                       as sample_size,
    sum(case when o.is_won then 1 else 0 end)      as won_count,
    sum(case when not o.is_won then 1 else 0 end)  as lost_count,
    sum(case when o.is_won then 1 else 0 end) / nullif(count(*), 0) as historical_win_rate
from first_touch ft
inner join closed_opps o on o.opportunity_id = ft.opportunity_id
group by ft.stage_name
