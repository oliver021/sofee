"""Panel de uso del agente, calculado desde `agent_runs` (roadmap §3.12 y A9).

Todo se agrega en SQL. Los días son UTC. Los percentiles usan `percentile_cont`, que ignora los
nulos: un run sin `ttft_ms` o sin `finished_at` no entra en esa mediana.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ..models.agent import AgentRun
from ..models.provider import Provider, ProviderModel
from ..schemas.agent_admin import (
    LatencyStats,
    UsageBindingRow,
    UsageDayRow,
    UsageModelRow,
    UsageOut,
    UsageTotals,
)

FAILED = "failed"


def window_start(days: int, now: datetime | None = None) -> datetime:
    """Medianoche UTC del primer día de la ventana: `days` días incluido el de hoy."""
    current = now or datetime.now(UTC)
    midnight = current.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=days - 1)


def _money(value: Decimal | float | None) -> float:
    return 0.0 if value is None else float(value)


def _rate(failed: int, runs: int) -> float | None:
    return round(failed / runs, 4) if runs else None


def _latency_columns() -> tuple[ColumnElement[Any], ...]:
    # Duración en milisegundos desde started_at y finished_at; ttft ya está en milisegundos.
    duration_ms = extract("epoch", AgentRun.finished_at - AgentRun.started_at) * 1000
    return (
        func.percentile_cont(0.5).within_group(duration_ms),
        func.percentile_cont(0.95).within_group(duration_ms),
        func.percentile_cont(0.5).within_group(AgentRun.ttft_ms),
        func.percentile_cont(0.95).within_group(AgentRun.ttft_ms),
    )


def _latency(row: Sequence[Any]) -> LatencyStats:
    def ms(value: float | None) -> float | None:
        return None if value is None else round(float(value), 1)

    return LatencyStats(
        duration_p50_ms=ms(row[0]),
        duration_p95_ms=ms(row[1]),
        ttft_p50_ms=ms(row[2]),
        ttft_p95_ms=ms(row[3]),
    )


async def usage_report(db: AsyncSession, *, days: int, now: datetime | None = None) -> UsageOut:
    since = window_start(days, now)
    in_window = AgentRun.created_at >= since

    totals_row = (
        await db.execute(
            select(
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.input_tokens), 0),
                func.coalesce(func.sum(AgentRun.output_tokens), 0),
                func.sum(AgentRun.cost_estimate),
                func.count(AgentRun.id).filter(AgentRun.status == FAILED),
                func.coalesce(func.sum(AgentRun.hallucinated_citations), 0),
                *_latency_columns(),
            ).where(in_window)
        )
    ).one()
    runs = int(totals_row[0])
    failed = int(totals_row[4])
    totals = UsageTotals(
        runs=runs,
        input_tokens=int(totals_row[1]),
        output_tokens=int(totals_row[2]),
        cost_estimate=_money(totals_row[3]),
        failed_runs=failed,
        error_rate=_rate(failed, runs),
        hallucinated_citations=int(totals_row[5]),
    )

    day = func.date(func.timezone("UTC", AgentRun.created_at))
    daily_rows = (
        await db.execute(
            select(
                day,
                AgentRun.catalog_slug,
                AgentRun.model_label,
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.input_tokens), 0),
                func.coalesce(func.sum(AgentRun.output_tokens), 0),
                func.sum(AgentRun.cost_estimate),
            )
            .where(in_window)
            .group_by(day, AgentRun.catalog_slug, AgentRun.model_label)
            .order_by(day, AgentRun.catalog_slug)
        )
    ).all()
    daily = [
        UsageDayRow(
            day=row[0],
            catalog_slug=row[1],
            model_label=row[2],
            runs=int(row[3]),
            input_tokens=int(row[4]),
            output_tokens=int(row[5]),
            cost_estimate=_money(row[6]),
        )
        for row in daily_rows
    ]

    model_rows = (
        await db.execute(
            select(
                AgentRun.catalog_slug,
                AgentRun.model_label,
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.input_tokens), 0),
                func.coalesce(func.sum(AgentRun.output_tokens), 0),
                func.sum(AgentRun.cost_estimate),
            )
            .where(in_window)
            .group_by(AgentRun.catalog_slug, AgentRun.model_label)
            .order_by(func.count(AgentRun.id).desc())
        )
    ).all()
    by_model = [
        UsageModelRow(
            catalog_slug=row[0],
            model_label=row[1],
            runs=int(row[2]),
            input_tokens=int(row[3]),
            output_tokens=int(row[4]),
            cost_estimate=_money(row[5]),
        )
        for row in model_rows
    ]

    binding_rows = (
        await db.execute(
            select(
                AgentRun.provider_model_id,
                ProviderModel.model_id,
                Provider.name,
                func.count(AgentRun.id),
                func.count(AgentRun.id).filter(AgentRun.status == FAILED),
                *_latency_columns(),
            )
            .select_from(AgentRun)
            .outerjoin(ProviderModel, ProviderModel.id == AgentRun.provider_model_id)
            .outerjoin(Provider, Provider.id == ProviderModel.provider_id)
            .where(in_window)
            .group_by(AgentRun.provider_model_id, ProviderModel.model_id, Provider.name)
            .order_by(func.count(AgentRun.id).desc())
        )
    ).all()
    bindings = []
    for row in binding_rows:
        binding_runs = int(row[3])
        binding_failed = int(row[4])
        bindings.append(
            UsageBindingRow(
                provider_model_id=row[0],
                model_id=row[1],
                provider_name=row[2],
                runs=binding_runs,
                failed_runs=binding_failed,
                error_rate=_rate(binding_failed, binding_runs),
                latency=_latency(row[5:]),
            )
        )

    return UsageOut(
        days=days,
        since=since,
        totals=totals,
        latency=_latency(totals_row[6:]),
        daily=daily,
        by_model=by_model,
        bindings=bindings,
    )


__all__ = ["usage_report", "window_start"]
