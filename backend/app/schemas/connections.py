from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectionCreate(BaseModel):
    receiver_id: UUID
    message: str | None = Field(default=None, max_length=300)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    model_config = ConfigDict(extra="forbid")


class ConnectionAction(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def valid_action(cls, value: str) -> str:
        if value not in {"accept", "decline"}:
            raise ValueError("Choose accept or decline.")
        return value

    model_config = ConfigDict(extra="forbid")
