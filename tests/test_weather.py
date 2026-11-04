"""Tests for the weather extraction helpers (decision 013)."""

import json

import pytest

from madrid_air_quality_pipeline.config import WEATHER_VARIABLES
from madrid_air_quality_pipeline.extract.weather import (
    is_complete_year,
    read_stations,
    validate_weather,
)

# --- read_stations --------------------------------------------------------------------


def test_read_stations_handles_bom_and_semicolons(tmp_path):
    path = tmp_path / "stations.csv"
    path.write_bytes(
        "\ufeffCODIGO;CODIGO_CORTO;ALTITUD;LONGITUD;LATITUD\r\n"
        "28079004;4;637,0;-3.7122;40.4239\r\n".encode()
    )

    [station] = read_stations(path)

    assert station.code == "28079004"
    assert station.latitude == pytest.approx(40.4239)
    assert station.longitude == pytest.approx(-3.7122)


def test_read_stations_fails_when_file_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_stations(tmp_path / "missing.csv")


def test_read_stations_fails_when_file_has_no_rows(tmp_path):
    path = tmp_path / "stations.csv"
    path.write_text("CODIGO;LONGITUD;LATITUD\n")

    with pytest.raises(ValueError, match="No stations"):
        read_stations(path)


# --- validate_weather -----------------------------------------------------------------


def make_payload(hours: int = 3) -> dict:
    hourly = {"time": [f"2024-01-01T{h:02d}:00" for h in range(hours)]}
    hourly.update({name: [0.0] * hours for name in WEATHER_VARIABLES})
    return {"hourly": hourly}


def test_validate_weather_accepts_complete_payload():
    validate_weather(make_payload(), source="test")  # does not raise


def test_validate_weather_rejects_missing_variable():
    payload = make_payload()
    del payload["hourly"]["boundary_layer_height"]

    with pytest.raises(ValueError, match="boundary_layer_height"):
        validate_weather(payload, source="test")


def test_validate_weather_rejects_arrays_of_different_length():
    payload = make_payload()
    payload["hourly"]["temperature_2m"].pop()

    with pytest.raises(ValueError, match="different lengths"):
        validate_weather(payload, source="test")


# --- is_complete_year -----------------------------------------------------------------


def write_times(path, times: list[str]) -> None:
    path.write_text(json.dumps({"hourly": {"time": times}}))


def test_year_is_complete_when_it_reaches_december_31_at_23(tmp_path):
    path = tmp_path / "weather.json"
    write_times(path, ["2024-12-31T22:00", "2024-12-31T23:00"])

    assert is_complete_year(path, 2024) is True


def test_year_is_incomplete_when_last_days_are_missing(tmp_path):
    path = tmp_path / "weather.json"
    write_times(path, ["2024-12-29T22:00", "2024-12-29T23:00"])

    assert is_complete_year(path, 2024) is False


def test_year_is_incomplete_when_file_is_missing(tmp_path):
    assert is_complete_year(tmp_path / "missing.json", 2024) is False


def test_year_is_incomplete_when_file_has_no_times(tmp_path):
    path = tmp_path / "weather.json"
    write_times(path, [])

    assert is_complete_year(path, 2024) is False
