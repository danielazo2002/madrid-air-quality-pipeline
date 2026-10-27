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