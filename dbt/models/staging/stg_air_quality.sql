{#- Wide source format: Hnn = hourly value, Vnn = validation flag, for nn = 01..24. -#}
{%- set hours = range(1, 25) -%}

with historical as (

    select
        * exclude (period),
        'historical/' || period as source_partition,
        1                       as source_priority
    from {{ source('raw', 'air_quality_historical') }}

),

realtime as (

    select
        * exclude ("date"),
        'realtime/' || "date"   as source_partition,
        2                       as source_priority
    from {{ source('raw', 'air_quality_realtime') }}

),

unioned as (

    select * from historical
    union all by name
    select * from realtime

),

unpivoted as (

    unpivot unioned
    on
    {%- for h in hours %}
        {%- set hh = "%02d" | format(h) %}
        (H{{ hh }}, V{{ hh }}) as h{{ hh }}{% if not loop.last %},{% endif %}
    {%- endfor %}
    into
        name hour_label
        value raw_value, validation_flag

),

typed as (

    select
        lpad(trim(ESTACION), 3, '0')                    as station_id,
        lpad(trim(MAGNITUD), greatest(length(trim(MAGNITUD)), 2)::integer, '0') as pollutant_code,
        trim(PUNTO_MUESTREO)                            as sampling_point,
        make_date(
            cast(ANO as integer),
            cast(MES as integer),
            cast(DIA as integer)
        )                                               as measurement_date_local,
        cast(substr(hour_label, 2) as integer)          as hour_ending_local,
        trim(validation_flag)                           as validation_flag,
        -- Only validated values are kept; 'N' becomes NULL, never 0 (decision 009).
        case
            when trim(validation_flag) = 'V'
                then cast(replace(trim(raw_value), ',', '.') as double)
        end                                             as value,
        source_partition,
        source_priority
    from unpivoted

),

with_local_start as (

    select
        *,
        -- Hnn covers the hour ending at nn, so it starts at nn - 1 (local time).
        measurement_date_local + to_hours(hour_ending_local - 1) as period_start_local
    from typed

),

with_utc as (

    select
        *,
        -- Read the wall-clock time as Europe/Madrid, then express it as a UTC timestamp.
        timezone('UTC', timezone('Europe/Madrid', period_start_local)) as period_start_utc,
        -- Round trip back to local time. A mismatch means the local hour does not exist
        -- (the hour skipped by the March DST change).
        timezone('Europe/Madrid', timezone('Europe/Madrid', period_start_local))
            = period_start_local                                     as is_existing_local_time
    from with_local_start

),

deduplicated as (

    select *
    from with_utc
    where is_existing_local_time
    -- One row per station, pollutant and hour: valid rows first, then historical over realtime.
    qualify row_number() over (
        partition by station_id, pollutant_code, period_start_utc
        order by (validation_flag = 'V') desc, source_priority
    ) = 1

)

select
    station_id,
    pollutant_code,
    sampling_point,
    period_start_utc + interval 1 hour  as measured_at_utc,
    measurement_date_local,
    hour_ending_local,
    validation_flag,
    value,
    source_partition
from deduplicated