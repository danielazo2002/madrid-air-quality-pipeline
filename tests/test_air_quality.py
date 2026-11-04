"""Tests for air quality discovery and extraction (decisions 010, 011, 012 and 025)."""

import io
import zipfile

import pytest

from madrid_air_quality_pipeline.extract import air_quality
from madrid_air_quality_pipeline.extract.air_quality import (
    EXPECTED_HEADER,
    FINGERPRINT_FILE,
    HistoricalResource,
    discover_historical_resources,
    extract_historical,
    extract_realtime,
    save_zip_csvs,
    should_download,
    validate_realtime_file,
    with_page_size,
)

CSV_CONTENT = f"{EXPECTED_HEADER};H02\n28;079;004;08;28079004_8_8;2024;01;01;12;V;10\n".encode()


def ckan_resource(name: str, fmt: str, url: str, hash_: str = "") -> dict:
    """Build a CKAN resource with the fields the extractor reads."""
    return {"hierarchy": [{"hierarchy_name": name}], "format": fmt, "url": url, "hash": hash_}


def make_zip(member_names: list[str], content: bytes = CSV_CONTENT) -> bytes:
    """Build an in-memory ZIP archive containing the given members."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in member_names:
            archive.writestr(name, content)
    return buffer.getvalue()


MONTHLY_CSVS = [f"ene_mo24_{month:02d}.csv" for month in range(1, 13)]

PORTAL_RESOURCES = [
    ckan_resource("Documentación", "PDF", "https://example.test/doc.pdf"),
    ckan_resource("2023", "ZIP", "https://example.test/2023.zip"),
    ckan_resource("2024", "ZIP", "https://example.test/2024.zip"),
    ckan_resource("2024", "JSON", "https://example.test/2024.json"),
    ckan_resource("Desde 2025", "CSV", "https://example.test/desde_2025.csv", hash_="abc"),
]


# --- Discovery ------------------------------------------------------------------------


def test_discovery_selects_closed_years_in_range_and_the_open_period(monkeypatch):
    monkeypatch.setattr(air_quality, "get_package_resources", lambda _: PORTAL_RESOURCES)

    resources = discover_historical_resources(start_year=2024)

    assert [(r.period, r.is_open, r.url) for r in resources] == [
        ("2024", False, "https://example.test/2024.zip"),
        ("desde_2025", True, "https://example.test/desde_2025.csv"),
    ]


def test_discovery_fails_loudly_when_a_year_is_missing(monkeypatch):
    without_2024_zip = [r for r in PORTAL_RESOURCES if r["url"] != "https://example.test/2024.zip"]
    monkeypatch.setattr(air_quality, "get_package_resources", lambda _: without_2024_zip)

    with pytest.raises(RuntimeError, match=r"Missing historical files for years: \[2024\]"):
        discover_historical_resources(start_year=2024)


def test_discovery_fails_loudly_without_open_period(monkeypatch):
    without_open = [r for r in PORTAL_RESOURCES if r["format"] != "CSV"]
    monkeypatch.setattr(air_quality, "get_package_resources", lambda _: without_open)

    with pytest.raises(RuntimeError, match="No open"):
        discover_historical_resources(start_year=2024)


# --- Incremental logic ----------------------------------------------------------------


def make_resource(is_open: bool, fingerprint: str = "abc") -> HistoricalResource:
    return HistoricalResource(
        period="desde_2025" if is_open else "2024",
        year=2025 if is_open else 2024,
        is_open=is_open,
        url="https://example.test/file",
        fingerprint=fingerprint,
    )


@pytest.mark.parametrize(
    ("is_open", "stored_fingerprint", "current_fingerprint", "expected"),
    [
        (False, None, "abc", True),  # never downloaded
        (True, None, "abc", True),  # never downloaded
        (False, "abc", "abc", False),  # closed year: downloaded once, never again
        (True, "abc", "abc", False),  # open period unchanged
        (True, "abc", "xyz", True),  # open period changed at the source
        (True, "abc", "", True),  # no fingerprint available: always refresh
    ],
)
def test_should_download(tmp_path, is_open, stored_fingerprint, current_fingerprint, expected):
    if stored_fingerprint is not None:
        (tmp_path / FINGERPRINT_FILE).write_text(stored_fingerprint)

    resource = make_resource(is_open, fingerprint=current_fingerprint)

    assert should_download(resource, tmp_path) is expected


# --- ZIP handling ---------------------------------------------------------------------


def test_save_zip_csvs_keeps_only_csv_members(tmp_path):
    content = make_zip([*MONTHLY_CSVS, "ene_mo24.txt", "ene_mo24.xml"])

    saved = save_zip_csvs(content, tmp_path, source="test.zip")

    assert saved == 12
    assert sorted(p.name for p in tmp_path.iterdir()) == MONTHLY_CSVS


def test_save_zip_csvs_flattens_member_paths(tmp_path):
    """Members with directories (or '..') are written by file name only: no zip slip."""
    target = tmp_path / "target"
    names = [f"../../{MONTHLY_CSVS[0]}", *[f"sub/{n}" for n in MONTHLY_CSVS[1:]]]

    save_zip_csvs(make_zip(names), target, source="test.zip")

    assert sorted(p.name for p in target.iterdir()) == MONTHLY_CSVS
    assert not (tmp_path / MONTHLY_CSVS[0]).exists()


def test_save_zip_csvs_rejects_incomplete_year(tmp_path):
    with pytest.raises(ValueError, match="Expected 12 monthly CSV files"):
        save_zip_csvs(make_zip(MONTHLY_CSVS[:11]), tmp_path, source="test.zip")


def test_save_zip_csvs_rejects_unexpected_header(tmp_path):
    with pytest.raises(ValueError, match="Unexpected content"):
        save_zip_csvs(
            make_zip(MONTHLY_CSVS, content=b"not;a;valid;file\n"), tmp_path, source="test.zip"
        )


# --- End to end: idempotency ----------------------------------------------------------


class FakeFetch:
    """Stand-in for downloader.fetch that serves canned bodies by URL and counts calls."""

    def __init__(self, bodies: dict[str, bytes]):
        self.bodies = bodies
        self.urls: list[str] = []

    def __call__(self, url: str, params: dict | None = None):
        self.urls.append(url)

        class Response:
            content = self.bodies[url]

        return Response()


def test_extract_historical_is_idempotent(monkeypatch, tmp_path):
    resources = [r for r in PORTAL_RESOURCES if r["hierarchy"][0]["hierarchy_name"] != "2023"]
    monkeypatch.setattr(air_quality, "get_package_resources", lambda _: resources)
    monkeypatch.setattr(air_quality, "HISTORICAL_DIR", tmp_path)
    fake_fetch = FakeFetch(
        {
            "https://example.test/2024.zip": make_zip(MONTHLY_CSVS),
            "https://example.test/desde_2025.csv": CSV_CONTENT,
        }
    )
    monkeypatch.setattr(air_quality, "fetch", fake_fetch)

    first_run = extract_historical(start_year=2024)
    second_run = extract_historical(start_year=2024)

    assert len(first_run) == 2
    assert second_run == []
    assert len(fake_fetch.urls) == 2  # nothing downloaded again
    assert (tmp_path / "period=2024" / FINGERPRINT_FILE).exists()
    assert (tmp_path / "period=desde_2025" / "air_quality.csv").read_bytes() == CSV_CONTENT


# --- Real-time (accumulated last 30 days) ---------------------------------------------


def realtime_csv(stations: list[str], days: int = 2) -> bytes:
    rows = [
        f"28;079;{station};08;28079{station}_8_8;2026;10;{day:02d}" + ";10;V" * 24
        for station in stations
        for day in range(1, days + 1)
    ]
    return "\n".join([EXPECTED_HEADER, *rows]).encode()


def test_with_page_size_replaces_existing_value():
    url = "https://example.test/query/data.csv?pageSize=5000&format=csv"

    assert (
        with_page_size(url, 50000)
        == "https://example.test/query/data.csv?format=csv&pageSize=50000"
    )


def test_with_page_size_adds_missing_parameter():
    assert (
        with_page_size("https://example.test/data.csv", 10)
        == "https://example.test/data.csv?pageSize=10"
    )


def test_validate_realtime_file_accepts_complete_file():
    validate_realtime_file(realtime_csv(["4", "8", "11"]), source="test", min_stations=3)


def test_validate_realtime_file_rejects_possibly_truncated_file():
    content = realtime_csv(["4", "8"], days=5)  # 10 rows

    with pytest.raises(ValueError, match="truncated"):
        validate_realtime_file(content, source="test", page_size=10, min_stations=1)


def test_validate_realtime_file_rejects_missing_stations():
    with pytest.raises(ValueError, match="2 stations, expected at least 3"):
        validate_realtime_file(realtime_csv(["4", "8"]), source="test", min_stations=3)


def test_extract_realtime_requests_a_large_page_and_writes_dated_partition(monkeypatch, tmp_path):
    resource = ckan_resource("Tiempo real", "CSV", "https://example.test/rt.csv?pageSize=5000")
    monkeypatch.setattr(air_quality, "get_package_resources", lambda _: [resource])
    monkeypatch.setattr(air_quality, "REALTIME_DIR", tmp_path)
    expected_url = f"https://example.test/rt.csv?pageSize={air_quality.REALTIME_PAGE_SIZE}"
    content = realtime_csv([str(n) for n in range(1, 21)])  # 20 stations
    fake_fetch = FakeFetch({expected_url: content})
    monkeypatch.setattr(air_quality, "fetch", fake_fetch)

    destination = extract_realtime()

    assert fake_fetch.urls == [expected_url]
    assert destination.parent.name.startswith("date=")
    assert destination.read_bytes() == content
