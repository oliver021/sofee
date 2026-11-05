"""Llamadas a herramientas de UI que el modelo escribe como texto: se recuperan como eventos."""

from app.agent.leaked_calls import recover_leaked_ui_calls
from tests.helpers import authed_client

# Mismos helpers y fixtures que test_knowledge_runs.py.
from tests.test_knowledge_runs import _drain_runs, _events, _run, _thread, use_model  # noqa: F401
from tests.agent_fakes import ai

DIRECTIONS = '{"items": [{"title": "What are its key features?", "why": "It would show how it works."}]}'


def test_a_trailing_call_is_removed_and_returned_as_the_event_the_tool_would_emit():
    text = f"MCP is an open standard [1].\n\nsuggest_directions {DIRECTIONS}"
    clean, events = recover_leaked_ui_calls(text)
    assert clean == "MCP is an open standard [1]."
    assert events == [
        (
            "ui.directions",
            {"items": [{"title": "What are its key features?", "why": "It would show how it works."}]},
        )
    ]


def test_quiz_calls_and_call_syntax_variants_are_recovered_too():
    quiz = '{"items": [{"question": "What is an index?", "answer": "A lookup structure."}]}'
    clean, events = recover_leaked_ui_calls(f"Explanation.\ncheck_understanding({quiz})")
    assert clean == "Explanation."
    assert events[0][0] == "ui.quiz" and events[0][1]["items"][0]["answer"] == "A lookup structure."
    clean, events = recover_leaked_ui_calls(f"Text.\n```json\nsuggest_directions: {DIRECTIONS}\n```")
    assert clean == "Text." and events[0][0] == "ui.directions"
    # El modelo local suele poner el JSON en la línea siguiente al nombre.
    clean, events = recover_leaked_ui_calls(f"Text.\n\nsuggest_directions\n{DIRECTIONS}")
    assert clean == "Text." and events[0][0] == "ui.directions"


def test_anything_that_is_not_a_valid_call_is_left_untouched():
    for text in (
        "I could call suggest_directions here, but I will not.",
        'suggest_directions {"items": []}',  # sin elementos válidos no hay nada que mostrar
        'suggest_directions {"items": [{"title": "only a title"}]}',
        "suggest_directions {not json}",
        "No tool call in this answer at all.",
    ):
        clean, events = recover_leaked_ui_calls(text)
        assert clean == text and events == []


async def test_a_run_whose_model_wrote_the_call_as_text_answers_cleanly_and_emits_the_event(
    client, use_model  # noqa: F811
):
    await authed_client(client)
    await _thread(client, mode="explore")
    run_id = await _run(
        client,
        use_model,
        [ai(f"MCP is an open standard.\n\nsuggest_directions {DIRECTIONS}")],
        mode="explore",
    )
    events = await _events(run_id)

    completed = [p for kind, p in events if kind == "run.completed"][0]
    assert completed["text"] == "MCP is an open standard."
    directions = [p for kind, p in events if kind == "ui.directions"]
    assert [d["items"][0]["title"] for d in directions] == ["What are its key features?"]
    # El evento llega antes de que el run se dé por terminado.
    kinds = [kind for kind, _ in events]
    assert kinds.index("ui.directions") < kinds.index("run.completed")
