with base_air_quality as (

    select * from {{ ref('base_air_quality') }}

),

with_local_start as (

    select
        *,
        -- Hnn covers the hour ending at nn, so it starts at nn - 1 (local time).
        measurement_date_local + to_hours(hour_ending_local - 1) as period_start_local
    from base_air_quality

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