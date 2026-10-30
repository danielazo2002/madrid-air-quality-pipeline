with source as (

    select * from {{ source('raw', 'stations') }}

),

renamed as (

    select
        -- Join key with air quality data. Padded to 3 digits so '11' and '011' match.
        lpad(trim(CODIGO_CORTO), 3, '0')  as station_id,
        trim(CODIGO)                      as station_code,
        trim(ESTACION)                    as station_name,
        cast(LATITUD as double)           as latitude,
        cast(LONGITUD as double)          as longitude,
        cast(replace(trim(ALTITUD), ',', '.') as double)                   as altitude_m,
        strptime(trim("Fecha alta"), ['%d/%m/%Y', '%Y-%m-%d'])::date      as opened_on,
        -- COD_TIPO instead of NOM_TIPO: the names contain typos.
        trim(COD_TIPO)                    as station_type_code

    from source

)

select * from renamed