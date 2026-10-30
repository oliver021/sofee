from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.catalog import ModelCatalogEntry
from ...schemas.catalog import PublicCatalogEntry
from ...services.catalog import bindings_with_availability, is_agent_ready
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
    ).scalars().all()
    result: list[PublicCatalogEntry] = []
    for entry in entries:
        rows = await bindings_with_availability(db, entry.id)
        usable = [model for _, model, _, available in rows if available]
        result.append(
            PublicCatalogEntry(
                id=entry.id,
                slug=entry.slug,
                display_name=entry.display_name,
                description=entry.description,
                category=entry.category,
                is_available=bool(usable),
                agent_ready=is_agent_ready(rows),
                context_window=usable[0].context_window if usable else None,
            )
        )
    return result
