-- Average concentration by local hour of the day, weekdays vs weekends (traffic signature).
with hourly as (

    select * from {{ ref('int_dashboard_hourly') }}
    where value is not null

)

select
    pollutant_symbol,
    unit,
    case
        when isodow(period_start_local) in (6, 7) then 'weekend'
        else 'weekday'
    end                                 as day_type,
    hour(period_start_local)            as hour_local,
    avg(value)                          as avg_value,
    count(*)                            as valid_hours
from hourly
group by all
