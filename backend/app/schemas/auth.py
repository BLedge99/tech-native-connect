from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

COMMON_PASSWORDS = {"password", "password123", "12345678", "qwerty123", "letmein123"}


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter at least 2 characters.")
        return value

    @field_validator("password")
    @classmethod
    def reject_common_password(cls, value: str) -> str:
        if value.lower() in COMMON_PASSWORDS:
            raise ValueError("Choose a less common password.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class MagicLinkRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    first_name: str
    is_admin: bool
    profile_complete: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)