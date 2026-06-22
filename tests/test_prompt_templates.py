"""Tests for the in-repo prompt management system (issue #145).

These pin the *exact* rendered output of each ``.prompty`` template. The whole
point of the migration was to move prompt text out of inline f-strings without
changing a byte of what reaches the model, so the expected strings below are the
pre-migration f-string output verbatim. If a template's whitespace or wording
drifts, these fail.

(Not to be confused with ``test_prompts.py``, which covers the unrelated in-game
``Prompt`` choice mechanism.)
"""

import pytest

from text_adventure_games import prompt_templates
from text_adventure_games.enums import ReActLabel

# The labels are passed into the decision template (not hard-coded there) so
# ReActLabel stays the single source of truth; mirror that here.
_LABELS = {
    "reasoning_label": ReActLabel.REASONING,
    "action_label": ReActLabel.ACTION,
    "duration_label": ReActLabel.DURATION,
}

_INSTRUCTION = (
    "Based on your persona, goals, and the current situation, choose a single "
    "game command to execute. Reply with exactly three lines:\n"
    "Reasoning: <one short sentence explaining your choice>\n"
    "Action: <the command, e.g. 'attack player', 'go north', 'take sword'>\n"
    "Duration: <estimated in-game minutes this action takes, e.g. 5>"
)


# ----------------------------------------------------------------------
# npc_decision: the NPC decision system message
# ----------------------------------------------------------------------


def _decision(persona, goals_block, include_instruction):
    return prompt_templates.render(
        "npc_decision",
        persona=persona,
        goals_block=goals_block,
        include_instruction=include_instruction,
        **_LABELS,
    )


def test_npc_decision_persona_goals_and_instruction():
    out = _decision(
        "I am the troll. I guard the drawbridge.",
        "Short-term:\n  - keep the player off the bridge",
        True,
    )
    assert out == (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am the troll. I guard the drawbridge.\n"
        "Goals:\n"
        "Short-term:\n"
        "  - keep the player off the bridge\n"
        f"{_INSTRUCTION}"
    )


def test_npc_decision_persona_only_with_instruction():
    out = _decision("I am hungry.", "", True)
    assert out == (
        "You are an NPC in a text adventure game.\n"
        "Persona: I am hungry.\n"
        f"{_INSTRUCTION}"
    )


def test_npc_decision_bare_with_instruction():
    # No persona, no goals: just the opening line and the instruction, with no
    # blank lines where the absent sections would have been.
    out = _decision("", "", True)
    assert out == f"You are an NPC in a text adventure game.\n{_INSTRUCTION}"


def test_npc_decision_structured_omits_instruction():
    # The structured tool-calling path renders persona/goals but NOT the
    # Reasoning/Action/Duration instruction (the tool schema is the contract).
    out = _decision("I wander.", "", False)
    assert out == "You are an NPC in a text adventure game.\nPersona: I wander."
    assert "Reasoning:" not in out


def test_npc_decision_instruction_is_not_html_escaped():
    # Jinja autoescaping must be OFF: the angle brackets and apostrophes in the
    # instruction must reach the model raw, not as &lt; / &#39;.
    out = _decision("", "", True)
    assert "<one short sentence explaining your choice>" in out
    assert "'attack player'" in out
    assert "&lt;" not in out and "&#39;" not in out


# ----------------------------------------------------------------------
# Parser narration / matching templates
# ----------------------------------------------------------------------

_NARRATE_OK = (
    "You are the narrator for a text adventure game. You create short, "
    "evocative descriptions of the game. The player can be described in "
    "the 2nd person, and you should use present tense. If a command "
    "doesn't work, tell the player why. If the command is 'look' then "
    "describe the game location and its characters and items."
)


def test_narrate_ok_without_style():
    assert prompt_templates.render("narrate_ok", narration_style=None) == _NARRATE_OK
    # An unset variable behaves the same as an explicit empty one.
    assert prompt_templates.render("narrate_ok") == _NARRATE_OK


def test_narrate_ok_appends_style():
    out = prompt_templates.render(
        "narrate_ok", narration_style="Write in a spooky tone"
    )
    assert out == _NARRATE_OK + "\nWrite in a spooky tone."


def test_narrate_fail():
    assert prompt_templates.render("narrate_fail") == (
        "You are the narrator for a text adventure game. The player attempted a "
        "command that failed in the game. Try to help the player understand "
        "why the command failed."
    )


def test_match_intent():
    assert prompt_templates.render("match_intent") == (
        "You are the parser for a text adventure game. For a user input, say which "
        "of the commands it most closely matches. The commands are:"
    )


def test_match_character_without_hint():
    out = prompt_templates.render("match_character", player_name="hero", hint=None)
    assert out == (
        "You are the parser for a text adventure game. For an input command try to "
        "match the character in the command (if no character is mentioned in the "
        "command, then default to 'hero').\n\nThe possible characters are:"
    )


def test_match_character_with_hint():
    out = prompt_templates.render("match_character", player_name="hero", hint="guard")
    assert out == (
        "You are the parser for a text adventure game. For an input command try to "
        "match the character in the command (if no character is mentioned in the "
        "command, then default to 'hero').\n"
        "Hint: the character you are looking for is the guard.\n\n"
        "The possible characters are:"
    )


def test_match_item_with_and_without_hint():
    base = (
        "You are the parser for a text adventure game. For an input command try to "
        "match the item in the command."
    )
    assert prompt_templates.render("match_item", hint=None) == (
        base + "\n\nThe possible items are:"
    )
    assert prompt_templates.render("match_item", hint="it glows") == (
        base + "\nHint: it glows.\n\nThe possible items are:"
    )


def test_match_direction():
    assert prompt_templates.render("match_direction") == (
        "You are the parser for a text adventure game. For an input command try to "
        "match the direction in the command. Give the closest matching one, or say "
        "None if none match. The possible directions are:"
    )


# ----------------------------------------------------------------------
# Loader behavior
# ----------------------------------------------------------------------


def test_unknown_template_raises_with_available_list():
    with pytest.raises(FileNotFoundError) as excinfo:
        prompt_templates.render("does_not_exist")
    # The error names the missing template and lists what is available, so a
    # typo'd name fails loudly instead of rendering nothing.
    message = str(excinfo.value)
    assert "does_not_exist" in message
    assert "npc_decision" in message


def test_render_ignores_unused_variables():
    # Passing a variable the template never references is harmless.
    assert prompt_templates.render("narrate_fail", unused="ignored").startswith(
        "You are the narrator"
    )
