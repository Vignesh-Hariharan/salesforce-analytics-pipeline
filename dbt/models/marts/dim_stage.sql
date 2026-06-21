{{ config(materialized='table') }}

with stage_order as (
    select * from {{ ref('stage_order') }}
),

default_weights as (
    select * from {{ ref('default_stage_weights') }}
)

select
    cast(o.stage_name as varchar)                  as stage_name,
    cast(o.stage_position as number(38, 0))        as stage_position,
    cast(o.stage_category as varchar)              as stage_category,
    cast(w.default_weight as float)                as default_weight,
    cast(o.stage_category in ('Closed Won', 'Closed Lost') as boolean) as is_closed_stage,
    cast(o.stage_category = 'Closed Won' as boolean)                   as is_won_stage,
    cast(o.stage_position < 99 as boolean)                            as is_funnel_stage
from stage_order o
left join default_weights w on w.stage_name = o.stage_name
