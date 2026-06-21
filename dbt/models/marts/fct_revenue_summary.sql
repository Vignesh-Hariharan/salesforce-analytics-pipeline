-- Single-row headline metrics for the revenue-forecast workflow.
with open_pipeline as (
    select
        count(*)  as open_opps,
        sum(amount) as total_pipeline
    from {{ ref('fct_opportunities') }}
    where not is_closed
      and amount > 0
),

at_risk as (
    select coalesce(sum(amount), 0) as at_risk_value
    from {{ ref('fct_opportunities') }}
    where not is_closed
      and days_open > {{ var('at_risk_days') }}
),

forecast as (
    select coalesce(sum(weighted_value), 0) as weighted_forecast
    from {{ ref('fct_revenue_forecast') }}
),

fallbacks as (
    select count(*) as weights_fallback_count
    from {{ ref('fct_stage_win_probability') }}
    where weight_source = 'default'
)

select
    o.open_opps,
    o.total_pipeline,
    a.at_risk_value,
    f.weighted_forecast,
    fb.weights_fallback_count
from open_pipeline o
cross join at_risk a
cross join forecast f
cross join fallbacks fb
