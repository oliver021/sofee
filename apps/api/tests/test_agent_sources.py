from app.agent.sources import SourceRegistry, finalize, get_registry, release_registry


def _registry_with(*titles: str) -> SourceRegistry:
    registry = SourceRegistry("run-test")
    for title in titles:
        registry.add(kind="kb", title=title, ref=f"/{title}.md")
    return registry


def test_add_numbers_sources_in_order_and_dedupes_by_ref():
    registry = SourceRegistry("run-a")
    first = registry.add(kind="kb", title="Despliegue", ref="/despliegue.md")
    second = registry.add(kind="web", title="Docs", url="https://example.com")
    again = registry.add(kind="kb", title="Despliegue", ref="/despliegue.md")
    assert (first, second, again) == (1, 2, 1)
    assert [s.index for s in registry.sources] == [1, 2]


def test_finalize_renumbers_by_order_of_appearance():
    registry = _registry_with("alfa", "beta", "gamma")
    text = "Primero [3], luego [1] y otra vez [3]."
    renumbered, citations, hallucinated = finalize(text, registry)
    assert renumbered == "Primero [1], luego [2] y otra vez [1]."
    assert [c["index"] for c in citations] == [1, 2]
    assert [c["title"] for c in citations] == ["gamma", "alfa"]
    assert hallucinated == 0


def test_finalize_drops_unknown_numbers_and_counts_them():
    registry = _registry_with("alfa")
    renumbered, citations, hallucinated = finalize("Hecho [1] y falso [9] y [0].", registry)
    assert renumbered == "Hecho [1] y falso  y ."
    assert len(citations) == 1
    assert hallucinated == 2


def test_finalize_leaves_code_spans_untouched():
    registry = _registry_with("alfa")
    text = "Usa `lista[1]` y el bloque:\n```python\nx = arr[1]\n```\nVer [1]."
    renumbered, citations, hallucinated = finalize(text, registry)
    assert "`lista[1]`" in renumbered
    assert "arr[1]" in renumbered
    assert renumbered.endswith("Ver [1].")
    assert len(citations) == 1
    assert hallucinated == 0


def test_finalize_citation_shape():
    registry = SourceRegistry("run-shape")
    registry.add(kind="web", title="Guía", url="https://example.com/g", snippet="texto", ref=None)
    _, citations, _ = finalize("Según [1].", registry)
    assert citations == [
        {
            "index": 1,
            "title": "Guía",
            "url": "https://example.com/g",
            "kind": "web",
            "snippet": "texto",
            "ref": None,
        }
    ]


def test_registry_is_per_run_and_releasable():
    first = get_registry("run-x")
    assert get_registry("run-x") is first
    release_registry("run-x")
    assert get_registry("run-x") is not first
    release_registry("run-x")
