"""Tests for the generic HTTP download helpers (decisions 012 and 014)."""

import pytest
import requests

from madrid_air_quality_pipeline.downloader import (
    RATE_LIMIT_WAIT_SECONDS,
    download_file,
    fetch,
    validate_header,
    write_atomic,
)
from tests.helpers import make_response

URL = "https://example.test/data.csv"


# --- fetch: retry policy -----------------------------------------------------------

def test_fetch_returns_response_on_success(fake_get, sleeps):
    fake = fake_get([make_response(200, b"ok")])

    response = fetch(URL)

    assert response.content == b"ok"
    assert len(fake.calls) == 1
    assert sleeps == []


def test_fetch_retries_server_errors_with_exponential_backoff(fake_get, sleeps):
    fake = fake_get([make_response(503), make_response(502), make_response(200, b"ok")])

    response = fetch(URL)

    assert response.content == b"ok"
    assert len(fake.calls) == 3
    assert sleeps == [2, 4]  # 2**1, 2**2


def test_fetch_honours_retry_after_on_rate_limit(fake_get, sleeps):
    fake_get([make_response(429, headers={"Retry-After": "7"}), make_response(200)])

    fetch(URL)

    assert sleeps == [7]


def test_fetch_waits_default_time_on_rate_limit_without_retry_after(fake_get, sleeps):
    fake_get([make_response(429), make_response(200)])

    fetch(URL)

    assert sleeps == [RATE_LIMIT_WAIT_SECONDS]


def test_fetch_retries_network_errors(fake_get, sleeps):
    fake = fake_get([requests.ConnectionError("connection reset"), make_response(200)])

    fetch(URL)

    assert len(fake.calls) == 2


@pytest.mark.parametrize("status", [400, 403, 404])
def test_fetch_fails_fast_on_client_errors(fake_get, sleeps, status):
    fake = fake_get([make_response(status)])

    with pytest.raises(requests.HTTPError):
        fetch(URL)

    assert len(fake.calls) == 1
    assert sleeps == []


def test_fetch_raises_after_last_retry(fake_get, sleeps):
    fake = fake_get([make_response(500)] * 3)

    with pytest.raises(requests.HTTPError):
        fetch(URL, retries=3)

    assert len(fake.calls) == 3
    assert len(sleeps) == 2  # no wait after the final attempt


def test_fetch_always_sets_a_timeout(fake_get, sleeps):
    fake = fake_get([make_response(200)])

    fetch(URL)

    assert fake.calls[0]["timeout"] is not None


# --- validate_header ---------------------------------------------------------------

def test_validate_header_accepts_bom_and_quotes():
    content = '﻿"CODIGO";"CODIGO_CORTO";"ESTACION"\r\n1;2;3\r\n'.encode("utf-8")

    validate_header(content, "CODIGO;CODIGO_CORTO", source="test")  # does not raise


def test_validate_header_rejects_unexpected_content():
    content = b"<html><body>Service unavailable</body></html>"

    with pytest.raises(ValueError, match="Unexpected content"):
        validate_header(content, "CODIGO;CODIGO_CORTO", source="test")


def test_validate_header_rejects_empty_content():
    with pytest.raises(ValueError):
        validate_header(b"", "CODIGO", source="test")


# --- write_atomic / download_file --------------------------------------------------

def test_write_atomic_creates_parents_and_leaves_no_temporary_file(tmp_path):
    destination = tmp_path / "a" / "b" / "file.csv"

    write_atomic(destination, b"content")

    assert destination.read_bytes() == b"content"
    assert list(destination.parent.iterdir()) == [destination]


def test_write_atomic_replaces_existing_file(tmp_path):
    destination = tmp_path / "file.csv"
    destination.write_bytes(b"old")

    write_atomic(destination, b"new")

    assert destination.read_bytes() == b"new"


def test_download_file_does_not_write_invalid_content(fake_get, sleeps, tmp_path):
    fake_get([make_response(200, b"<html>error page</html>")])
    destination = tmp_path / "stations.csv"

    with pytest.raises(ValueError):
        download_file(URL, destination, expected_header="CODIGO")

    assert not destination.exists()


def test_download_file_writes_valid_content(fake_get, sleeps, tmp_path):
    fake_get([make_response(200, b"CODIGO;NAME\n1;A\n")])
    destination = tmp_path / "stations.csv"

    download_file(URL, destination, expected_header="CODIGO")

    assert destination.read_bytes() == b"CODIGO;NAME\n1;A\n"
