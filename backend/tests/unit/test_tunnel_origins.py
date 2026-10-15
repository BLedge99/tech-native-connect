"""WebSocket handshake origin checks. routers/messaging.py:156.

The tunnel path depends on this: a visitor arriving over Cloudflare sends
`Origin: https://<random>.trycloudflare.com`, and if this rejects it the socket
closes 1008 and live messaging is dead for everyone outside the host machine
while working perfectly on localhost. Pin it.
"""

import pytest

from app.routers.messaging import is_allowed_origin

LOCAL = ["http://localhost:5173"]


@pytest.mark.parametrize(
    "origin",
    [
        "https://random-words-1234.trycloudflare.com",
        "https://a-b-c.trycloudflare.com",
        # Uppercase must still match; urlsplit().hostname is not lowercased
        # for you, the function lowercases it.
        "https://RANDOM-WORDS.trycloudflare.com",
    ],
)
def test_quick_tunnel_origins_are_allowed(origin: str) -> None:
    """This is the whole reason the tunnel works off-host."""
    assert is_allowed_origin(origin, LOCAL) is True


@pytest.mark.parametrize(
    "origin",
    [
        # Suffix confusion. `.endswith(".trycloudflare.com")` is safe here
        # because the leading dot is included — but the attacker controls the
        # whole label, so pin the neighbouring shapes too.
        "https://trycloudflare.com.attacker.test",
        "https://evil-trycloudflare.com.attacker.test",
        "https://attacker.test/x.trycloudflare.com",
        "http://localhost:5173.attacker.test",
    ],
)
def test_lookalike_origins_are_rejected(origin: str) -> None:
    assert is_allowed_origin(origin, LOCAL) is False


def test_unrelated_origin_is_rejected() -> None:
    assert is_allowed_origin("https://someone-elses-app.test", LOCAL) is False


def test_configured_origin_is_allowed() -> None:
    allowed = ["https://app.example.test", "http://localhost:5173"]
    assert is_allowed_origin("https://app.example.test", allowed) is True
    assert is_allowed_origin("https://app.other.test", allowed) is False


@pytest.mark.parametrize("pattern", ["*.example.test", "https://*.example.test"])
def test_wildcard_matches_subdomains_but_not_the_apex(pattern: str) -> None:
    """A leading-dot wildcard means subdomains. The apex is not one — that is
    how this has always behaved and how CORS operators expect it to read."""
    allowed = [pattern]
    assert is_allowed_origin("https://app.example.test", allowed) is True
    assert is_allowed_origin("https://deep.app.example.test", allowed) is True
    assert is_allowed_origin("https://example.test", allowed) is False


@pytest.mark.parametrize("pattern", ["*.example.test", "https://*.example.test"])
def test_wildcard_does_not_match_a_host_that_merely_ends_with_the_label(
    pattern: str,
) -> None:
    """Regression. Matching the bare label without its dot accepted
    `https://notexample.test` for `https://*.example.test`."""
    assert is_allowed_origin("https://notexample.test", [pattern]) is False
    assert is_allowed_origin("https://example.test.attacker.test", [pattern]) is False


def test_star_in_the_list_allows_anything() -> None:
    assert is_allowed_origin("https://anything.test", ["*"]) is True


def test_malformed_origin_is_rejected_rather_than_raising() -> None:
    """A handshake must not be able to 500 the server with a junk Origin."""
    assert is_allowed_origin("not-a-url", LOCAL) is False
    assert is_allowed_origin("", LOCAL) is False