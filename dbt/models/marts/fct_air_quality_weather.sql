with air_quality as (

    select * from {{ ref('stg_air_quality') }}

),

stations as (

    select * from {{ ref('stg_stations') }}

),

pollutants as (

    select * from {{ ref('pollutants') }}

),

weather as (

    select * from {{ ref('stg_weather') }}

)

select
    -- Keys and time
    air_quality.station_id,
    stations.station_code,
    air_quality.pollutant_code,
    air_quality.measured_at_utc,
    -- Local time, for display only (decision 008).
    timezone('Europe/Madrid', timezone('UTC', air_quality.measured_at_utc)) as measured_at_local,

    -- Station attributes
    stations.station_name,
    stations.station_type_code,

    -- Measurement
    pollutants.pollutant_symbol,
    pollutants.unit,
    air_quality.value,
    air_quality.validation_flag,

    -- Weather at the same station and hour (NULL when not yet available)
    weather.temperature_c,
    weather.relative_humidity_pct,
    weather.precipitation_mm,
    weather.wind_speed_kmh,
    weather.wind_direction_deg,
    weather.shortwave_radiation_wm2,
    weather.boundary_layer_height_m

from air_quality
inner join stations
    on air_quality.station_id = stations.station_id
inner join pollutants
    on air_quality.pollutant_code = pollutants.pollutant_code
left join weather
    on  weather.station_code    = stations.station_code
    and weather.measured_at_utc = air_quality.measured_at_utc