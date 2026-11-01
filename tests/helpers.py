"""Helpers to fake HTTP responses in tests.

HTTP is never called for real in these tests. Fake responses are built as real
`requests.Response` objects, so `raise_for_status()` behaves exactly as in production.
"""

from collections.abc import Iterable

import requests


def make_response(
    status: int = 200,
    content: bytes = b"",
    headers: dict[str, str] | None = None,
    url: str = "https://example.test",
) -> requests.Response:
    """Build a real requests.Response with the given status, body and headers."""
    response = requests.Response()
    response.status_code = status
    response._content = content
    response.headers.update(headers or {})
    response.url = url
    return response


class FakeGet:
    """Stand-in for requests.get that replays a scripted sequence of outcomes.

    Each outcome is either a Response (returned) or an exception (raised).
    Every call is recorded, so tests can assert how many requests were made.
    """

    def __init__(self, outcomes: Iterable[requests.Response | Exception]):
        self._outcomes = list(outcomes)
        self.calls: list[dict] = []

    def __call__(self, url: str, params: dict | None = None, timeout: int | None = None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
