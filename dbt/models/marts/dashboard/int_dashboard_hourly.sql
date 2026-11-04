{#-
    Hourly rows for the dashboard pollutants, with the local hour start for calendar grouping.
    Ephemeral: compiled into the models that use it, never stored.
-#}
{{ config(materialized='ephemeral') }}

select
    station_id,
    station_name,
    station_type_code,
    pollutant_symbol,
    unit,
    measured_at_utc,
    -- measured_at_local labels the END of the hour; its start gives the right local date and hour.
    measured_at_local - interval 1 hour     as period_start_local,
    value,
    validation_flag,
    temperature_c,
    precipitation_mm,
    wind_speed_kmh,
    shortwave_radiation_wm2,
    boundary_layer_height_m
from {{ ref('fct_air_quality_weather') }}
where pollutant_symbol in (
    {%- for pollutant in var('dashboard_pollutants') %}
    '{{ pollutant }}'{% if not loop.last %},{% endif %}
    {%- endfor %}
)
