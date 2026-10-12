from pydantic import BaseModel, ConfigDict


class MarkReadRequest(BaseModel):
    read: bool

    model_config = ConfigDict(extra="forbid")
