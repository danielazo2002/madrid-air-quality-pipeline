"""Extract hourly weather for every air quality station from the Open-Meteo archive API."""

import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from madrid_air_quality_pipeline.config import (
    OPEN_METEO_ARCHIVE_URL,
    RAW_DIR,
    SOURCE_TIMEZONE,
    START_YEAR,
    WEATHER_VARIABLES,
)
from madrid_air_quality_pipeline.downloader import fetch, write_atomic

logger = logging.getLogger(__name__)

STATIONS_FILE = RAW_DIR / "stations" / "stations.csv"
WEATHER_DIR = RAW_DIR / "weather"
PAUSE_BETWEEN_REQUESTS_SECONDS = 1


@dataclass
class Station:
    code: str
    latitude: float
    longitude: float


def read_stations(path: Path = STATIONS_FILE) -> list[Station]:
    """Read station codes and coordinates from the raw stations file."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the stations extraction first.")

    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")
        stations = [
            Station(
                code=row["CODIGO"],
                latitude=float(row["LATITUD"]),
                longitude=float(row["LONGITUD"]),
            )
            for row in reader
        ]

    if not stations:
        raise ValueError(f"No stations found in {path}")
    return stations


def validate_weather(payload: dict, source: str) -> None:
    """Fail loudly if a variable is missing or the parallel arrays have different lengths."""
    hourly = payload.get("hourly") or {}
    expected = ["time", *WEATHER_VARIABLES]

    missing = [name for name in expected if name not in hourly]
    if missing:
        raise ValueError(f"Missing hourly variables {missing} in response for {source}")

    lengths = {name: len(hourly[name]) for name in expected}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"Hourly arrays have different lengths for {source}: {lengths}")


def is_complete_year(destination: Path, year: int) -> bool:
    """A past year is complete only if its saved file reaches the last hour of December 31."""
    if not destination.exists():
        return False
    times = json.loads(destination.read_text()).get("hourly", {}).get("time") or []
    return bool(times) and times[-1] == f"{year}-12-31T23:00"


def extract_weather(start_year: int = START_YEAR) -> list[Path]:
    """Download one JSON file per station and year, up to yesterday (Madrid time)."""
    yesterday = datetime.now(ZoneInfo(SOURCE_TIMEZONE)).date() - timedelta(days=1)
    stations = read_stations()
    written: list[Path] = []

    for station in stations:
        for year in range(start_year, yesterday.year + 1):
            destination = WEATHER_DIR / f"station={station.code}" / f"year={year}" / "weather.json"

            if year < yesterday.year and is_complete_year(destination, year):
                logger.info("Station %s, year %d is complete, skipping", station.code, year)
                continue

            params = {
                "latitude": station.latitude,
                "longitude": station.longitude,
                "start_date": date(year, 1, 1).isoformat(),
                "end_date": min(date(year, 12, 31), yesterday).isoformat(),
                "hourly": ",".join(WEATHER_VARIABLES),
                "timezone": "GMT",
            }
            response = fetch(OPEN_METEO_ARCHIVE_URL, params=params)
            validate_weather(response.json(), source=f"station {station.code}, year {year}")
            write_atomic(destination, response.content)

            logger.info("Saved weather for station %s, year %d", station.code, year)
            written.append(destination)
            time.sleep(PAUSE_BETWEEN_REQUESTS_SECONDS)

    return written


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    extract_weather()