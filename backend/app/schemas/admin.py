from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReferenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)

    @field_validator("name", "category")
    @classmethod
    def trim_values(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    model_config = ConfigDict(extra="forbid")


class ReferenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=50)

    @field_validator("name", "category")
    @classmethod
    def trim_values(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_update(self):
        if not self.model_fields_set or (self.name is None and self.category is None):
            raise ValueError("Provide a value to update.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be null.")
        return self

    model_config = ConfigDict(extra="forbid")
