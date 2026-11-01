"""Shared pytest fixtures."""

from collections.abc import Callable, Iterable

import pytest
import requests

from tests.helpers import FakeGet


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Replace time.sleep in the downloader with a recorder, so retry tests run instantly."""
    from madrid_air_quality_pipeline import downloader

    recorded: list[float] = []
    monkeypatch.setattr(downloader.time, "sleep", recorded.append)
    return recorded


@pytest.fixture
def fake_get(monkeypatch) -> Callable[[Iterable], FakeGet]:
    """Install a FakeGet with the given outcomes in place of requests.get."""
    from madrid_air_quality_pipeline import downloader

    def install(outcomes: Iterable[requests.Response | Exception]) -> FakeGet:
        fake = FakeGet(outcomes)
        monkeypatch.setattr(downloader.requests, "get", fake)
        return fake

    return install
