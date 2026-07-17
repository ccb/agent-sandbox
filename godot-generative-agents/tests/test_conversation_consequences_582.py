"""Conversation consequences (issue #582).

A meeting can change the rest of the day and the relationship: an agreement
becomes a plan revision, a notable exchange a durable relationship memory. One
structured ``conversation_outcome`` call per participant, at the tail of
``maybe_converse``, only when a real brain drove an actual conversation.

Fully offline (fake brains + fake planners). Run from the repo root::

    PYTHONPATH=.:godot-generative-agents uv run --no-sync pytest \\
        godot-generative-agents/tests/test_conversation_consequences_582.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_pacing_authority_581.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend import cognition  # noqa: E402
from backend.prompt_templates import render  # noqa: E402


def test_trigger_and_importance_constants():
    assert cognition.CONVERSATION == "conversation"
    assert cognition.RELATIONSHIP_NOTE_IMPORTANCE == 8.0


def test_outcome_tool_schema_shape():
    tool = cognition.CONVERSATION_OUTCOME_TOOL
    assert tool["name"] == "conversation_outcome"
    props = tool["parameters"]["properties"]
    assert set(props) == {"plans_changed", "commitment", "relationship_note"}
    assert props["plans_changed"]["type"] == "boolean"
    # Only the yes/no gate is required; the two strings are optional.
    assert tool["parameters"]["required"] == ["plans_changed"]


def test_outcome_prompt_renders_partner_and_transcript():
    text = render(
        "conversation_outcome",
        partner="Ayesha Khan",
        transcript="Maria Lopez: Library at 2?\nAyesha Khan: See you there.",
    )
    assert "Ayesha Khan" in text
    assert "Library at 2?" in text
    assert "See you there." in text
