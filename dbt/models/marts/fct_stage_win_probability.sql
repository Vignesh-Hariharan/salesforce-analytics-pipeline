-- Stage win probability for forecasting: historical rate when sample_size meets
-- the threshold, otherwise the documented default from seeds. weight_source flags
-- which was used so downstream never confuses a default for a fitted estimate.
{% set min_sample = var('min_stage_sample') %}

with historical as (
    select * from {{ ref('int_stage_win_rates') }}
),

defaults as (
    select stage_name, default_weight
    from {{ ref('default_stage_weights') }}
)

select
    d.stage_name,
    coalesce(h.sample_size, 0)                         as sample_size,
    case
        when coalesce(h.sample_size, 0) >= {{ min_sample }}
        then h.historical_win_rate
        else d.default_weight
    end                                                as weight,
    case
        when coalesce(h.sample_size, 0) >= {{ min_sample }}
        then 'historical'
        else 'default'
    end                                                as weight_source
from defaults d
left join historical h on h.stage_name = d.stage_name
