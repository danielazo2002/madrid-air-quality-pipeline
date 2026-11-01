{#-
    Base model: reshapes the raw wide files into one row per station, pollutant and local hour.
    Kept separate from stg_air_quality so the time zone and precedence logic can be unit tested
    with plain rows, without depending on the raw file layout.

    Wide source format: Hnn = hourly value, Vnn = validation flag, for nn = 01..24. -#}
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

)

select * from typed
