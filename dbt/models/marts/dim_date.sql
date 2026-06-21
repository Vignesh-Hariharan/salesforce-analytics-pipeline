{{ config(materialized='table') }}

-- Generated calendar spanning the reporting window (var date_spine_start to
-- today). Gives trend and cohort queries a complete set of dates to join to,
-- including days with no opportunity activity.
with spine as (
    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ var('date_spine_start') ~ "' as date)",
        end_date="dateadd('day', 1, current_date)"
    ) }}
)

select
    cast(date_day as date)                              as date_day,
    cast(extract(year from date_day) as number(38, 0))  as year_number,
    cast(extract(quarter from date_day) as number(38, 0)) as quarter_number,
    cast(extract(month from date_day) as number(38, 0)) as month_number,
    cast(to_char(date_day, 'YYYY-MM') as varchar)       as year_month,
    cast(date_trunc('week', date_day) as date)          as week_start,
    cast(date_trunc('month', date_day) as date)         as month_start
from spine
