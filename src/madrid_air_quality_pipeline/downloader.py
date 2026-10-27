"""Generic HTTP download with retries, validation and atomic writes."""

import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def fetch(url: str, retries: int = 3, timeout: int = 60) -> requests.Response:
    """GET a URL, retrying on failure with exponential backoff."""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            if attempt == retries:
                raise
            wait_seconds = 2**attempt
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %ds",
                attempt, retries, url, error, wait_seconds,
            )
            time.sleep(wait_seconds)
    raise RuntimeError("Unreachable")


def download_file(url: str, destination: Path, expected_header: str | None = None) -> Path:
    """Download a file and save it atomically, optionally validating its first line."""
    response = fetch(url)
    content = response.content

    if expected_header is not None:
        first_line = content[:2000].decode("utf-8-sig", errors="replace").splitlines()[0]
        if not first_line.startswith(expected_header):
            raise ValueError(
                f"Unexpected content from {url}. "
                f"Expected header starting with {expected_header!r}, got {first_line[:100]!r}"
            )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(destination)

    logger.info("Downloaded %s (%d bytes)", destination, len(content))
    return destination