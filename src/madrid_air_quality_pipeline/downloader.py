"""Generic HTTP download with retries, validation and atomic writes."""

import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RATE_LIMIT_WAIT_SECONDS = 60


def fetch(url: str, params: dict | None = None, retries: int = 4, timeout: int = 60) -> requests.Response:
    """GET a URL, retrying only transient failures (rate limits, server and network errors)."""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            status = error.response.status_code if error.response is not None else None
            is_retryable = status is None or status in RETRYABLE_STATUS_CODES
            if not is_retryable or attempt == retries:
                raise

            if status == 429:
                retry_after = error.response.headers.get("Retry-After", "")
                wait_seconds = int(retry_after) if retry_after.isdigit() else RATE_LIMIT_WAIT_SECONDS
            else:
                wait_seconds = 2**attempt

            logger.warning(
                "Attempt %d/%d failed for %s (status %s). Retrying in %ds",
                attempt, retries, url, status, wait_seconds,
            )
            time.sleep(wait_seconds)
    raise RuntimeError("Unreachable")


def validate_header(content: bytes, expected_header: str, source: str) -> None:
    """Fail loudly if the first line does not start with the expected header."""
    lines = content[:2000].decode("utf-8-sig", errors="replace").splitlines()
    first_line = lines[0] if lines else ""
    normalized = first_line.replace('"', "")
    if not normalized.startswith(expected_header):
        raise ValueError(
            f"Unexpected content from {source}. "
            f"Expected header starting with {expected_header!r}, got {first_line[:100]!r}"
        )


def write_atomic(destination: Path, content: bytes) -> None:
    """Write bytes to a temporary file and rename it, so readers never see a partial file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)


def download_file(url: str, destination: Path, expected_header: str | None = None) -> Path:
    """Download a file, optionally validate its header, and save it atomically."""
    content = fetch(url).content
    if expected_header is not None:
        validate_header(content, expected_header, source=url)
    write_atomic(destination, content)
    logger.info("Downloaded %s (%d bytes)", destination, len(content))
    return destination