-- One row per station, pollutant and local day: daily mean concentration and daily weather.
with hourly as (

    select * from {{ ref('int_dashboard_hourly') }}

)

select
    station_id,
    station_name,
    pollutant_symbol,
    unit,
    cast(period_start_local as date)    as date_local,
    avg(value)                          as avg_value,
    max(value)                          as max_hourly_value,
    count(value)                        as valid_hours,
    count(*)                            as total_hours,
    avg(temperature_c)                  as avg_temperature_c,
    sum(precipitation_mm)               as total_precipitation_mm,
    avg(wind_speed_kmh)                 as avg_wind_speed_kmh,
    avg(shortwave_radiation_wm2)        as avg_shortwave_radiation_wm2,
    avg(boundary_layer_height_m)        as avg_boundary_layer_height_m
from hourly
group by all
