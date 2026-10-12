import pytest
from argon2 import extract_parameters
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.auth import hash_password, hash_token, verify_password


def test_register_normalises_email_and_name() -> None:
    request = RegisterRequest(email="  Sam@Example.COM ", password="correct-horse", display_name=" Sam Wilson ")

    assert str(request.email) == "sam@example.com"
    assert request.display_name == "Sam Wilson"


@pytest.mark.parametrize("password", ["short12", "password123"])
def test_register_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="sam@example.com", password=password, display_name="Sam")


def test_password_hash_uses_argon2id() -> None:
    password_hash = hash_password("correct-horse")

    assert extract_parameters(password_hash).type.name == "ID"
    assert verify_password(password_hash, "correct-horse")
    assert not verify_password(password_hash, "wrong-password")


def test_session_token_is_hashed_at_rest() -> None:
    raw_token = "this-is-never-stored"

    assert hash_token(raw_token) != raw_token.encode()
    assert len(hash_token(raw_token)) == 32


def test_login_normalises_email() -> None:
    request = LoginRequest(email=" Alice@Example.COM ", password="correct-horse")

    assert str(request.email) == "alice@example.com"