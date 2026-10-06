import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    id: int
    actor_id: uuid.UUID | None
    actor_email: str | None = None
    action: str
    resource_type: str | None
    resource_id: str | None
    metadata: dict | None
    ip_address: str | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None = None