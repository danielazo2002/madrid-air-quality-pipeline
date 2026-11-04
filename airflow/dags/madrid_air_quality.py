"""
### Madrid air quality and weather: daily ELT

1. **Extract** the station catalogue, historical and recent air quality, and weather
   into the raw layer (`data/raw`). Weather needs the station catalogue first.
2. **Transform** with dbt, one Airflow task per model and test (Astronomer Cosmos).

Runs every day at 06:00 Madrid time (decision 028). dbt tasks share the `duckdb_writer`
pool, which has a single slot: DuckDB allows only one writer process (decision 027).
"""

from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.sdk import dag, task
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import InvocationMode

from madrid_air_quality_pipeline.extract import air_quality, stations, weather

DBT_PROJECT_DIR = Path("/opt/pipeline/dbt")
DBT_EXECUTABLE = Path("/opt/airflow/dbt_venv/bin/dbt")
DUCKDB_POOL = "duckdb_writer"


@dag(
    dag_id="madrid_air_quality",
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 11, 1, tz="Europe/Madrid"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    doc_md=__doc__,
    tags=["madrid", "air-quality", "dbt"],
)
def madrid_air_quality():

    @task
    def extract_stations() -> None:
        stations.extract_stations()

    @task
    def extract_weather() -> None:
        weather.extract_weather()

    @task
    def extract_air_quality_historical() -> None:
        air_quality.extract_historical()

    @task
    def extract_air_quality_realtime() -> None:
        air_quality.extract_realtime()

    transform = DbtTaskGroup(
        group_id="dbt",
        project_config=ProjectConfig(DBT_PROJECT_DIR),
        profile_config=ProfileConfig(
            profile_name="madrid_air_quality",
            target_name="dev",
            profiles_yml_filepath=DBT_PROJECT_DIR / "profiles.yml",
        ),
        execution_config=ExecutionConfig(
            dbt_executable_path=DBT_EXECUTABLE,
            # Always run the dbt executable from its own virtual environment (decision 027),
            # never dbt imported as a library inside Airflow's Python environment.
            invocation_mode=InvocationMode.SUBPROCESS,
        ),
        render_config=RenderConfig(
            dbt_executable_path=DBT_EXECUTABLE,
            # Cosmos runs `dbt ls` at parse time to build the task graph. Its default
            # (RenderConfig.invocation_mode = DBT_RUNNER) imports dbt inside Airflow's
            # Python environment, where dbt is deliberately not installed (decision 027).
            invocation_mode=InvocationMode.SUBPROCESS,
            # Unit tests check code, not data: they run in CI, not in the daily pipeline.
            exclude=["resource_type:unit_test"],
        ),
        operator_args={"pool": DUCKDB_POOL},
    )

    weather_extracted = extract_stations() >> extract_weather()
    [
        weather_extracted,
        extract_air_quality_historical(),
        extract_air_quality_realtime(),
    ] >> transform


madrid_air_quality()
