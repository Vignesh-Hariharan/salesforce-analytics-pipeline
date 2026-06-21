-- Single-row headline metrics for the pipeline-health workflow.
with opportunities as (
    select * from {{ ref('fct_opportunities') }}
)

select
    count(*)                                                       as total_opportunities,
    sum(case when is_won then 1 else 0 end)                        as closed_won,
    sum(case when is_closed and not is_won then 1 else 0 end)      as closed_lost,
    round(
        sum(case when is_won then 1 else 0 end) / nullif(count(*), 0) * 100, 1
    )                                                              as close_rate,
    avg(case when is_closed then days_to_close end)                as avg_days_to_close,
    sum(case when not is_closed then amount else 0 end)            as pipeline_value,
    avg(amount)                                                    as avg_deal_size
from opportunities
