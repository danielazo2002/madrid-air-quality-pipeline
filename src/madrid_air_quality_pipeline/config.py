"""Central configuration: paths and source URLs."""

import os
from pathlib import Path

# Project root: three levels up from this file
# config.py -> madrid_air_quality_pipeline/ -> src/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The data directory can be overridden with an environment variable.
# This will matter later, when the code runs inside Airflow's Docker containers.
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"

STATIONS_URL = (
    "https://datos.madrid.es/dataset/212629-0-estaciones-control-aire/"
    "resource/212629-0-estaciones-control-aire-csv/download/"
    "212629-0-estaciones-control-aire-csv.csv"
)

# First year of data to load (decision 006). Can be overridden from the environment.
START_YEAR = int(os.environ.get("START_YEAR", "2024"))

# CKAN metadata API, used to discover download URLs (decision: discovery over hardcoding)
CKAN_PACKAGE_SHOW_URL = "https://datos.madrid.es/api/3/action/package_show"
AIR_QUALITY_HISTORICAL_PACKAGE = "201200-0-calidad-aire-horario"
AIR_QUALITY_REALTIME_PACKAGE = "212531-0-calidad-aire-tiempo-real"

# Timezone in which the source publishes its data
SOURCE_TIMEZONE = "Europe/Madrid"