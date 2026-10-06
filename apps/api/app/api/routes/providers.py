from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db import get_session
from ...models.provider import Provider, ProviderModel
from ...schemas.provider import PublicProviderModel
from ..deps import require_user

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/models", response_model=list[PublicProviderModel])
async def list_enabled_models(
    _user=Depends(require_user),
    db: AsyncSession = Depends(get_session),
) -> list[PublicProviderModel]:
    """Modelos habilitados de providers habilitados para el selector de `apps/web`.
    No expone credenciales, URLs internas ni metadata de administración.
    """
    rows = (
        await db.execute(
            select(ProviderModel, Provider)
            .join(Provider, Provider.id == ProviderModel.provider_id)
            .where(
                Provider.is_enabled.is_(True),
                ProviderModel.is_enabled.is_(True),
            )
            .order_by(Provider.name, ProviderModel.model_id)
            .options(selectinload(ProviderModel.provider))
        )
    ).all()
    return [
        PublicProviderModel(
            id=model.id,
            provider_id=provider.id,
            provider_name=provider.name,
            model_id=model.model_id,
            display_name=model.display_name,
        )
        for model, provider in rows
    ]