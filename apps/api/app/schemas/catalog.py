import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CatalogBindingCreate(BaseModel):
    provider_model_id: uuid.UUID
    priority: int | None = Field(default=None, ge=0)


class CatalogBindingUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=0)
    is_enabled: bool | None = None


class CatalogBindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_model_id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    model_id: str
    model_display_name: str
    priority: int
    is_enabled: bool
    is_available: bool


class CatalogEntryCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9-]*$")
    display_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    category: str = Field(min_length=1, max_length=50)
    is_enabled: bool = True
    sort_order: int = 0


class CatalogEntryUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    is_enabled: bool | None = None
    sort_order: int | None = None


class CatalogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    display_name: str
    description: str | None
    category: str
    is_enabled: bool
    sort_order: int
    is_available: bool
    created_at: datetime
    updated_at: datetime
    bindings: list[CatalogBindingOut] = []


class PublicCatalogEntry(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    description: str | None
    category: str
    is_available: bool
