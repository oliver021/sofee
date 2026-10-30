# deepagents / LangGraph: API notes

Verified on 2026-10-29 against the installed packages in `apps/api/.venv`:
`deepagents` 0.7.32, `langgraph` 1.2.18, `langchain` 1.4.7, `langchain-core` 1.7.3,
`langchain-openai` 1.7.3, `langgraph-checkpoint-postgres` 3.2.0, `psycopg` 3.3.6.
Where the docs and the installed source disagree, the source wins. Behaviour marked
**verified** was run with a scripted fake chat model (no network); behaviour marked
**source** was read in the installed code and not run. Repo code that depends on
these notes: `apps/api/app/agent/`.

## 1. Import paths

| Symbol | Import |
| --- | --- |
| `create_deep_agent`, `FilesystemPermission`, `HarnessProfile`, `GeneralPurposeSubagentProfile`, `register_harness_profile`, `SubAgent` | `from deepagents import ...` |
| `CompositeBackend`, `StateBackend`, `StoreBackend` | `from deepagents.backends import ...` |
| `TodoListMiddleware`, `HumanInTheLoopMiddleware`, `InterruptOnConfig`, `ModelFallbackMiddleware`, `AgentMiddleware` | `from langchain.agents.middleware import ...` |
| `ToolCallRequest` | `from langchain.agents.middleware.types import ToolCallRequest` |
| `UsageMetadataCallbackHandler` | `from langchain_core.callbacks import UsageMetadataCallbackHandler` |
| `get_stream_writer` | `from langgraph.config import get_stream_writer` |
| `Command` | `from langgraph.types import Command` |
| `Runtime` | `from langgraph.runtime import Runtime` |
| `InMemorySaver` / `InMemoryStore` | `from langgraph.checkpoint.memory import InMemorySaver`, `from langgraph.store.memory import InMemoryStore` |
| `AsyncPostgresSaver` / `AsyncPostgresStore` | `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver`, `from langgraph.store.postgres.aio import AsyncPostgresStore` |

## 2. `create_deep_agent`

Parameters used by the harness: `model`, `tools`, `system_prompt`, `middleware`,
`subagents`, `permissions`, `backend`, `interrupt_on`, `context_schema`,
`checkpointer`, `store`, `name`.

- `system_prompt` is the only authored prompt. The base prompt is empty in 0.7, so every
  profile prompt must explain files, plans, subagents and citations itself. **source**
- The default `recursion_limit` is 9999. An invoke-time `configurable.recursion_limit`
  overrides it. **verified** (limit 6 raised `GraphRecursionError`).
- The `execute` tool is not exposed unless the backend supports execution. The
  `CompositeBackend` of this app does not. **source**

## 3. Planning: `TodoListMiddleware`

- Not added by default. Pass `middleware=[TodoListMiddleware()]` to the main agent and to
  each subagent that should plan. **verified**
- Adds the `write_todos` tool. State key: `todos` (`[{content, status}]`). **verified**
- Without the middleware, `write_todos` is not a tool and the call fails.
  **verified** (state stayed unset).

## 4. Subagents (`SubAgent` TypedDict)

Required: `name`, `description`. Optional: `system_prompt`, `tools`, `model`,
`middleware`, `interrupt_on`, `permissions`, `skills`, `response_format`, `mode`
(`"fork"` is experimental; not used).

- Omitted `tools`, `model`, `permissions` and `interrupt_on` inherit from the top level.
  `permissions` inheritance **verified** (a subagent write to `/kb/` was denied). Others **source**.
- `interrupt_on: {}` on a subagent overrides the inherited top-level config. **source**
  (`spec.get("interrupt_on", interrupt_on)`).
- `middleware` entries are appended after the core stack. They are not inherited from the
  main agent. **source** Same for `ModelFallbackMiddleware` and `SourcesMiddleware`.
- `task` returns the subagent's final text as a `ToolMessage` named `task`. **verified**

## 5. Disabling the auto-added `general-purpose` subagent

`create_deep_agent` adds `general-purpose` unless the active harness profile disables it.
`create_deep_agent` has no flag for this. Use a harness profile keyed by model:

```python
from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile

register_harness_profile(
    "openai:meta-llama/Meta-Llama-3.1-8B-Instruct",
    HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
)
```

- The key is `provider:model`, from `_get_ls_params()["ls_provider"]` and `model_name`.
  `ChatOpenAI` reports provider `openai`. Profiles are global to the process.
  Implemented in `apps/api/app/agent/profiles.py::_disable_general_purpose_subagent`, which
  uses the private helpers `deepagents._models`. **verified**: `task(subagent_type="general-purpose")`
  then returns "the only allowed types are `investigador`, `critico`".
- A subagent named `general-purpose` replaces the default. It does not remove it.

## 6. Backends and namespaces

```python
CompositeBackend(
    default=StateBackend(),
    routes={
        "/kb/": StoreBackend(namespace=lambda rt: ("kb",)),
        "/notes/": StoreBackend(namespace=lambda rt: (rt.context.thread_id, "notes")),
    },
)
```

- Longest prefix wins. The route prefix is stripped before the route backend sees the
  path: `/notes/x.md` reaches `StoreBackend` as key `/x.md`. **verified**
- The namespace factory receives the `Runtime`. `rt.context` is the `context=` passed to
  `ainvoke`/`astream`. It reaches tools of the main agent **and of subagents**. **verified**
- Namespace components must match `^[A-Za-z0-9\-_.@+:~]+$`. **source** UUID thread ids pass.
- Store layout: `store.get(namespace, "/x.md").value` is
  `{"content": str, "encoding": "utf-8", "created_at": iso, "modified_at": iso}`. **verified**
- Other code can write files into the store with the same shape:
  `store.put(("kb",), "/guia.md", {"content": text, "encoding": "utf-8", "created_at": iso, "modified_at": iso})`.
  `read_file("/kb/guia.md")` then returns it. **verified**

## 7. Read-only paths: `FilesystemPermission`

```python
from deepagents import FilesystemPermission

FilesystemPermission(operations=["write"], paths=["/kb/**", "/attachments/**"], mode="deny")
```

- `operations`: `"read"` and/or `"write"`. Writes cover `write_file`, `edit_file` and `delete`.
- `mode`: `"allow"` (default), `"deny"`, or `"interrupt"` (routes through HITL).
- Rules are checked in declaration order; the first match wins. Paths must start with `/`
  and must not contain `..`.
- Denied writes return `Error: permission denied for write on /kb/x.md`. **verified**
- `permissions=` on `create_deep_agent` applies to the main agent and to subagents that
  do not declare their own. **verified**
- This is the read-only guard. No custom `BackendProtocol` is needed.

## 8. Human-in-the-loop

- Pass `interrupt_on={"write_todos": {...}}` to `create_deep_agent`. It becomes a
  `HumanInTheLoopMiddleware` on the main agent.
- Config keys: `allowed_decisions` (`approve`, `edit`, `reject`, `respond`) and `description`.
  `when` exists. **verified**
- `when(req: ToolCallRequest) -> bool`. `req.state` is the agent state at `after_model`;
  `req.runtime.context` is the run context. It runs again on resume and must be
  deterministic.
  **verified**: `when=lambda req: not req.state.get("todos")` interrupts the first plan only.
- Result: `result = await agent.ainvoke(inputs, config, context=ctx, version="v2")`.
  `result.value` holds the state. `result.interrupts` is a tuple of `Interrupt(id, value)`.
  `value["action_requests"]` lists `{name, args, description}`; `value["review_configs"]`
  lists the allowed decisions. **verified**
- Resume: `ainvoke(Command(resume={"decisions": [...]}), config, context=ctx, version="v2")`,
  one decision per action, in order **verified**:
  - `{"type": "approve"}`
  - `{"type": "edit", "edited_action": {"name": "write_todos", "args": {"todos": [...]}}}`
    (the edited plan replaces the original)
  - `{"type": "reject", "message": "..."}`
- A checkpointer and a stable `configurable.thread_id` are required. A run paused on Postgres
  resumes through a new saver object on the same database. **verified**

## 9. Middleware hooks and fallback

- Tool wrapper: `AgentMiddleware.wrap_tool_call(self, request: ToolCallRequest, handler)` and
  `awrap_tool_call`. `request.tool_call` is a dict (`name`, `args`, `id`). `request.runtime.context`
  is available. Return `ToolMessage` or `Command`. Copy a `ToolMessage` with `model_copy(update=...)`. **verified**
- A missing file read returns the **string** `Error: File '<path>' not found` with
  `status="success"`. Check the content, not the status. The path is backend-relative
  (`/no-existe.md`). **verified**
- `ModelFallbackMiddleware(first_model, *more_models)` retries on any exception, with each
  model in order. **verified**: a failing primary was answered by the fallback. Subagents
  do not inherit it; `profiles.py` adds it per subagent.

## 10. Streaming

```python
async for part in agent.astream(
    inputs, config, context=ctx,
    stream_mode=["messages", "updates", "custom"], subgraphs=True, version="v2",
):
    part["type"], part["ns"], part["data"]
```

- `part["type"]` is `messages`, `updates` or `custom`. **verified**
- `messages` data: `(message_chunk, metadata)`. `metadata["langgraph_node"]` is `model` or
  `tools`. `metadata["lc_agent_name"]` is the subagent name, or `None` for the main agent. **verified**
- `updates` data: `{node: update}`. An interrupt appears under the `__interrupt__` key. **verified**
- `custom` data: whatever the tool wrote with `get_stream_writer()(payload)`. **verified**
- `ns == ()` is the main agent. `ns == ("tools:<uuid>",)` is a subagent. Subagent tokens are
  streamed too, so `message.delta` must filter on `ns == ()`. **verified**
- `get_stream_writer()` raises `RuntimeError` outside a graph run. Tools must catch it. **verified**

## 11. Usage

```python
from langchain_core.callbacks import UsageMetadataCallbackHandler

usage = UsageMetadataCallbackHandler()
await agent.ainvoke(inputs, config | {"callbacks": [usage]}, context=ctx, version="v2")
usage.usage_metadata  # {"<model_name>": {"input_tokens": ..., "output_tokens": ..., "total_tokens": ...}}
```

- Totals are keyed by `response_metadata["model_name"]` and include subagent calls when the
  callback is in the run config. **verified** (2 main + 3 subagent calls summed correctly).
- `ChatOpenAI` needs `stream_usage=True` with a custom `base_url`. **source**

## 12. Checkpointer and store

- Tests: `InMemorySaver` and `InMemoryStore`.
- Postgres, psycopg 3 only (LangGraph does not use asyncpg):

```python
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

pool = AsyncConnectionPool(
    conninfo="postgresql://user:pass@host:5432/db",   # no "+asyncpg"
    kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    open=False,
)
await pool.open(wait=True)
saver, store = AsyncPostgresSaver(pool), AsyncPostgresStore(pool)
await saver.setup()   # idempotent
await store.setup()   # idempotent
```

- `setup()` creates `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`, `store` and `store_migrations`. **verified** by
  `python -m app.cli setup-agent-storage` on the dev database. The release runs it, not the server start.
- Both constructors need a running event loop, and `AsyncPostgresStore` starts a background
  task. Create them in the FastAPI lifespan (`apps/api/app/agent/persistence.py`).
- `LANGGRAPH_STRICT_MSGPACK` is read when LangGraph's serde module is imported. It must be set
  before any `langgraph` import: `apps/api/app/agent/__init__.py` does this. **verified**
  (`STRICT_MSGPACK_ENABLED` is `True` afterwards).

## 13. Fake chat models for tests

- `GenericFakeChatModel` drops `tool_calls` when a stream consumer is attached, because its
  `_stream` only yields content and `additional_kwargs`. **source** Do not use it for tool calls.
- Use `apps/api/tests/agent_fakes.py::ScriptedChatModel`. It returns a script of `AIMessage`s
  in order and fails when the script runs out. `bind_tools` returns `self`. `_stream` yields
  text tokens and `tool_call_chunks`. `_get_ls_params` reports provider `openai`, so the
  general-purpose disable key matches. `FailingChatModel` simulates a provider outage.

## 14. ChatOpenAI for the agent

```python
ChatOpenAI(
    model=model_id, base_url=base_url, api_key=api_key, default_headers=headers or None,
    stream_usage=True,
    profile={"max_input_tokens": context_window or 32000, "tool_calling": True},
)
```

**verified**: the constructor accepts `profile` and stores it. Implemented in `apps/api/app/agent/models.py`.

## 15. What exists in apps/api after A1

| Module | Role |
| --- | --- |
| `app/agent/context.py` | `SofeeContext(user_id, thread_id, run_id, mode, locale)` |
| `app/agent/persistence.py` | Postgres or in-memory checkpointer and store; lifespan; `setup_agent_storage` |
| `app/agent/models.py` | `resolve_chat_model` (catalog to `ChatOpenAI`, primary plus fallbacks); `ModelUnavailable` |
| `app/agent/profiles.py` | `DEFAULT_PROFILES` per mode; `load_profile` (DB version over defaults); `build_agent` |
| `app/agent/backends.py` | `make_backend()`; `READ_ONLY_PERMISSIONS` |
| `app/agent/sources.py` | `SourceRegistry` per run; `SourcesMiddleware`; `finalize` |
| `app/agent/tools/` | `get_tools`; `suggest_directions`, `check_understanding` |
| `app/agent/executor.py` | `prepare_run_files` seam (no-op until B2) |

Not in A1: run endpoints, the event mapping (`events.py`), the run executor loop, `web_search`,
`search_team_docs` and the KB tables (B2).

## 16. A2: runs, event mapping and SSE (verified)

Verified on 2026-10-29 with scripted fake models (no network). Code: `apps/api/app/agent/events.py`,
`executor.py`, `history.py`, `apps/api/app/api/routes/runs.py`.

### Corrections to earlier sections

- **§2 and §3.0 (recursion limit).** The key that LangGraph reads is the top-level config key
  `recursion_limit`. `{"configurable": {"recursion_limit": 6}}` has **no effect**: a 20-step script
  ran to exhaustion. `{"recursion_limit": 6}` raises `GraphRecursionError`. A1 was wrong. A2 sets the
  top-level key from `profile.config["limits"]["max_steps"]`.
- **§10 (`lc_agent_name`).** The main agent is not `None`. Its `lc_agent_name` is `sofee-<mode>`, for
  example `sofee-research`. Only `ns == ()` identifies the main agent. Subagents carry their own name,
  for example `investigador`.

### Stream shapes (`astream(version="v2", subgraphs=True, stream_mode=["messages","updates","custom"])`)

- `messages` data is `(AIMessageChunk, metadata)`. Metadata has `langgraph_node` (`model` or `tools`) and
  `lc_agent_name`. Tool results also arrive here as `ToolMessage` chunks: ignore them.
- A subagent's root `ns` is `("tools:<uuid>",)`. Its name is learned from `lc_agent_name` in the
  `messages` part, or from `AIMessage.name` in the `updates` part. The `ns` uuid is not the `task`
  `tool_call_id`.
- `updates` data is `{node: update}`. An `AIMessage` in a `model` update has `.name` (agent name),
  `.tool_calls` and `.usage_metadata`. A `ToolMessage` in a `tools` update has `.tool_call_id`, `.name`
  and `.status`. `write_todos` returns `todos` in the same `tools` update.
- Some updates are `None` (for example `PatchToolCallsMiddleware.before_agent`). Treat them as no-ops.
- `__interrupt__` appears in `updates` as a tuple of `Interrupt(id, value)`. `value["action_requests"]`
  holds `{name, args, description}`. The stream ends right after the interrupt part.
- `aget_state(config).tasks[i].interrupts` gives the same pending interrupts, so resume can build one
  decision per action without keeping state in memory.
- `astream(Command(resume={"decisions": [...]}), ...)` resumes the same graph and works like `ainvoke`.
  After approval the `when` predicate does not interrupt again: the plan now exists in state.
- A missing `/kb/` file returns `"Error: File ... not found"` with `status="success"` (already in §9).

### Usage, errors and streaming

- `openai.InternalServerError` built from an `httpx.Response` is classified as `provider_error`.
  A plain `RuntimeError` from the model is classified as `internal`.
- `UsageMetadataCallbackHandler().usage_metadata` sums per model name. The executor uses it for the
  run's persisted totals. The mapper emits `usage` with those totals and computes `context_percent`
  from the last main-agent `input_tokens` (`AIMessage.usage_metadata`).
- `SecurityHeadersMiddleware` (`BaseHTTPMiddleware`) with Starlette 1.6.0 **does not buffer** an SSE
  body: the first event reaches the client while the run is still running. A client disconnect
  propagates to the generator, which unsubscribes. No rewrite to pure ASGI was needed. Verified in
  `tests/test_agent_runs.py` by driving the ASGI app directly, because `httpx.ASGITransport` waits for
  the whole body.

### Run lifecycle (A2 decisions)

- Assistant text is flushed to `messages.text` at the first delta (status `streaming`), at most once a
  second while streaming, and at every pause or end. `GET /threads/{id}/runs` omits `message.delta`.
  A reader that needs the exact streamed text must replay `GET /runs/{id}/events?after=0`, which
  includes every delta. The `messages` row can lag by up to one second.
- The source registry (`sources.py`) lives in memory. On load, the executor replays the persisted
  `source.added` events in order, so `[n]` numbers survive a resume after a restart.
- `cancel` on a running task cancels the task. `cancel` on a paused run (no task) settles it directly.
  Both paths keep the partial text and set the message to `stopped`.
- On startup, `recover_orphaned_runs()` closes `queued` and `running` runs with no task as failed
  (`internal`, retryable). `interrupted` runs stay resumable. This assumes a single replica.

### Open items after A2

- `max_subagents` and `max_searches` are not enforced. They need the B2 tools.
- `prepare_run_files` is still a no-op (B2).
- `agent.enabled` is checked when a run is created and when it is resumed. A run already in flight is
  not stopped by the switch.
- Starters, quotas and the kill switch are read from `app_settings` by `apps/api/app/services/app_settings.py`.
  The admin side writes them (step C2).
