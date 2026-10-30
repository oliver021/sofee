"""Integraciones externas en el admin. Hoy: la clave de Tavily (búsqueda web del agente).

La clave se cifra como las de los providers, se muestra solo con sus últimos cuatro caracteres
y nunca se escribe en la auditoría ni en la respuesta.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...db import get_session
from ...models.integration import IntegrationCredential
from ...schemas.integration import TavilyKeyIn, TavilyStatusOut, TavilyTestOut
from ...services.audit import write_audit
from ...services.integrations import TAVILY, active_credential, active_secret, store_credential
from ...services.tavily import TavilyError, tavily_search
from ..deps import AuthContext, check_csrf, client_ip, get_current_auth, require_admin

router = APIRouter(
    prefix="/admin/integrations/tavily",
    tags=["integrations-admin"],
    dependencies=[Depends(require_admin)],
)

_TEST_QUERY = "Sofee: prueba de conexión"


def _status(credential: IntegrationCredential | None) -> TavilyStatusOut:
    if credential is None:
        return TavilyStatusOut(configured=False)
    return TavilyStatusOut(
        configured=True,
        last_four=credential.last_four,
        updated_at=credential.created_at,
    )


@router.get("", response_model=TavilyStatusOut)
async def get_tavily_status(db: AsyncSession = Depends(get_session)) -> TavilyStatusOut:
    return _status(await active_credential(db, TAVILY))


@router.put("", response_model=TavilyStatusOut)
async def set_tavily_key(
    payload: TavilyKeyIn,
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> TavilyStatusOut:
    previous = await active_credential(db, TAVILY)
    credential = await store_credential(db, TAVILY, payload.api_key, auth.user.id)
    await write_audit(
        db,
        action="integration.tavily_key_set",
        actor_id=auth.user.id,
        resource_type="integration",
        resource_id=TAVILY,
        data={
            "last_four": credential.last_four,
            "previous_last_four": previous.last_four if previous is not None else None,
        },
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(credential)
    return _status(credential)


@router.post("/test", response_model=TavilyTestOut)
async def test_tavily_key(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    _csrf=Depends(check_csrf),
    db: AsyncSession = Depends(get_session),
) -> TavilyTestOut:
    """Una búsqueda real y trivial con la clave activa. Queda auditada con su resultado."""
    api_key = await active_secret(db, TAVILY)
    if api_key is None:
        result = TavilyTestOut(ok=False, message="No hay ninguna clave configurada.")
    else:
        try:
            results = await tavily_search(api_key, _TEST_QUERY, max_results=1)
            result = TavilyTestOut(ok=True, message=f"Conexión correcta ({len(results)} resultado(s)).")
        except TavilyError as exc:
            result = TavilyTestOut(ok=False, message=str(exc))
    await write_audit(
        db,
        action="integration.tavily_tested",
        actor_id=auth.user.id,
        resource_type="integration",
        resource_id=TAVILY,
        data={"ok": result.ok},
        ip_address=client_ip(request),
    )
    await db.commit()
    return result


__all__ = ["router"]
