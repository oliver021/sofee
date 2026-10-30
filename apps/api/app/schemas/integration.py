from datetime import datetime

from pydantic import BaseModel, Field


class TavilyKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


class TavilyStatusOut(BaseModel):
    configured: bool
    last_four: str | None = None
    updated_at: datetime | None = None


class TavilyTestOut(BaseModel):
    ok: bool
    message: str


__all__ = ["TavilyKeyIn", "TavilyStatusOut", "TavilyTestOut"]
