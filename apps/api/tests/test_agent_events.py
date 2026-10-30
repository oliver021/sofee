"""Mapeo de partes de LangGraph a eventos de Sofee, con partes sintéticas (sin red ni BD)."""

from types import SimpleNamespace

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from app.agent.events import EVENT_TYPES, TERMINAL_EVENTS, RunEventMapper, todo_items


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _chunk(text: str, node: str = "model", agent: str = "sofee-research") -> tuple:
    return (
        AIMessageChunk(content=text),
        {"langgraph_node": node, "lc_agent_name": agent},
    )


def _ai(*calls, name: str | None = None, usage: dict | None = None, content: str = "") -> AIMessage:
    return AIMessage(
        content=content,
        name=name,
        tool_calls=[{"name": n, "args": a, "id": i} for n, a, i in calls],
        usage_metadata=usage,
    )


def _tool(call_id: str, name: str, content: str, status: str = "success") -> ToolMessage:
    return ToolMessage(content=content, tool_call_id=call_id, name=name, status=status)


def _types(events) -> list[str]:
    return [event.type for event in events]


def test_contract_lists_all_event_types_and_terminals():
    assert {"message.delta", "tool.started", "subagent.finished", "interrupt", "usage"} <= EVENT_TYPES
    assert TERMINAL_EVENTS == {"run.completed", "run.failed", "run.cancelled"}
    assert TERMINAL_EVENTS <= EVENT_TYPES


def test_main_agent_tokens_become_message_deltas_and_only_model_node():
    mapper = RunEventMapper()
    events = mapper.map({"type": "messages", "ns": (), "data": _chunk("Hola ")})
    assert [(e.type, e.payload) for e in events] == [("message.delta", {"text": "Hola "})]

    # Los resultados de herramienta llegan también como mensajes: no son texto del asistente.
    tool_chunk = (ToolMessage(content="x", tool_call_id="c1", name="ls"), {"langgraph_node": "tools"})
    assert mapper.map({"type": "messages", "ns": (), "data": tool_chunk}) == []
    # Tokens vacíos (p. ej., solo una llamada a herramienta) no producen delta.
    assert mapper.map({"type": "messages", "ns": (), "data": _chunk("")}) == []


def test_subagent_tokens_are_not_streamed_but_name_is_learned():
    mapper = RunEventMapper()
    ns = ("tools:abc",)
    assert mapper.map({"type": "messages", "ns": ns, "data": _chunk("interno", agent="investigador")}) == []
    # El nombre aprendido de los tokens se usa después para etiquetar las herramientas.
    update = {"model": {"messages": [_ai(("read_file", {"file_path": "/kb/a.md"}, "r1"), name=None)]}}
    events = mapper.map({"type": "updates", "ns": ns, "data": update})
    started = [e for e in events if e.type == "tool.started"]
    assert started[0].payload["agent"] == "investigador"


def test_tool_calls_start_and_finish_with_duration_and_preview():
    clock = FakeClock()
    mapper = RunEventMapper(clock=clock)
    call = _ai(("search_team_docs", {"query": "despliegue"}, "s1"), name="sofee-learn")
    started = mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [call]}}})
    assert _types(started) == ["tool.started"]
    assert started[0].payload == {
        "id": "s1",
        "name": "search_team_docs",
        "agent": "main",
        "args_preview": '{"query": "despliegue"}',
    }

    clock.now += 0.25
    finished = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"messages": [_tool("s1", "search_team_docs", "Fuente [1]: despliegue")]}}}
    )
    assert _types(finished) == ["tool.finished"]
    assert finished[0].payload["status"] == "success"
    assert finished[0].payload["duration_ms"] == 250
    assert finished[0].payload["result_preview"] == "Fuente [1]: despliegue"


def test_missing_file_result_is_an_error_even_with_success_status():
    mapper = RunEventMapper()
    mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [_ai(("read_file", {"file_path": "/kb/no.md"}, "r1"))]}}})
    events = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"messages": [_tool("r1", "read_file", "Error: File '/kb/no.md' not found")]}}}
    )
    assert events[0].payload["status"] == "error"


def test_task_call_opens_and_closes_a_subagent():
    clock = FakeClock()
    mapper = RunEventMapper(clock=clock)
    call = _ai(("task", {"description": "investiga el despliegue", "subagent_type": "investigador"}, "k1"))
    events = mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [call]}}})
    assert _types(events) == ["tool.started", "subagent.started"]
    assert events[1].payload == {"id": "k1", "name": "investigador", "task": "investiga el despliegue"}

    done = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"messages": [_tool("k1", "task", "Resumen [1].")]}}}
    )
    assert _types(done) == ["tool.finished", "subagent.finished"]
    assert done[1].payload == {"id": "k1", "name": "investigador", "status": "success", "summary": "Resumen [1]."}


def test_failed_task_marks_subagent_as_error():
    mapper = RunEventMapper()
    mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [_ai(("task", {"description": "x", "subagent_type": "critico"}, "k2"))]}}})
    done = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"messages": [_tool("k2", "task", "boom", status="error")]}}}
    )
    assert done[-1].payload["status"] == "error"


def test_notes_writes_emit_file_written_and_other_paths_do_not():
    mapper = RunEventMapper()
    write = _ai(
        ("write_file", {"file_path": "/notes/informe.md", "content": "añó"}, "w1"),
        ("write_file", {"file_path": "/workspace/x.md", "content": "no"}, "w2"),
        ("edit_file", {"file_path": "/notes/informe.md", "old_string": "a", "new_string": "b"}, "w3"),
    )
    mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [write]}}})
    events = mapper.map(
        {
            "type": "updates",
            "ns": (),
            "data": {
                "tools": {
                    "messages": [
                        _tool("w1", "write_file", "Updated file /notes/informe.md"),
                        _tool("w2", "write_file", "Updated file /workspace/x.md"),
                        _tool("w3", "edit_file", "Updated file /notes/informe.md"),
                    ]
                }
            },
        }
    )
    written = [e.payload for e in events if e.type == "file.written"]
    # Tamaño en bytes UTF-8 para write_file; edit_file no lo informa y lo completa el executor.
    assert written == [
        {"path": "/notes/informe.md", "size": len("añó".encode("utf-8"))},
        {"path": "/notes/informe.md", "size": None},
    ]


def test_denied_write_is_not_announced():
    mapper = RunEventMapper()
    mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [_ai(("write_file", {"file_path": "/kb/x.md", "content": "y"}, "d1"))]}}})
    events = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"messages": [_tool("d1", "write_file", "Error: permission denied for write on /kb/x.md")]}}}
    )
    assert "file.written" not in _types(events)
    assert events[0].payload["status"] == "error"


def test_todos_only_come_from_the_main_agent():
    mapper = RunEventMapper()
    main = mapper.map(
        {"type": "updates", "ns": (), "data": {"tools": {"todos": [{"content": "buscar", "status": "in_progress"}, {"content": "?", "status": "raro"}], "messages": []}}}
    )
    assert main == [
        main[0].__class__(
            "todos.updated",
            {"items": [{"content": "buscar", "status": "in_progress"}, {"content": "?", "status": "pending"}]},
        )
    ]
    sub = mapper.map({"type": "updates", "ns": ("tools:x",), "data": {"tools": {"todos": [{"content": "sub", "status": "pending"}]}}})
    assert sub == []


def test_usage_reports_totals_and_context_percent_from_last_main_input():
    mapper = RunEventMapper(context_window=1000)
    first = _ai(usage={"input_tokens": 400, "output_tokens": 20, "total_tokens": 420})
    events = mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [first]}}})
    usage = [e for e in events if e.type == "usage"][0]
    assert usage.payload == {"input_tokens": 400, "output_tokens": 20, "context_percent": 40.0}

    sub = _ai(usage={"input_tokens": 100, "output_tokens": 5, "total_tokens": 105})
    events = mapper.map({"type": "updates", "ns": ("tools:s",), "data": {"model": {"messages": [sub]}}})
    usage = [e for e in events if e.type == "usage"][0]
    # Los subagentes suman al total, pero el medidor de contexto sigue la entrada del agente principal.
    assert usage.payload == {"input_tokens": 500, "output_tokens": 25, "context_percent": 40.0}


def test_usage_totals_callable_overrides_internal_sum_and_no_window_gives_null_percent():
    mapper = RunEventMapper(usage_totals=lambda: (7, 3))
    events = mapper.map({"type": "updates", "ns": (), "data": {"model": {"messages": [_ai(usage={"input_tokens": 9, "output_tokens": 1, "total_tokens": 10})]}}})
    usage = [e for e in events if e.type == "usage"][0]
    assert usage.payload == {"input_tokens": 7, "output_tokens": 3, "context_percent": None}


def test_interrupt_maps_the_plan_and_only_the_first_one_counts():
    mapper = RunEventMapper()
    value = {
        "action_requests": [
            {"name": "write_todos", "args": {"todos": [{"content": "buscar", "status": "pending"}]}, "description": "..."}
        ],
        "review_configs": [],
    }
    part = {"type": "updates", "ns": (), "data": {"__interrupt__": (SimpleNamespace(id="i-1", value=value),)}}
    events = mapper.map(part)
    assert [(e.type, e.payload) for e in events] == [
        ("interrupt", {"interrupt_id": "i-1", "kind": "plan_review", "todos": [{"content": "buscar", "status": "pending"}]})
    ]
    assert mapper.interrupted is True
    again = mapper.map({"type": "updates", "ns": (), "data": {"__interrupt__": (SimpleNamespace(id="i-2", value=value),)}})
    assert again == []


def test_custom_events_pass_through_without_the_type_field_and_unknown_ones_are_dropped():
    mapper = RunEventMapper()
    events = mapper.map(
        {"type": "custom", "ns": ("tools:s",), "data": {"type": "source.added", "index": 1, "title": "Doc", "url": None, "kind": "kb", "ref": "/kb/doc.md"}}
    )
    assert [(e.type, e.payload["index"]) for e in events] == [("source.added", 1)]
    assert "type" not in events[0].payload

    assert mapper.map({"type": "custom", "ns": (), "data": {"type": "ui.directions", "items": []}})[0].type == "ui.directions"
    assert mapper.map({"type": "custom", "ns": (), "data": {"type": "algo.raro"}}) == []
    assert mapper.map({"type": "custom", "ns": (), "data": "no es un dict"}) == []


def test_unknown_part_types_and_malformed_updates_are_ignored():
    mapper = RunEventMapper()
    assert mapper.map({"type": "values", "ns": (), "data": {}}) == []
    assert mapper.map({"type": "updates", "ns": (), "data": {"PatchToolCallsMiddleware.before_agent": None}}) == []
    assert mapper.map({"type": "messages", "ns": (), "data": "x"}) == []


def test_todo_items_normalises_statuses():
    assert todo_items(None) == []
    assert todo_items([{"content": "a", "status": "completed"}, "x", {"content": "b"}]) == [
        {"content": "a", "status": "completed"},
        {"content": "b", "status": "pending"},
    ]


def test_text_of_joins_text_blocks_of_list_content():
    from app.agent.events import text_of

    assert text_of([{"type": "text", "text": "Hola "}, {"type": "image_url"}, "mundo"]) == "Hola mundo"
    assert text_of(None) == ""
