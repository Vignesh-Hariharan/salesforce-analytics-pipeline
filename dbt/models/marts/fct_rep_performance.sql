select
    owner_name,
    count(*)                                              as total_opps,
    sum(case when is_won then 1 else 0 end)               as won_opps,
    avg(amount)                                           as avg_deal_size,
    avg(total_activities)                                 as avg_activities,
    sum(amount)                                           as total_revenue,
    round(
        sum(case when is_won then 1 else 0 end) / nullif(count(*), 0) * 100, 1
    )                                                     as close_rate_pct
from {{ ref('fct_opportunities') }}
where is_closed
group by owner_name
having count(*) >= 3
order by won_opps desc
