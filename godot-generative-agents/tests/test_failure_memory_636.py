"""Failure memory (issue #636): a gate-blocked action leaves a first-person
"I tried X but it didn't work" memory, so the next decide can steer away
instead of re-choosing the same blocked action forever.

Fully offline. Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_failure_memory_636.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents, remember_outcome  # noqa: E402
from backend.prompt_templates import render  # noqa: E402
from backend.run_simulation import step  # noqa: E402
from backend.sim_config import CognitionConfig  # noqa: E402
from penn_world import PENN_ACTION_VERBS, PENN_EXTRA_ACTIONS  # noqa: E402
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402

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


# --------------------------------------------------------- template phrasing


def test_reflection_template_pins_the_failure_line():
    assert (
        render(
            "reflection",
            failed=True,
            command="talk_to Ghost",
            reason="There's no one here to talk to.",
        )
        == "I tried to \"talk_to Ghost\" but it didn't work: There's no one here to talk to."
    )


def test_failure_phrasing_overrides_the_verb():
    # `failed` short-circuits: a failed travel is NOT rendered as "I traveled".
    assert (
        render(
            "reflection",
            verb="travel",
            location="Mars",
            failed=True,
            command="travel to Mars",
            reason="No path.",
        )
        == 'I tried to "travel to Mars" but it didn\'t work: No path.'
    )


# -------------------------------------------------------- remember_outcome


def test_failed_action_writes_a_failure_memory():
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    remember_outcome(
        ada,
        "get the golden axe",
        5,
        fail_reason="There's no golden axe here.",
    )
    recs = [r for r in ada.agent.memory.records if "golden axe" in r.text]
    assert len(recs) == 1
    assert (
        recs[0].text
        == "I tried to \"get the golden axe\" but it didn't work: There's no golden axe here."
    )
    assert recs[0].importance == 3.0


def test_no_fail_reason_keeps_the_normal_outcome_memory():
    # Backward compatibility: the default (fail_reason=None) path is unchanged --
    # a successful `get` still routes through the existing verb branch.
    game, chars = _world(["Ada"])
    ada = chars["Ada"]
    remember_outcome(ada, "get the golden axe", 5)  # no fail_reason
    texts = [r.text for r in ada.agent.memory.records]
    assert 'I did "get the golden axe".' in texts
    assert not any("didn't work" in t for t in texts)
