import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ..models.provider import ProviderKind


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: ProviderKind
    base_url: str | None = Field(default=None, max_length=500)
    is_enabled: bool = True
    default_headers: dict[str, str] = {}
    initial_api_key: str | None = Field(default=None, min_length=1, max_length=500)


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=500)
    is_enabled: bool | None = None
    default_headers: dict[str, str] | None = None


class ProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: ProviderKind
    base_url: str | None
    is_enabled: bool
    default_headers: dict | None
    created_at: datetime
    updated_at: datetime
    credential_last_four: str | None = None


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_four: str
    is_active: bool
    created_at: datetime


class CredentialRotateRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


class CredentialRotateResponse(BaseModel):
    credential: CredentialOut
    previous_last_four: str | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    model_id: str
    display_name: str
    is_enabled: bool
    # Aptitud para agentes. `supports_tools` lo fija la prueba del catálogo; null = no probado.
    supports_tools: bool | None = None
    context_window: int | None = None
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None


class ModelCapabilitiesUpdate(BaseModel):
    """Solo se cambian los campos enviados; null borra el dato (queda desconocido)."""

    supports_tools: bool | None = None
    context_window: int | None = Field(default=None, ge=1, le=10_000_000)
    input_price_per_mtok: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    output_price_per_mtok: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)


class ModelToggleRequest(BaseModel):
    is_enabled: bool


class ModelSyncResult(BaseModel):
    created: int
    already_exists: int
    total: int
    models: list[ModelOut]


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    model_count: int = 0


class PublicProviderModel(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    model_id: str
    display_name: str