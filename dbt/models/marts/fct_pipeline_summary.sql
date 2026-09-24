-- Single-row headline metrics for the pipeline-health workflow.
with opportunities as (
    select * from {{ ref('fct_opportunities') }}
),
rolled as (
    select
        count(*)                                                       as total_opportunities,
        sum(case when is_won then 1 else 0 end)                        as closed_won,
        sum(case when is_closed and not is_won then 1 else 0 end)      as closed_lost,
        avg(case when is_closed then days_to_close end)                as avg_days_to_close,
        sum(case when not is_closed then amount else 0 end)            as pipeline_value,
        avg(amount)                                                    as avg_deal_size
    from opportunities
)

select
    total_opportunities,
    closed_won,
    closed_lost,
    round(
        closed_won / nullif(closed_won + closed_lost, 0) * 100, 1
    )                                                                  as close_rate,
    avg_days_to_close,
    pipeline_value,
    avg_deal_size
from rolled
