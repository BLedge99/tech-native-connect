"""Notification render strings and URL safety. specs/07 §3, §5."""

import pytest

from app.models.enums import NotificationType
from app.services.notifications import RENDER, _safe_url


class FakeRow:
    def __init__(self, type: str, data: dict):
        self.type = type
        self.data = data


def test_every_type_has_a_render_string():
    """A type with no template renders as raw JSON on the page."""
    assert set(RENDER) == {t.value for t in NotificationType}


def test_render_strings_are_personally_addressed():
    for template in RENDER.values():
        assert "{actor}" in template


def test_idea_interest_includes_the_title():
    from app.services.notifications import render_text

    row = FakeRow("idea_interest", {"actor_name": "Sam", "title": "Carbon routing"})
    assert render_text(row) == 'Sam is interested in your idea "Carbon routing"'


def test_unknown_type_falls_back():
    from app.services.notifications import render_text

    row = FakeRow("something_new", {"actor_name": "Sam"})
    assert render_text(row) == "Sam — new activity"


# ─── URL safety ──────────────────────────────────────────────────────────────
# A user-controllable URL on a trusted page is an open-redirect vector.


def test_relative_urls_pass_through():
    assert _safe_url("/connections") == "/connections"


def test_absolute_urls_rejected():
    assert _safe_url("https://evil.com") == "/notifications"


def test_protocol_relative_urls_rejected():
    """//evil.com is the sneaky form."""
    assert _safe_url("//evil.com") == "/notifications"


def test_empty_url_rejected():
    assert _safe_url("") == "/notifications"