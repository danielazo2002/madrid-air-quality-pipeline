"""Extract Madrid hourly air quality data: historical files and the real-time file."""

import io
import logging
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from madrid_air_quality_pipeline.config import (
    AIR_QUALITY_HISTORICAL_PACKAGE,
    AIR_QUALITY_REALTIME_PACKAGE,
    CKAN_PACKAGE_SHOW_URL,
    RAW_DIR,
    SOURCE_TIMEZONE,
    START_YEAR,
)
from madrid_air_quality_pipeline.downloader import (
    fetch,
    validate_header,
    write_atomic,
)

logger = logging.getLogger(__name__)

EXPECTED_HEADER = "PROVINCIA;MUNICIPIO;ESTACION;MAGNITUD;PUNTO_MUESTREO;ANO;MES;DIA;H01;V01"
PERIOD_PATTERN = re.compile(r"^(?:Desde )?(\d{4})$")
MONTHS_PER_YEAR = 12
FINGERPRINT_FILE = "_fingerprint.txt"

# The real-time file is served by a paginated API. One page must hold the whole file:
# ~3,900 rows observed for 30 days, so 50,000 leaves a wide margin.
REALTIME_PAGE_SIZE = 50_000
# 23 of the 24 catalogue stations were reporting when this was written.
MIN_REALTIME_STATIONS = 20

HISTORICAL_DIR = RAW_DIR / "air_quality" / "historical"
REALTIME_DIR = RAW_DIR / "air_quality" / "realtime"


@dataclass
class HistoricalResource:
    """A historical file published on the portal."""

    period: str  # folder name: "2024" or "desde_2025"
    year: int
    is_open: bool  # True for "Desde YYYY": still being updated every month
    url: str
    fingerprint: str  # changes whenever the source file changes


# --- Discovery -----------------------------------------------------------------


def get_package_resources(package_id: str) -> list[dict]:
    """Return the list of resources of a CKAN dataset."""
    payload = fetch(f"{CKAN_PACKAGE_SHOW_URL}?id={package_id}").json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN returned an unsuccessful response for {package_id}")
    return payload["result"]["resources"]


def discover_historical_resources(start_year: int = START_YEAR) -> list[HistoricalResource]:
    """Select the closed yearly ZIPs from start_year onwards, plus the open 'Desde YYYY' CSV."""
    selected: list[HistoricalResource] = []

    for resource in get_package_resources(AIR_QUALITY_HISTORICAL_PACKAGE):
        hierarchy = resource.get("hierarchy") or [{}]
        name = hierarchy[0].get("hierarchy_name") or ""
        match = PERIOD_PATTERN.match(name)
        if match is None:
            continue  # e.g. the PDF documentation

        year = int(match.group(1))
        is_open = name.startswith("Desde")
        expected_format = "CSV" if is_open else "ZIP"

        if resource.get("format") != expected_format:
            continue  # skip the JSON / XML copies
        if not is_open and year < start_year:
            continue  # closed years outside our range

        selected.append(
            HistoricalResource(
                period=f"desde_{year}" if is_open else str(year),
                year=year,
                is_open=is_open,
                url=resource["url"],
                fingerprint=resource.get("hash") or resource.get("last_modified") or "",
            )
        )

    # Turn silent gaps into loud errors
    open_years = [r.year for r in selected if r.is_open]
    if not open_years:
        raise RuntimeError("No open 'Desde YYYY' CSV found: the portal layout may have changed")

    closed_years = {r.year for r in selected if not r.is_open}
    missing = set(range(start_year, min(open_years))) - closed_years
    if missing:
        raise RuntimeError(f"Missing historical files for years: {sorted(missing)}")

    return selected


# --- Historical extraction -------------------------------------------------------


def should_download(resource: HistoricalResource, target_dir: Path) -> bool:
    """Closed years are downloaded once; the open period only when its fingerprint changes."""
    marker = target_dir / FINGERPRINT_FILE
    if not marker.exists():
        return True
    if not resource.is_open:
        return False
    return not resource.fingerprint or marker.read_text().strip() != resource.fingerprint


def save_zip_csvs(content: bytes, target_dir: Path, source: str) -> int:
    """Extract only the CSV files from a yearly ZIP, validating each one."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        csv_members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        if len(csv_members) != MONTHS_PER_YEAR:
            raise ValueError(
                f"Expected {MONTHS_PER_YEAR} monthly CSV files in {source}, found {len(csv_members)}"
            )
        for member in csv_members:
            data = archive.read(member)
            validate_header(data, EXPECTED_HEADER, source=f"{source}::{member}")
            write_atomic(target_dir / Path(member).name, data)
    return len(csv_members)


def extract_historical(start_year: int = START_YEAR) -> list[Path]:
    """Download every historical period that is missing or has changed."""
    updated: list[Path] = []

    for resource in discover_historical_resources(start_year):
        target_dir = HISTORICAL_DIR / f"period={resource.period}"

        if not should_download(resource, target_dir):
            logger.info("Period %s is up to date, skipping", resource.period)
            continue

        content = fetch(resource.url).content
        if resource.is_open:
            validate_header(content, EXPECTED_HEADER, source=resource.url)
            write_atomic(target_dir / "air_quality.csv", content)
        else:
            save_zip_csvs(content, target_dir, source=resource.url)

        # Written last: if anything above fails, the marker is missing and the period is retried
        write_atomic(target_dir / FINGERPRINT_FILE, (resource.fingerprint or resource.url).encode())
        logger.info("Period %s saved to %s", resource.period, target_dir)
        updated.append(target_dir)

    return updated


# --- Real-time extraction --------------------------------------------------------


def with_page_size(url: str, page_size: int) -> str:
    """Return the URL with its pageSize query parameter set (replacing any existing value)."""
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "pageSize"]
    query.append(("pageSize", str(page_size)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def validate_realtime_file(
    content: bytes,
    source: str,
    page_size: int = REALTIME_PAGE_SIZE,
    min_stations: int = MIN_REALTIME_STATIONS,
) -> None:
    """Fail loudly if the paginated API may have truncated the file or stations are missing."""
    lines = content.decode("utf-8-sig", errors="replace").splitlines()
    rows = [line for line in lines[1:] if line.strip()]

    if len(rows) >= page_size:
        raise ValueError(
            f"{source} returned {len(rows)} rows, the full page size: the file may be truncated"
        )

    stations = {row.split(";")[2].strip('"') for row in rows}
    if len(stations) < min_stations:
        raise ValueError(
            f"{source} contains {len(stations)} stations, expected at least {min_stations}"
        )


def extract_realtime() -> Path:
    """Download the last 30 days of real-time data, partitioned by download date (Madrid)."""
    csv_resources = [
        r for r in get_package_resources(AIR_QUALITY_REALTIME_PACKAGE) if r.get("format") == "CSV"
    ]
    if len(csv_resources) != 1:
        raise RuntimeError(f"Expected 1 real-time CSV resource, found {len(csv_resources)}")

    url = with_page_size(csv_resources[0]["url"], REALTIME_PAGE_SIZE)
    content = fetch(url).content
    validate_header(content, EXPECTED_HEADER, source=url)
    validate_realtime_file(content, source=url)

    today_in_madrid = datetime.now(ZoneInfo(SOURCE_TIMEZONE)).date()
    destination = REALTIME_DIR / f"date={today_in_madrid.isoformat()}" / "air_quality.csv"
    write_atomic(destination, content)
    logger.info("Downloaded %s (%d bytes)", destination, len(content))
    return destination


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    extract_historical()
    extract_realtime()
