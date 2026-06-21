{{ config(materialized='table') }}

-- Opportunity-grain fact. Holds the derivations that used to live in the Python
-- loader: activity totals, lifetime days, and current age. days_open measures
-- age to the close date for closed opportunities and to today for open ones, so
-- the at-risk and age-distribution metrics reflect true elapsed time.
with opportunities as (
    select * from {{ ref('stg_opportunities') }}
),

activity_counts as (
    select * from {{ ref('int_opportunity_activity_counts') }}
),

stages as (
    select
        stage_name,
        stage_position,
        stage_category
    from {{ ref('dim_stage') }}
)

select
    cast(o.opportunity_id as varchar)       as opportunity_id,
    cast(o.opportunity_name as varchar)     as opportunity_name,
    cast(o.amount as number(18, 2))         as amount,
    cast(o.stage_name as varchar)           as stage_name,
    cast(s.stage_position as number(38, 0)) as stage_position,
    cast(s.stage_category as varchar)       as stage_category,
    cast(o.created_date as date)            as created_date,
    cast(o.close_date as date)              as close_date,
    cast(o.is_closed as boolean)            as is_closed,
    cast(o.is_won as boolean)               as is_won,
    cast(o.owner_id as varchar)             as owner_id,
    cast(o.owner_name as varchar)           as owner_name,
    cast(
        case
            when o.is_closed then datediff('day', o.created_date, o.close_date)
            else datediff('day', o.created_date, current_date)
        end as number(38, 0)
    )                                       as days_open,
    cast(
        case when o.is_closed then datediff('day', o.created_date, o.close_date) end
        as number(38, 0)
    )                                       as days_to_close,
    cast(coalesce(a.total_activities, 0) as number(38, 0)) as total_activities
from opportunities o
left join activity_counts a on a.opportunity_id = o.opportunity_id
left join stages s on s.stage_name = o.stage_name
