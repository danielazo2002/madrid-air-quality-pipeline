with source as (

    select * from {{ source('raw', 'weather') }}

),

unnested as (

    select
        station                                  as station_code,
        latitude                                 as grid_latitude,
        longitude                                as grid_longitude,
        -- Parallel arrays: DuckDB unnests several lists in the same SELECT position by position.
        unnest(hourly['time'])                   as time_text,
        unnest(hourly['temperature_2m'])         as temperature_c,
        unnest(hourly['relative_humidity_2m'])   as relative_humidity_pct,
        unnest(hourly['precipitation'])          as precipitation_mm,
        unnest(hourly['wind_speed_10m'])         as wind_speed_kmh,
        unnest(hourly['wind_direction_10m'])     as wind_direction_deg,
        unnest(hourly['shortwave_radiation'])    as shortwave_radiation_wm2,
        unnest(hourly['boundary_layer_height'])  as boundary_layer_height_m
    from source

)

select
    station_code,
    grid_latitude,
    grid_longitude,
    -- Requested with timezone=GMT, so these naive timestamps are already UTC.
    strptime(time_text, '%Y-%m-%dT%H:%M')        as measured_at_utc,
    cast(temperature_c as double)                as temperature_c,
    cast(relative_humidity_pct as double)        as relative_humidity_pct,
    cast(precipitation_mm as double)             as precipitation_mm,
    cast(wind_speed_kmh as double)               as wind_speed_kmh,
    cast(wind_direction_deg as double)           as wind_direction_deg,
    cast(shortwave_radiation_wm2 as double)      as shortwave_radiation_wm2,
    cast(boundary_layer_height_m as double)      as boundary_layer_height_m
from unnested