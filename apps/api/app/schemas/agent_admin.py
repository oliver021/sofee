"""Esquemas del admin del agente: perfiles, ajustes, runs, valoraciones, uso y pruebas de aptitud.

Los importes (`cost_estimate`, precios) salen como número en JSON; en la BD son `Numeric`.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..models.user import UserRole
from .agent import RunEventOut
from .catalog import CatalogEntryOut
from .conversation import ComposerMode

# Herramientas que un perfil puede nombrar (ver app/agent/tools). Si el registro cambia, cambia aquí.
ToolName = Literal["search_team_docs", "web_search", "suggest_directions", "check_understanding"]
RunStatus = Literal["queued", "running", "interrupted", "completed", "failed", "cancelled"]
ProbeVerdict = Literal["supports", "no_tool_call", "rejected", "inconclusive", "skipped"]

_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
_Locale = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}(-[A-Za-z]{2,4})?$")]
_Starter = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


# --- perfiles -----------------------------------------------------------------------------


class SubagentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    description: str = Field(min_length=1, max_length=500)
    system_prompt: str = Field(min_length=1, max_length=20_000)
    tools: list[ToolName] = Field(default_factory=list, max_length=10)
    planning: bool = False


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(ge=1, le=200)
    max_seconds: int = Field(ge=10, le=3600)
    max_subagents: int = Field(ge=0, le=5)
    max_searches: int = Field(ge=0, le=50)


class ProfileConfig(BaseModel):
    """Configuración completa de un perfil, tal como se guarda en `agent_profiles.config`."""

    model_config = ConfigDict(extra="forbid")

    tools: list[ToolName] = Field(max_length=10)
    planning: bool
    plan_review: bool
    subagents: list[SubagentConfig] = Field(max_length=5)
    limits: LimitsConfig

    @model_validator(mode="after")
    def _coherent(self) -> "ProfileConfig":
        if self.plan_review and not self.planning:
            raise ValueError("plan_review requires planning")
        names = [subagent.name for subagent in self.subagents]
        if len(set(names)) != len(names):
            raise ValueError("subagent names must be unique")
        return self


class AgentProfileIn(BaseModel):
    """Versión nueva de un perfil. `config` puede ser parcial: lo que falte viene de los defaults."""

    system_prompt: _Text = Field(max_length=20_000)
    config: dict[str, Any] = Field(default_factory=dict)


class ProfileVersionOut(BaseModel):
    # `id`, `version` y `created_at` son null cuando es el default de código (sin fila en la BD).
    id: uuid.UUID | None
    version: int | None
    is_active: bool
    system_prompt: str
    config: dict[str, Any]
    created_by_email: str | None = None
    created_at: datetime | None = None


class AgentProfileOut(BaseModel):
    mode: str
    active: ProfileVersionOut
    history: list[ProfileVersionOut]


# --- ajustes ------------------------------------------------------------------------------


class ReplayEntry(BaseModel):
    prompt: _Text = Field(max_length=500)
    run_id: uuid.UUID


class QuotaLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs_per_day: int | None = Field(default=None, ge=0, le=1_000_000)
    tokens_per_day: int | None = Field(default=None, ge=0, le=1_000_000_000)


class AgentSettings(BaseModel):
    """Ajustes globales del agente. El PUT reemplaza el documento entero (todos los campos son obligatorios)."""

    enabled: bool
    # Modo -> idioma -> preguntas de arranque (tres por modo e idioma en el roadmap, máximo diez).
    starters: dict[ComposerMode, dict[_Locale, Annotated[list[_Starter], Field(max_length=10)]]]
    replay_map: list[ReplayEntry] = Field(max_length=50)
    quotas: dict[UserRole, QuotaLimits]


# --- runs ---------------------------------------------------------------------------------


class AdminRunOut(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None
    kind: str
    mode: str
    status: str
    catalog_slug: str | None
    model_label: str | None
    provider_model_id: uuid.UUID | None
    error_code: str | None
    input_tokens: int
    output_tokens: int
    cost_estimate: float | None
    ttft_ms: int | None
    duration_ms: int | None
    hallucinated_citations: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AdminRunPage(BaseModel):
    items: list[AdminRunOut]
    next_cursor: str | None = None


class AdminRunDetailOut(AdminRunOut):
    # Pregunta del usuario que el run responde, y texto que quedó en el mensaje del asistente.
    question: str | None
    answer: str | None
    citations: list[dict[str, Any]] | None
    error_message: str | None
    profile_version_id: uuid.UUID | None
    profile_version: int | None
    trace_url: str | None
    # Línea de tiempo. Todos los `message.delta` del run van colapsados en uno, con `payload.text`.
    events: list[RunEventOut]


# --- valoraciones -------------------------------------------------------------------------


class AdminFeedbackOut(BaseModel):
    id: uuid.UUID
    value: Literal["good", "bad"]
    reason: str | None
    comment: str | None
    reviewed: bool
    reviewed_at: datetime | None
    created_at: datetime
    user_email: str | None
    thread_id: uuid.UUID
    message_id: uuid.UUID
    run_id: uuid.UUID | None
    question: str | None
    answer: str


class AdminFeedbackPage(BaseModel):
    items: list[AdminFeedbackOut]
    next_cursor: str | None = None


class FeedbackReviewIn(BaseModel):
    reviewed: bool


# --- uso ----------------------------------------------------------------------------------


class UsageTotals(BaseModel):
    runs: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float
    failed_runs: int
    error_rate: float | None
    hallucinated_citations: int


class LatencyStats(BaseModel):
    duration_p50_ms: float | None
    duration_p95_ms: float | None
    ttft_p50_ms: float | None
    ttft_p95_ms: float | None


class UsageDayRow(BaseModel):
    day: date
    catalog_slug: str | None
    model_label: str | None
    runs: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float


class UsageModelRow(BaseModel):
    catalog_slug: str | None
    model_label: str | None
    runs: int
    input_tokens: int
    output_tokens: int
    cost_estimate: float


class UsageBindingRow(BaseModel):
    provider_model_id: uuid.UUID | None
    provider_name: str | None
    model_id: str | None
    runs: int
    failed_runs: int
    error_rate: float | None
    latency: LatencyStats


class UsageOut(BaseModel):
    days: int
    since: datetime
    totals: UsageTotals
    latency: LatencyStats
    daily: list[UsageDayRow]
    by_model: list[UsageModelRow]
    bindings: list[UsageBindingRow]


# --- aptitud para agentes -----------------------------------------------------------------


class AgentTestResultOut(BaseModel):
    binding_id: uuid.UUID
    provider_model_id: uuid.UUID
    provider_name: str
    model_id: str
    verdict: ProbeVerdict
    # Valor de `supports_tools` después de la prueba (puede seguir null si la prueba no fue concluyente).
    supports_tools: bool | None
    message: str
    latency_ms: int | None


class AgentTestOut(BaseModel):
    results: list[AgentTestResultOut]
    agent_ready: bool
    entry: CatalogEntryOut


__all__ = [
    "AdminFeedbackOut",
    "AdminFeedbackPage",
    "AdminRunDetailOut",
    "AdminRunOut",
    "AdminRunPage",
    "AgentProfileIn",
    "AgentProfileOut",
    "AgentSettings",
    "AgentTestOut",
    "AgentTestResultOut",
    "FeedbackReviewIn",
    "LatencyStats",
    "LimitsConfig",
    "ProbeVerdict",
    "ProfileConfig",
    "ProfileVersionOut",
    "QuotaLimits",
    "ReplayEntry",
    "RunStatus",
    "SubagentConfig",
    "ToolName",
    "UsageBindingRow",
    "UsageDayRow",
    "UsageModelRow",
    "UsageOut",
    "UsageTotals",
]
