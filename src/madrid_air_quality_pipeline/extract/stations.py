"""Extract the air quality monitoring stations catalogue."""

import logging
from pathlib import Path

from madrid_air_quality_pipeline.config import RAW_DIR, STATIONS_URL
from madrid_air_quality_pipeline.downloader import download_file

logger = logging.getLogger(__name__)

EXPECTED_HEADER = "CODIGO;CODIGO_CORTO;ESTACION"


def extract_stations() -> Path:
    """Download the stations CSV into the raw layer, overwriting any previous version."""
    destination = RAW_DIR / "stations" / "stations.csv"
    return download_file(STATIONS_URL, destination, expected_header=EXPECTED_HEADER)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    extract_stations()