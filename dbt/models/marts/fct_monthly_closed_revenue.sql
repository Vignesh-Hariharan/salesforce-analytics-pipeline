select
    date_trunc('month', close_date) as month,
    sum(amount)                     as revenue
from {{ ref('fct_opportunities') }}
where is_won
  and close_date >= dateadd('month', -6, current_date())
group by date_trunc('month', close_date)
order by month
