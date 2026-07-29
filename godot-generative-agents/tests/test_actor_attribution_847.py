"""Per-actor cost attribution for the plan/reflect role clients (issue #847).

``GET /usage`` ``by_actor`` reads ``CallRecord.actor``, which the client copies
from its ``context["actor"]`` at record time. The decide/outcome/score/converse
sites stamp that actor before each (sequential) call, but the plan and reflect
role clients (``serve_penn._role_client``) are *shared* across the whole cast and
only ever stamped a ``role`` -- so every plan/reflect call recorded
``actor=None`` and its spend fell into the single ``(unattributed)`` bucket.

The fix gives the per-agent :class:`LLMReflector` / :class:`LLMPlanner` their own
``actor`` and has each stamp it onto its (shared) client's ``context`` inside the
one ``_call`` funnel every model request goes through -- so the sequential
reflect/plan calls are attributed to the agent that made them.

Fully offline (fake clients / mock brain). Run from the repo root::

    uv run pytest godot-generative-agents/tests/test_actor_attribution_847.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_cognition_wiring.py: the Penn sim modules run as
# scripts (no package), so tests import them off the sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402
from backend.planner import LLMPlanner  # noqa: E402
from text_adventure_games.planning import DailyPlan  # noqa: E402
from text_adventure_games.reflection import LLMReflector  # noqa: E402


class _CtxClient:
    """A fake ``LlmClient`` with the ``context`` dict the real adapters read at
    record time. Returns ``by_tool[name]`` (default ``{}``) so a plan/reflect
    pass runs its calls but produces nothing usable -- enough to fire ``_call``."""

    def __init__(self, by_tool=None):
        self.context: dict = {}
        self.by_tool = by_tool or {}
        self.calls: list[str] = []

    def call_tool(self, messages, tool, max_tokens=256, temperature=0.0):
        self.calls.append(tool["name"])
        return self.by_tool.get(tool["name"], {})

    def chat(self, *args, **kwargs):
        return None

    def count_tokens(self, text):
        return len(str(text).split())


# --- unit: each cognitive object stamps its own actor onto its client --------


def test_reflector_call_stamps_its_actor():
    client = _CtxClient()
    LLMReflector(client, actor="Diego Torres").salient_questions([])
    assert client.calls  # the reflect call actually fired
    assert client.context.get("actor") == "Diego Torres"


def test_planner_generate_and_revise_stamp_their_actor():
    client = _CtxClient()
    planner = LLMPlanner(client, actor="Sofia Ramirez")

    planner.generate(persona="Sofia")
    assert client.context.get("actor") == "Sofia Ramirez"

    client.context.clear()
    planner.revise(DailyPlan(stops=[]), trigger=None, memory=None)
    assert client.context.get("actor") == "Sofia Ramirez"


def test_no_actor_leaves_context_untouched():
    # Backward compatible: the webapp / tests that build these without an actor
    # (the default) must not start stamping -- context stays exactly as before.
    client = _CtxClient()
    LLMReflector(client).salient_questions([])
    LLMPlanner(client).generate(persona="Ada")
    assert "actor" not in client.context


# --- integration: attach_agents wires char.name through to the role clients --

LOCATIONS = [
    {
        "name": "The Green",
        "description": "the central lawn",
        "address": None,
        "hub": True,
    },
    {"name": "Cafe", "description": "a coffee shop", "address": "T:Cafe:counter"},
]


def _personas():
    return [
        {
            "name": "Ada",
            "home": "The Green",
            "persona": "I am Ada, a curious first-year.",
            "emoji": "\U0001f4d6",
            "start_tile": [0, 0],
            "destination": "Cafe",
            "activity": "reading a novel",
            "schedule": [
                {
                    "place": "Cafe",
                    "activity": "reading a novel",
                    "emoji": "\U0001f4d6",
                    "steps": None,
                }
            ],
        }
    ]


def test_attach_agents_attributes_reflect_and_plan_to_the_agent():
    personas = _personas()
    game, chars = build_world(None, personas, LOCATIONS)
    reflector_client = _CtxClient()
    planner_client = _CtxClient()
    attach_agents(
        chars,
        personas,
        reflector_client=reflector_client,
        planner_client=planner_client,
    )
    ada = chars["Ada"]

    # The per-agent reflector carries the agent's name (stamped on every reflect).
    assert ada.agent.reflector.actor == "Ada"
    # The day plan is generated during the build -> its client was stamped now.
    assert planner_client.context.get("actor") == "Ada"
    assert planner_client.calls  # the plan pass actually ran
