from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal["software_developer", "business_developer"]


class ProfileUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=500)
    role: Role | None = None
    course_id: UUID | None = None
    looking_for: str | None = Field(default=None, max_length=300)
    skill_ids: list[UUID] | None = Field(default=None, max_length=20)
    interest_ids: list[UUID] | None = Field(default=None, max_length=20)

    @field_validator("bio", "looking_for")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("skill_ids", "interest_ids")
    @classmethod
    def require_arrays_when_present(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value is None:
            raise ValueError("Send an array, or omit the field.")
        return value

    model_config = ConfigDict(extra="forbid")


class NamedReference(BaseModel):
    id: UUID
    name: str
    category: str | None = None
    created_at: datetime | None = None


class CourseReference(BaseModel):
    id: UUID
    name: str


class ProfileFields(BaseModel):
    bio: str | None
    role: Role | None
    course: CourseReference | None
    looking_for: str | None
    skills: list[NamedReference]
    interests: list[NamedReference]
    profile_complete: bool | None = None
    has_photo: bool
    photo_url: str | None


class UserPrivate(BaseModel):
    id: UUID
    email: str
    display_name: str
    first_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    profile_complete: bool
    profile: ProfileFields


class UserPublic(BaseModel):
    id: UUID
    display_name: str
    first_name: str
    profile: ProfileFields
