from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def trim_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write a message before sending.")
        return value

    model_config = ConfigDict(extra="forbid")
