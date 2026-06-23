"""Tests for the generative-agents prompt templates (issue #145).

These pin the *exact* rendered output of each ``.prompty`` template. The whole
point of the migration was to move the port's agent-generated memory/belief text
out of inline f-strings without changing a byte of what gets stored, so the
expected strings below are the pre-migration f-string output verbatim. If a
template's whitespace or wording drifts, these fail -- and so would the seeding /
memory-wiring tests that assert these same strings end-to-end
(``test_seed_personas.py``, ``test_memory_wiring.py``, ``test_embeddings_in_sim.py``).

Run from ``generative-agents``::

    uv run pytest tests/test_prompt_templates.py -v
"""

import pytest

from backend.prompt_templates import render


# -- plan_memory (smallville_agents.attach_agents) -------------------------------
def test_plan_memory():
    out = render(
        "plan_memory",
        destination="Hobbs Cafe",
        activity="tending the cafe counter",
        itinerary="tending the cafe counter at Hobbs Cafe, then reading at the library",
    )
    assert out == (
        "Plan: go to Hobbs Cafe and tending the cafe counter. "
        "Today's stops: tending the cafe counter at Hobbs Cafe, "
        "then reading at the library."
    )


def test_plan_memory_without_itinerary():
    # Back-compat: the "Today's stops" sentence is dropped when no itinerary.
    out = render(
        "plan_memory",
        destination="Hobbs Cafe",
        activity="tending the cafe counter",
    )
    assert out == "Plan: go to Hobbs Cafe and tending the cafe counter."


# -- reflection (smallville_agents.remember_outcome) -----------------------------
def test_reflection_travel():
    out = render("reflection", verb="travel", location="Hobbs Cafe")
    assert out == "I traveled to Hobbs Cafe."


def test_reflection_perform():
    out = render("reflection", verb="perform", activity="tending the cafe counter")
    assert out == "I am tending the cafe counter."


def test_reflection_other_quotes_the_command_raw():
    # The fallback wraps the raw command in double quotes. Jinja autoescaping must
    # be OFF so the quotes reach memory as `"`, not `&#34;`.
    out = render("reflection", verb="emote", command="dance wildly")
    assert out == 'I did "dance wildly".'
    assert "&#34;" not in out and "&quot;" not in out


# -- spatial_knowledge (seed.seed_spatial_knowledge) -----------------------------
def test_spatial_knowledge_with_areas():
    out = render(
        "spatial_knowledge", place="Oak Hill College", areas="hallway, library"
    )
    assert out == "You know Oak Hill College — its hallway, library."


def test_spatial_knowledge_without_areas():
    out = render("spatial_knowledge", place="Johnson Park", areas="")
    assert out == "You know Johnson Park."


def test_spatial_knowledge_apostrophe_is_raw():
    # The em dash and the apostrophe in the place name must reach the belief raw,
    # not as HTML entities (autoescaping off).
    out = render(
        "spatial_knowledge",
        place="Isabella Rodriguez's apartment",
        areas="main room",
    )
    assert out == "You know Isabella Rodriguez's apartment — its main room."
    assert "&#39;" not in out and "&#x27;" not in out


# -- loader behavior -------------------------------------------------------------
def test_unknown_template_raises_with_available_list():
    with pytest.raises(FileNotFoundError) as excinfo:
        render("does_not_exist")
    message = str(excinfo.value)
    assert "does_not_exist" in message
    assert "plan_memory" in message  # the available list is included


def test_render_ignores_unused_variables():
    out = render("reflection", verb="travel", location="Hobbs Cafe", unused="ignored")
    assert out == "I traveled to Hobbs Cafe."
