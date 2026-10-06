from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.catalog import ModelCatalogEntry
from ...schemas.catalog import PublicCatalogEntry
from ...services.catalog import entry_is_available
from ..deps import require_user

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("", response_model=list[PublicCatalogEntry])
async def list_catalog(
    _user=Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[PublicCatalogEntry]:
    """El menú de modelos para `apps/web`: entradas curadas, sin providers ni ids
    crudos de modelo. `is_available` refleja si algún binding sirve ahora mismo.
    """
    entries = (
        await db.execute(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.is_enabled.is_(True))
            .order_by(ModelCatalogEntry.sort_order, ModelCatalogEntry.display_name)
        )
    ).scalars()
    return [
        PublicCatalogEntry(
            id=entry.id,
            slug=entry.slug,
            display_name=entry.display_name,
            description=entry.description,
            category=entry.category,
            is_available=await entry_is_available(db, entry.id),
        )
        for entry in entries
    ]
