"""Auth primitives. No database, no HTTP — specs/02 §8."""

import time

from app.errors import CsrfFailed
from app.services.auth import (
    decode_csrf,
    derive_first_name,
    encode_csrf,
    hash_password,
    hash_token,
    new_token,
    normalise_email,
    verify_password,
)
from app.services.auth import check_csrf
from app.services.profiles import sniff_image_type


# ─── Passwords ───────────────────────────────────────────────────────────────


def test_password_hash_is_argon2id():
    hashed = hash_password("correct-horse")
    assert hashed.startswith("$argon2id$")


def test_password_roundtrip():
    hashed = hash_password("correct-horse")
    assert verify_password(hashed, "correct-horse")
    assert not verify_password(hashed, "wrong-horse")


def test_same_password_hashes_differently():
    """Argon2 salts every hash."""
    assert hash_password("x") != hash_password("x")


def test_hash_password_is_not_reversible():
    assert "correct-horse" not in hash_password("correct-horse")


# ─── Tokens ──────────────────────────────────────────────────────────────────


def test_new_token_is_32_random_bytes():
    assert len(new_token()) == 32
    assert new_token() != new_token()


def test_session_token_is_hashed_at_rest():
    """A leaked database dump must not yield live sessions."""
    token = new_token()
    assert hash_token(token) != token
    assert len(hash_token(token)) == 32


# ─── CSRF ────────────────────────────────────────────────────────────────────


class FakeSession:
    def __init__(self, csrf_token: bytes):
        self.csrf_token = csrf_token


def test_csrf_roundtrip():
    token = new_token()
    session = FakeSession(token)
    check_csrf(session, encode_csrf(token))


def test_csrf_missing_rejected():
    import pytest

    with pytest.raises(CsrfFailed):
        check_csrf(FakeSession(new_token()), None)


def test_csrf_wrong_value_rejected():
    import pytest

    with pytest.raises(CsrfFailed):
        check_csrf(FakeSession(new_token()), encode_csrf(new_token()))


def test_csrf_garbage_rejected():
    import pytest

    with pytest.raises(CsrfFailed):
        check_csrf(FakeSession(new_token()), "not-valid-base64!!!")


def test_csrf_encode_decode_roundtrip():
    token = new_token()
    assert decode_csrf(encode_csrf(token)) == token


# ─── Normalisation ───────────────────────────────────────────────────────────


def test_normalise_email_trims_and_lowercases():
    """Whitespace and case must never create a second account."""
    assert normalise_email("  Sam@Example.COM ") == "sam@example.com"


def test_derive_first_name_from_display_name():
    assert derive_first_name("sam@example.com", "Sam Okafor") == "Sam"


def test_derive_first_name_from_email_fallback():
    assert derive_first_name("sam.okafor@example.com", None) == "Sam Okafor"


# ─── Photo type sniffing ─────────────────────────────────────────────────────
# Spec 03 §4: check the bytes, not the header. This is a trust boundary.

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20


def test_sniff_recognises_png():
    assert sniff_image_type(PNG) == "image/png"


def test_sniff_recognises_jpeg():
    assert sniff_image_type(JPEG) == "image/jpeg"


def test_sniff_recognises_webp():
    assert sniff_image_type(WEBP) == "image/webp"


def test_sniff_rejects_shell_script_claiming_png():
    """The exact attack the sniffing exists to stop."""
    assert sniff_image_type(b"#!/bin/sh\nrm -rf /") is None


def test_sniff_rejects_svg_with_script():
    """SVG can carry script. Not on the allowlist."""
    assert sniff_image_type(b'<svg><script>alert(1)</script></svg>') is None


def test_sniff_rejects_pdf():
    assert sniff_image_type(b"%PDF-1.7") is None


def test_sniff_rejects_empty():
    assert sniff_image_type(b"") is None


def test_sniff_rejects_riff_that_is_not_webp():
    assert sniff_image_type(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 20) is None