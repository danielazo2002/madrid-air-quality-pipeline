-- Average concentration by weather bin, computed on hourly data (not daily means).
-- bin_lower is the lower edge of each bin; the last bin of each variable is open-ended.
with hourly as (

    select * from {{ ref('int_dashboard_hourly') }}
    where value is not null

),

binned as (

    select pollutant_symbol, unit, 'wind_speed_kmh' as weather_variable,
        least(floor(wind_speed_kmh / 5) * 5, 40) as bin_lower, value
    from hourly where wind_speed_kmh is not null

    union all

    select pollutant_symbol, unit, 'boundary_layer_height_m',
        least(floor(boundary_layer_height_m / 250) * 250, 2500), value
    from hourly where boundary_layer_height_m is not null

    union all

    select pollutant_symbol, unit, 'temperature_c',
        floor(temperature_c / 5) * 5, value
    from hourly where temperature_c is not null

    union all

    select pollutant_symbol, unit, 'shortwave_radiation_wm2',
        least(floor(shortwave_radiation_wm2 / 100) * 100, 900), value
    from hourly where shortwave_radiation_wm2 is not null

    union all

    select pollutant_symbol, unit, 'precipitation_mm',
        case
            when precipitation_mm = 0 then 0
            when precipitation_mm < 1 then 0.1
            when precipitation_mm < 5 then 1
            else 5
        end, value
    from hourly where precipitation_mm is not null

)

select
    pollutant_symbol,
    unit,
    weather_variable,
    cast(bin_lower as double)   as bin_lower,
    count(*)                    as valid_hours,
    avg(value)                  as avg_value
from binned
group by all
