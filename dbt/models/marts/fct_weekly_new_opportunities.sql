-- New opportunities created per week over the trailing 12 weeks.
with opportunities as (
    select *
    from {{ ref('fct_opportunities') }}
    where created_date is not null
      and created_date >= dateadd('week', -12, current_date)
)

select
    date_trunc('week', created_date) as week_start,
    count(*)                         as new_opportunities
from opportunities
group by date_trunc('week', created_date)
order by week_start
