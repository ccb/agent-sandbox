"""Universal verbs (issue #614): `wait` offered with #581 pacing slots so a
chosen idle settles like `perform`, and agent-initiated `talk_to` that enters
the existing #582/#371 conversation loop.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_universal_verbs_614.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.actions import TalkTo, WaitPenn  # noqa: E402
from backend.build_world import build_world  # noqa: E402
from backend.cognition import action_tools_for, attach_agents  # noqa: E402
from penn_world import PENN_ACTION_VERBS, PENN_EXTRA_ACTIONS  # noqa: E402

_LOCATIONS = [
    {"name": "Plaza", "description": "the plaza", "address": None, "hub": True},
    {"name": "Cafe", "description": "a cafe", "address": "T:Cafe:counter"},
]


def _persona(name):
    return {
        "name": name,
        "home": "Plaza",
        "persona": f"I am {name}.",
        "emoji": "\U0001f9d1",
        "start_tile": [0, 0],
        "destination": "Cafe",
        "activity": "reading",
        "schedule": [
            {"place": "Cafe", "activity": "reading", "emoji": None, "steps": 5}
        ],
    }


def _world(names, extra=None, llm_client=None):
    personas = [_persona(n) for n in names]
    game, chars = build_world(None, personas, _LOCATIONS)
    for cls in PENN_EXTRA_ACTIONS:
        game.parser.add_action(cls)
    attach_agents(
        chars, personas, extra_action_names=extra or [], llm_client=llm_client
    )
    return game, chars


class _ToolBrain:
    """Minimal real-brain stand-in: has call_tools and is not agent.schedule,
    so _use_action_tools is True and the per-action tool path is live."""

    def __init__(self):
        self.context: dict = {}

    def call_tools(self, messages, tools, **kwargs):
        return None  # decline; tests call action_tools_for directly


# ---------------------------------------------------------------- wait offer


def test_wait_is_in_penn_action_verbs():
    assert "wait" in PENN_ACTION_VERBS


def test_wait_penn_is_registered_and_overrides_engine_wait():
    game, _chars = _world(["Ada"])
    assert game.parser.actions["wait"] is WaitPenn


def test_wait_tool_offered_with_pacing_slots():
    game, chars = _world(
        ["Ada"], extra=list(PENN_ACTION_VERBS), llm_client=_ToolBrain()
    )
    tools = {t["name"]: t for t in action_tools_for(game, chars["Ada"])}
    assert "wait" in tools
    props = tools["wait"]["parameters"]["properties"]
    assert "duration_minutes" in props
    assert "emoji" in props
    assert "duration_minutes" in tools["wait"]["parameters"]["required"]


def test_authored_wait_spacers_now_promote_to_action_names():
    personas = [_persona("Ada")]
    personas[0]["schedule"][0]["commands"] = ["wait", "wait"]
    game, chars = build_world(None, personas, _LOCATIONS)
    attach_agents(chars, personas)
    assert "wait" in chars["Ada"].agent.action_names


def test_wait_apply_effects_is_engine_identical_without_a_stash():
    # The mock path (schedule spacers) must be byte-identical: no stashed
    # duration -> no activity stamp, and the engine's "Time passes." message.
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.set_property("activity", "reading")
    assert game.parser.parse_command("wait", actor=ada)
    assert ada.get_property("activity") == "reading"  # untouched


def test_settled_wait_stamps_waiting_activity():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.set_property("activity", "reading")
    ada.agent.last_duration_minutes = 20  # what _take_pacing_args stashes
    assert game.parser.parse_command("wait", actor=ada)
    assert ada.get_property("activity") == "waiting"


# ------------------------------------------------------------ wait memory

from backend.cognition import remember_outcome  # noqa: E402
from backend.prompt_templates import render  # noqa: E402


def test_reflection_template_pins_the_wait_line():
    assert render("reflection", verb="wait") == "I waited; nothing needed doing."


def test_spacer_wait_writes_no_memory():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    remember_outcome(ada, "wait", 3)
    texts = [r.text for r in ada.agent.memory.retrieve(query="waited", turn=3)]
    assert "I waited; nothing needed doing." not in texts


def test_settled_wait_writes_the_honest_idle_memory():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    ada.agent.last_duration_minutes = 20
    remember_outcome(ada, "wait", 3)
    texts = [r.text for r in ada.agent.memory.retrieve(query="waited", turn=3)]
    assert "I waited; nothing needed doing." in texts


# ------------------------------------------------------------ talk_to gate


def _colocate(game, chars, names, place="Plaza"):
    loc = game.locations[place]
    for n in names:
        ch = chars[n]
        if ch.location is not None:
            ch.location.remove_character(ch)
        loc.add_character(ch)


def test_talk_to_is_registered_and_in_penn_action_verbs():
    game, _chars = _world(["Ada"])
    assert game.parser.actions["talk_to"] is TalkTo
    assert "talk_to" in PENN_ACTION_VERBS


def test_talk_to_gate_rejects_an_absent_target_with_actionable_feedback():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada"], "Plaza")
    _colocate(game, chars, ["Bo"], "Cafe")  # not co-located
    ok = game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert not ok
    assert "no one" in game.parser.last_fail_message.lower()
    assert not chars["Ada"].get_property("talk_request")


def test_talk_to_gate_rejects_a_dead_target():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    chars["Bo"].set_property("is_dead", True)
    ok = game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert not ok
    assert "Bo" in game.parser.last_fail_message
    assert not chars["Ada"].get_property("talk_request")


def test_talk_to_success_sets_the_one_shot_markers():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    assert game.parser.parse_command("talk_to Bo about the demo", actor=chars["Ada"])
    assert chars["Ada"].get_property("talk_request") == "Bo"
    assert chars["Ada"].get_property("talk_topic") == "the demo"


def test_talk_to_without_topic_sets_no_topic_marker():
    game, chars = _world(["Ada", "Bo"])
    _colocate(game, chars, ["Ada", "Bo"])
    assert game.parser.parse_command("talk_to Bo", actor=chars["Ada"])
    assert chars["Ada"].get_property("talk_request") == "Bo"
    assert chars["Ada"].get_property("talk_topic") is False  # defaultdict default
