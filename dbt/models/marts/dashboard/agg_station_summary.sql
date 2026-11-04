-- One row per station and pollutant: location, overall mean and data quality.
with hourly as (

    select * from {{ ref('int_dashboard_hourly') }}

),

stations as (

    select * from {{ ref('stg_stations') }}

),

summary as (

    select
        station_id,
        pollutant_symbol,
        unit,
        avg(value)                                                  as avg_value,
        count(value)                                                as valid_hours,
        count(*)                                                    as total_hours,
        count(value) / count(*)                                     as valid_share,
        cast(sum(case when validation_flag = 'N' then 1 else 0 end) as integer) as flag_n_hours,
        cast(sum(case when validation_flag not in ('V', 'N') then 1 else 0 end) as integer) as flag_other_hours,
        cast(min(period_start_local) as date)                       as first_date,
        cast(max(period_start_local) as date)                       as last_date
    from hourly
    group by all

)

select
    summary.station_id,
    stations.station_name,
    stations.station_type_code,
    stations.latitude,
    stations.longitude,
    summary.* exclude (station_id)
from summary
inner join stations
    on summary.station_id = stations.station_id
