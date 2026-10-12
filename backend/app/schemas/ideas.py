from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

IdeaCategory = Literal["find_problem", "build_product", "design_brand", "run_campaign", "other"]


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=50, max_length=2000)
    category: IdeaCategory
    skills_needed: list[str] = Field(default_factory=list, max_length=8)
    course_id: UUID | None = None

    @field_validator("title", "description")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @model_validator(mode="after")
    def validate_trimmed_lengths(self):
        if not 1 <= len(self.title) <= 120:
            raise ValueError("Title must be 1–120 characters.")
        if not 50 <= len(self.description) <= 2000:
            raise ValueError("Description must be 50–2000 characters.")
        return self

    @field_validator("skills_needed")
    @classmethod
    def clean_skills(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 50 for value in cleaned):
            raise ValueError("Use at most 50 characters for each skill.")
        return cleaned

    model_config = ConfigDict(extra="forbid")


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=50, max_length=2000)
    category: IdeaCategory | None = None
    skills_needed: list[str] | None = Field(default=None, max_length=8)
    course_id: UUID | None = None
    is_open: bool | None = None

    @field_validator("title", "description")
    @classmethod
    def trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("skills_needed")
    @classmethod
    def clean_optional_skills(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            raise ValueError("Send an array, or omit the field.")
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 50 for value in cleaned):
            raise ValueError("Use at most 50 characters for each skill.")
        return cleaned

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for name in ("title", "description", "category", "skills_needed"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        if self.title is not None and len(self.title) > 120:
            raise ValueError("Title must be at most 120 characters.")
        if self.description is not None and not 50 <= len(self.description) <= 2000:
            raise ValueError("Description must be 50–2000 characters.")
        return self

    model_config = ConfigDict(extra="forbid")
