# Scripted Full-Feature Mock Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, key-free `--brain scripted` option to the Penn sim that drives every `llm_client`-gated path (per-verb tool loop, cognition tools, conversation, reflection) offline, plus one end-to-end test that asserts each feature is *populated*, not merely shape-valid.

**Architecture:** A new `ScriptedPennBrain` (subclass of the existing `MockLlmClient`) becomes a *distinct* `llm_client` object — distinct from each agent's `ScheduleMockClient`, so the identity gate `_use_action_tools` (`brain is not agent.schedule`) opens and the gated paths run. It follows each persona's authored schedule by reading a `{name: ScheduleMockClient}` map that `attach_agents` registers on it, so agents still reach their rendezvous and conversations fire. `serve_penn.resolve_llm` gains a `"scripted"` outcome; `PennStepper` and `generate_penn_replay.py` build the scripted brain + a scripted reflector under it.

**Tech Stack:** Python 3.12, pytest, the existing `MockLlmClient` / `ToolCallResult` tool-calling stand-in, `uv` for commands.

## Global Constraints

- **Track:** `godot-ga-main` (backend-only). Branch: `feat/scripted-mock-brain-563`, worktree `.claude/worktrees/scripted-mock-563`.
- **No new runtime deps**, no contract change (`backend/contract.py`), no change to real-brain (`--brain llm`) behavior.
- **`--brain mock` bake stays byte-identical** — never touch `ScheduleMockClient` decision logic or the default (no-`llm_client`) path.
- **The scripted responder is a pure function of the prompt + registered schedule state** — never a call-counter (the client is shared across personas and #366 decides in parallel).
- **Determinism:** same run → identical frames.
- Run all commands from the **repo root** `/Users/yh/Documents/GitHub/agent-sandbox`. The Penn sim modules are run as scripts (no package): tests import them off the sim dir via the `sys.path.insert` shim already used in `test_penn_live.py` / `test_cognition_wiring.py`.
- Commit trailer on every commit: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Never `git add -A`/`git add .` — stage explicit paths.
- `#357` repair-round coverage and conversation→relationship-edge coverage are **deferred** (unbuilt upstream) — see the spec.

---

### Task 1: `resolve_llm` gains a `"scripted"` outcome + `--brain scripted` CLI

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`resolve_llm` ~83, the `--brain` argparse ~679, the `start_paused` gate ~757, the ledger `max_cost_usd` read ~309)
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (new)

**Interfaces:**
- Produces: module constant `SCRIPTED = "scripted"` in `serve_penn.py`; `resolve_llm(world_llm, brain, model=None, max_cost=None)` returns `SCRIPTED` when `brain == "scripted"`, `None` for `"mock"`, a `dict` for `"llm"`. Helper `_is_paid(llm) -> bool` (True only for a dict).

- [ ] **Step 1: Write the failing test**

Create `godot-generative-agents/tests/test_scripted_brain.py`:

```python
"""The scripted full-feature mock brain (#563): a deterministic, key-free brain
that reaches every llm_client-gated Penn path. Fully offline. Run from the repo
root::

    uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v
"""

import sys
from pathlib import Path

# Same import shim as test_penn_live.py: the Penn sim modules are run as scripts.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402


def test_resolve_llm_scripted_is_a_distinct_keyless_outcome():
    # scripted is neither the mock None nor a paid dict.
    assert serve_penn.resolve_llm(None, "scripted") == serve_penn.SCRIPTED
    assert serve_penn.resolve_llm(None, "mock") is None
    assert serve_penn._is_paid(serve_penn.resolve_llm(None, "scripted")) is False
    assert serve_penn._is_paid(None) is False
    # scripted needs no key even if the world declares an llm block.
    assert serve_penn.resolve_llm({"provider": "anthropic"}, "scripted") == serve_penn.SCRIPTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: FAIL — `AttributeError: module 'serve_penn' has no attribute 'SCRIPTED'`.

- [ ] **Step 3: Implement the scripted outcome + helper**

In `serve_penn.py`, add the constant near the other module constants (below `DEFAULT_LLM_MODEL`):

```python
# The scripted full-feature mock brain (#563): a deterministic, key-free brain
# that -- unlike the schedule mock -- is a DISTINCT client object, so it opens
# the llm_client-gated paths (tool loop, cognition tools, conversation,
# reflection) offline. resolve_llm returns this sentinel; it is not a paid run.
SCRIPTED = "scripted"


def _is_paid(llm) -> bool:
    """True only for a real, paying LLM config (a dict). None (mock) and the
    SCRIPTED sentinel are free."""
    return isinstance(llm, dict)
```

At the very top of `resolve_llm`'s body, before the `if brain != "llm":` line:

```python
    if brain == "scripted":
        return SCRIPTED
    if brain != "llm":
        return None
```

- [ ] **Step 4: Add the CLI choice**

In the `--brain` argparse block (`ap.add_argument("--brain", choices=("mock", "llm"), ...)`), change `choices` and extend the help:

```python
    ap.add_argument(
        "--brain",
        choices=("mock", "scripted", "llm"),
        default="mock",
        help="mock (default): the deterministic schedule brain -- offline, free, "
        "authored meeting dialogue on. scripted: a deterministic, key-free brain "
        "that drives the full backend offline (tool loop, cognition tools, "
        "conversation, reflection; #563). llm: the model named by the world's "
        "llm: block (Anthropic Claude Haiku) makes every decide/converse/"
        "reflect call; needs ANTHROPIC_API_KEY and `uv sync --extra llm`",
    )
```

- [ ] **Step 5: Fix the paid-only gates so scripted runs free and unpaused**

The `start_paused` default in `main()` currently reads `llm is not None`; the SCRIPTED sentinel is truthy, so it would boot paused. Change it to the paid check:

```python
    start_paused = (
        args.start_paused if args.start_paused is not None else _is_paid(llm)
    )
```

And the ledger cost-ceiling read in `PennStepper.__init__` currently does `(llm or {}).get("max_cost_usd")` — `"scripted".get` would raise. Change it to:

```python
        self.ledger = UsageLedger(  # backs GET /usage across resets
            max_cost_usd=(llm if isinstance(llm, dict) else {}).get("max_cost_usd")
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): resolve_llm 'scripted' outcome + --brain scripted CLI (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `ScriptedPennBrain` — schedule-following decide (travel/perform)

**Files:**
- Create: `godot-generative-agents/backend/penn/scripted_brain.py`
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: `ScheduleMockClient` (from `backend.cognition`) for `.destination` / `.activity`; `MockLlmClient` / `ToolCallResult` (from `text_adventure_games.llm_client`).
- Produces:
  - `class ScriptedPennBrain(MockLlmClient)` with `register_schedule(name: str, schedule) -> None` and an internal `_schedules: dict[str, object]`.
  - Its `call_tools(...)` returns a `ToolCallResult` whose single tool call is `travel` (args `{"destination": <place>, "reasoning": str}`) when the actor is not yet at its scheduled place, else `perform` (args `{"activity": <activity>, "reasoning": str}`). The actor is read from `self.context["actor"]` (the step loop stamps it via `npc._set_attribution`).

- [ ] **Step 1: Write the failing test**

Append to `test_scripted_brain.py`:

```python
from text_adventure_games.llm_client import ToolCallResult  # noqa: E402
from scripted_brain import ScriptedPennBrain  # noqa: E402


class _FakeSchedule:
    """Minimal stand-in for ScheduleMockClient's read surface."""
    def __init__(self, destination, activity):
        self.destination = destination
        self.activity = activity


def _decide_tools():
    # The two universal Penn verbs, shaped like action_tools_for's output.
    return [
        {"name": "travel", "parameters": {"type": "object",
            "properties": {"destination": {"type": "string", "enum": ["Hobbs Cafe"]},
                           "reasoning": {"type": "string"}}}},
        {"name": "perform", "parameters": {"type": "object",
            "properties": {"activity": {"type": "string"},
                           "reasoning": {"type": "string"}}}},
    ]


def _call(brain, observation):
    brain.context["actor"] = "Maya"
    return brain.call_tools(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": observation}],
        _decide_tools(),
        tool_choice="any",
    )


def test_decide_travels_when_not_yet_at_the_scheduled_place():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    result = _call(brain, "THE GREEN\nsome description")  # first line != destination
    assert isinstance(result, ToolCallResult)
    call = result.tool_calls[0]
    assert call["name"] == "travel"
    assert call["arguments"]["destination"] == "Hobbs Cafe"


def test_decide_performs_when_already_at_the_scheduled_place():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    result = _call(brain, "HOBBS CAFE\nsome description")  # first line == destination
    call = result.tool_calls[0]
    assert call["name"] == "perform"
    assert call["arguments"]["activity"] == "reading"


def test_decide_is_deterministic_and_pure_of_call_order():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    a = _call(brain, "THE GREEN\nx").tool_calls[0]
    b = _call(brain, "THE GREEN\nx").tool_calls[0]
    assert a == b  # same prompt -> same call, no hidden counter
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripted_brain'`.

- [ ] **Step 3: Implement the module + decide branch**

Create `godot-generative-agents/backend/penn/scripted_brain.py`:

```python
"""The scripted full-feature mock brain (issue #563).

A deterministic, key-free brain that -- unlike ``ScheduleMockClient`` -- is a
*distinct* client object, so the identity gate ``_use_action_tools`` (``brain is
not agent.schedule``) opens and every ``llm_client``-gated Penn path runs
offline: the per-verb tool loop (#485), cognition tools (#358/#512),
conversation (#86), and reflection (#84).

It follows each persona's authored schedule by reading a ``{name:
ScheduleMockClient}`` map that :func:`backend.cognition.attach_agents` registers
on it, so agents still reach their rendezvous and conversations fire. Every
response is a pure function of the prompt plus that (deterministic) schedule
state -- never a call counter, because the client is shared across personas and
decisions may run in parallel (#366).
"""

from text_adventure_games.llm_client import MockLlmClient


def _first_line_location(observation: str) -> str:
    """``describe_for`` puts the location name (UPPERCASE) on the first non-empty
    line; mirror ``ScheduleMockClient._current_location`` (lowercased)."""
    for line in (observation or "").splitlines():
        if line.strip():
            return line.strip().lower()
    return ""


def _last_user_content(messages) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


class ScriptedPennBrain(MockLlmClient):
    """A distinct ``MockLlmClient`` that follows registered schedules."""

    def __init__(self, ledger=None):
        # Bind our own methods as the responders so MockLlmClient's recording /
        # logging (ledger, tool_calls_log) is reused verbatim. The bound methods
        # close over self, so they can read self.context / self._schedules.
        super().__init__(
            tool_calls_responses=self._on_call_tools,
            tool_responses=self._on_call_tool,
            responses=self._on_chat,
            ledger=ledger,
        )
        self._schedules: dict[str, object] = {}

    def register_schedule(self, name: str, schedule) -> None:
        self._schedules[name] = schedule

    # -- responders ---------------------------------------------------------

    def _on_call_tools(self, messages, tools, tool_choice, max_tokens, temperature):
        # (converse + cognition branches are added in Task 3.)
        return self._decide(messages, tools)

    def _on_call_tool(self, messages, tool, max_tokens, temperature):
        return None  # (speak fallback is added in Task 3.)

    def _on_chat(self, messages, max_tokens, temperature):
        return None  # decide/converse go through the tool routes.

    # -- decide -------------------------------------------------------------

    def _decide(self, messages, tools):
        actor = (self.context or {}).get("actor")
        schedule = self._schedules.get(actor)
        observation = _last_user_content(messages)
        if schedule is None:
            # No schedule registered (safety): act in place so the loop advances.
            return {"tool_calls": [{"name": "perform",
                                    "arguments": {"activity": "looking around",
                                                  "reasoning": "no plan"}}]}
        destination = schedule.destination
        if _first_line_location(observation) != destination.lower():
            return {"tool_calls": [{"name": "travel",
                                    "arguments": {"destination": destination,
                                                  "reasoning": f"heading to {destination}"}}]}
        return {"tool_calls": [{"name": "perform",
                                "arguments": {"activity": schedule.activity,
                                              "reasoning": "settling in"}}]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: PASS (the three new decide tests + Task 1's).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/scripted_brain.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): ScriptedPennBrain schedule-following decide (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: cognition round in decide + the converse (`speak`) branch

**Files:**
- Modify: `godot-generative-agents/backend/penn/scripted_brain.py`
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: the offered `tools` list (names include `recall`/`read_plan` when cognition tools are on; `speak` when it's a conversation).
- Produces: `call_tools` now (a) returns a `recall` call on the *first* decide round when `recall` is offered and no tool result is present yet, then the action on the next round; (b) returns a `speak` call (`{"utterance": str, "done": True}`) when `speak` is among the offered tools. `call_tool` returns `{"utterance": str, "done": True}` for the `speak` tool (the cognition-off converse fallback).

- [ ] **Step 1: Write the failing tests**

Append to `test_scripted_brain.py`:

```python
def _tool_result_msg():
    # Shape run_tool_loop appends after a cognition call (see test_cognition_wiring).
    return {"role": "user", "content": [{"type": "tool_result", "is_error": False,
                                         "content": "a memory"}]}


def test_decide_recalls_first_then_acts_when_cognition_offered():
    brain = ScriptedPennBrain()
    brain.register_schedule("Maya", _FakeSchedule("Hobbs Cafe", "reading"))
    tools = _decide_tools() + [{"name": "recall", "parameters": {"type": "object",
        "properties": {"query": {"type": "string"}}}}]
    brain.context["actor"] = "Maya"
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "THE GREEN\nx"}]
    # Round 1: no tool_result yet -> recall.
    first = brain.call_tools(msgs, tools, tool_choice="any")
    assert first.tool_calls[0]["name"] == "recall"
    # Round 2: a tool_result is present -> the action.
    first_round_call = first.tool_calls[0]
    msgs2 = msgs + [
        {"role": "assistant", "content": [{"type": "tool_use", "name": "recall"}]},
        _tool_result_msg(),
    ]
    second = brain.call_tools(msgs2, tools, tool_choice="any")
    assert second.tool_calls[0]["name"] == "travel"


def test_converse_branch_speaks_when_speak_is_offered():
    brain = ScriptedPennBrain()
    brain.context["actor"] = "Maya"
    speak_tool = {"name": "speak", "parameters": {"type": "object",
        "properties": {"utterance": {"type": "string"}, "done": {"type": "boolean"}}}}
    result = brain.call_tools(
        [{"role": "user", "content": "Priya is here."}], [speak_tool], tool_choice="any")
    call = result.tool_calls[0]
    assert call["name"] == "speak"
    assert call["arguments"]["utterance"]  # non-empty line
    assert call["arguments"]["done"] is True


def test_call_tool_speak_fallback_returns_an_utterance():
    brain = ScriptedPennBrain()
    brain.context["actor"] = "Maya"
    speak_tool = {"name": "speak", "parameters": {"type": "object",
        "properties": {"utterance": {"type": "string"}}}}
    result = brain.call_tool([{"role": "user", "content": "hi"}], speak_tool)
    assert result["utterance"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: FAIL — the converse tests get `travel`/`None` instead of a `speak` call.

- [ ] **Step 3: Implement the cognition + converse branches**

In `scripted_brain.py`, add a helper and rewrite `_on_call_tools` / `_on_call_tool`:

```python
def _has_tool_result(messages) -> bool:
    """True once run_tool_loop has appended a tool_result block (i.e. a cognition
    call already ran this decide episode). Pure function of the prompt."""
    for m in messages or []:
        content = m.get("content")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            return True
    return False


def _line_for(actor) -> str:
    return f"Hello, it's {actor or 'me'} -- good to see you."
```

Replace the body of `_on_call_tools`:

```python
    def _on_call_tools(self, messages, tools, tool_choice, max_tokens, temperature):
        names = {t.get("name") for t in tools}
        if "speak" in names:
            actor = (self.context or {}).get("actor")
            return {"tool_calls": [{"name": "speak",
                                    "arguments": {"utterance": _line_for(actor),
                                                  "done": True}}]}
        # Decide: consult memory once (if offered) before acting, so the
        # cognition-tool path is exercised.
        if "recall" in names and not _has_tool_result(messages):
            return {"tool_calls": [{"name": "recall",
                                    "arguments": {"query": "my plan"}}]}
        return self._decide(messages, tools)
```

And `_on_call_tool`:

```python
    def _on_call_tool(self, messages, tool, max_tokens, temperature):
        if tool.get("name") == "speak":
            actor = (self.context or {}).get("actor")
            return {"utterance": _line_for(actor), "done": True}
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/scripted_brain.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): scripted brain cognition round + converse speak branch (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: scripted reflector + `build_scripted_brains` factory

**Files:**
- Modify: `godot-generative-agents/backend/penn/scripted_brain.py`
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: `LLMReflector`'s tools — `salient_questions` (returns `{"questions": [str,...]}`) and `record_insight` (returns `{"insight": str, "evidence": [int,...]}`), both via `call_tool`.
- Produces: `build_scripted_brains(ledger=None) -> tuple[ScriptedPennBrain, MockLlmClient]` returning `(brain, reflector)`. The reflector is a plain `MockLlmClient` whose `call_tool` responder answers the two reflection tools.

- [ ] **Step 1: Write the failing test**

Append to `test_scripted_brain.py`:

```python
from scripted_brain import build_scripted_brains  # noqa: E402
from text_adventure_games.reflection import SALIENT_QUESTIONS_TOOL, INSIGHT_TOOL  # noqa: E402


def test_build_scripted_brains_returns_brain_and_reflector():
    brain, reflector = build_scripted_brains()
    assert isinstance(brain, ScriptedPennBrain)
    q = reflector.call_tool([{"role": "user", "content": "recent memories"}],
                            SALIENT_QUESTIONS_TOOL)
    assert isinstance(q["questions"], list) and q["questions"]
    i = reflector.call_tool([{"role": "user", "content": "question + memories"}],
                            INSIGHT_TOOL)
    assert i["insight"] and isinstance(i["evidence"], list)


def test_scripted_brains_share_a_ledger_when_passed_one():
    from text_adventure_games.usage import UsageLedger
    ledger = UsageLedger()
    brain, reflector = build_scripted_brains(ledger=ledger)
    assert brain.ledger is ledger and reflector.ledger is ledger
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k build_scripted -v`
Expected: FAIL — `cannot import name 'build_scripted_brains'`.

- [ ] **Step 3: Implement the reflector responder + factory**

Append to `scripted_brain.py`:

```python
def _reflect_responder(messages, tool, max_tokens, temperature):
    """Answer LLMReflector's two tools with schema-valid, deterministic replies."""
    name = tool.get("name")
    if name == "salient_questions":
        return {"questions": ["What am I learning as my day unfolds?"]}
    if name == "record_insight":
        return {"insight": "I move between campus places to keep my plan.",
                "evidence": [1]}
    return None


def build_scripted_brains(ledger=None):
    """Return ``(brain, reflector)`` for a --brain scripted run. Both record into
    ``ledger`` when supplied, so GET /usage / the run log are non-empty offline."""
    brain = ScriptedPennBrain(ledger=ledger)
    reflector = MockLlmClient(tool_responses=_reflect_responder, ledger=ledger)
    return brain, reflector
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -v`
Expected: PASS (all scripted-brain unit tests).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/scripted_brain.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): scripted reflector + build_scripted_brains factory (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `attach_agents` registers each schedule on the brain

**Files:**
- Modify: `godot-generative-agents/backend/cognition.py` (in `attach_agents`, right after `agent.schedule = schedule` ~380)
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: any `llm_client` with a `register_schedule(name, schedule)` method (the `ScriptedPennBrain`); a real client / `None` has no such method.
- Produces: after `attach_agents(chars, personas, llm_client=brain)`, `brain._schedules[name]` is each persona's `ScheduleMockClient`. Guarded by `hasattr`, so real clients and the default mock path are untouched (byte-identical).

- [ ] **Step 1: Write the failing test**

Append to `test_scripted_brain.py`:

```python
from backend.build_world import build_world  # noqa: E402
from backend.cognition import attach_agents  # noqa: E402

_LOCATIONS = [
    {"name": "The Green", "description": "lawn", "address": None, "hub": True},
    {"name": "Cafe", "description": "coffee", "address": "T:Cafe:counter"},
]


def _personas():
    return [{
        "name": "Ada", "home": "The Green", "persona": "I am Ada.",
        "emoji": "\U0001f4d6", "start_tile": [0, 0],
        "destination": "Cafe", "activity": "reading",
        "schedule": [{"place": "Cafe", "activity": "reading",
                      "emoji": "\U0001f4d6", "steps": None}],
    }]


def test_attach_agents_registers_schedules_on_a_scripted_brain():
    brain, _ = build_scripted_brains()
    personas = _personas()
    chars = build_world(None, personas, _LOCATIONS)[1]
    attach_agents(chars, personas, llm_client=brain, cognition_tools=True)
    assert "Ada" in brain._schedules
    assert brain._schedules["Ada"] is chars["Ada"].agent.schedule


def test_attach_agents_is_a_noop_for_a_client_without_register_schedule():
    from text_adventure_games.llm_client import MockLlmClient
    plain = MockLlmClient()  # no register_schedule -> must not raise
    personas = _personas()
    chars = build_world(None, personas, _LOCATIONS)[1]
    attach_agents(chars, personas, llm_client=plain)  # no error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k attach_agents -v`
Expected: FAIL — `'Ada' not in brain._schedules` (nothing registers yet).

- [ ] **Step 3: Implement the registration hook**

In `cognition.py`, find the line `agent.schedule = schedule` (inside the `for spec in personas:` loop, ~380). Immediately after it, add:

```python
        # Scripted brain (#563): a distinct client that follows the authored
        # schedule reads it from here. Guarded so real clients / None / the
        # default mock path are untouched (byte-identical).
        register = getattr(llm_client, "register_schedule", None)
        if callable(register):
            register(char.name, schedule)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k attach_agents -v`
Expected: PASS.

- [ ] **Step 5: Guard the byte-identical default — run the determinism suite**

Run: `uv run pytest godot-generative-agents/tests/test_penn_live.py -v`
Expected: PASS (the mock stepper still reproduces `simulate()` exactly — the new hook is a no-op when `llm_client is None`).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/cognition.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): attach_agents registers schedules on a scripted brain (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `PennStepper` builds the scripted brains under `--brain scripted`

**Files:**
- Modify: `godot-generative-agents/backend/penn/serve_penn.py` (`PennStepper.__init__`, the `if llm is not None:` client-build block ~322-333; the `self.cognition_tools = cognition_tools` line ~303)
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: `build_scripted_brains` (from `scripted_brain`), `SCRIPTED` (module constant).
- Produces: when `llm == SCRIPTED`, `self.llm_client` is a `ScriptedPennBrain`, `self.reflector_client` is the scripted reflector, and `self.cognition_tools is True`; both record into `self.ledger`.

- [ ] **Step 1: Write the failing test**

Append to `test_scripted_brain.py`:

```python
from serve_penn import PennStepper  # noqa: E402


def test_stepper_under_scripted_wires_the_scripted_brains():
    stepper = PennStepper(num_steps=5, llm=serve_penn.SCRIPTED)
    assert isinstance(stepper.llm_client, ScriptedPennBrain)
    assert stepper.reflector_client is not None
    assert stepper.cognition_tools is True
    # The brain got its schedules from _build -> attach_agents.
    assert stepper.llm_client._schedules
    # Both clients record into the run ledger.
    assert stepper.llm_client.ledger is stepper.ledger


def test_stepper_default_mock_is_still_brainless():
    stepper = PennStepper(num_steps=5)  # --brain mock
    assert stepper.llm_client is None
    assert stepper.reflector_client is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k stepper -v`
Expected: FAIL — `stepper.llm_client is None` under scripted (the real-client block skips the sentinel).

- [ ] **Step 3: Implement the scripted branch**

At the top of `serve_penn.py`, add the import alongside the others:

```python
from scripted_brain import build_scripted_brains
```

In `PennStepper.__init__`, the `self.cognition_tools = cognition_tools` line becomes (force it on under scripted so the cognition path runs):

```python
        self.cognition_tools = cognition_tools or (llm == SCRIPTED)
```

Replace the `if llm is not None:` client-build block with a scripted branch first:

```python
        self.llm_client = None
        self.reflector_client = None
        if llm == SCRIPTED:
            # Free, key-free full-feature brain (#563): distinct client objects,
            # so the llm_client-gated paths open; both record into self.ledger.
            self.llm_client, self.reflector_client = build_scripted_brains(
                ledger=self.ledger
            )
        elif llm is not None:
            config = LlmConfig(provider="anthropic", model=llm.get("model"))
            brain_ledger = self._recording_ledger("decide")
            self.llm_client = create_llm_client(config, ledger=brain_ledger)
            ctx = getattr(self.llm_client, "context", None)
            if isinstance(brain_ledger, RoleTaggedLedger) and ctx is not None:
                brain_ledger.bind_context(ctx)
            self.reflector_client = create_llm_client(
                config, ledger=self._recording_ledger("reflect")
            )
        self._build(world)
```

(Delete the old `self.llm_client = None` / `self.reflector_client = None` / `if llm is not None:` lines this replaces — keep the `self._build(world)` call exactly once, at the end.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k stepper -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/backend/penn/serve_penn.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): PennStepper builds scripted brains under --brain scripted (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: bake wiring — `generate_penn_replay.py --brain scripted`

**Files:**
- Modify: `godot-generative-agents/backend/penn/generate_penn_replay.py` (argparse; the `simulate(...)` call ~196)
- Test: `godot-generative-agents/tests/test_scripted_brain.py` (extend)

**Interfaces:**
- Consumes: `build_scripted_brains`; `simulate(..., reflector_client=, llm_client=, cognition=, ledger=)` (already accepts these); `CognitionConfig(cognition_tools=True)` (from `backend.sim_config`); `UsageLedger`.
- Produces: `generate_penn_replay.main()` accepts `--brain {mock,scripted}`; under `scripted` it passes the scripted brain + reflector + `cognition=CognitionConfig(cognition_tools=True)` + a shared `UsageLedger` to `simulate`. `--brain mock` (default) is unchanged (byte-identical bake).

- [ ] **Step 1: Write the failing test**

Append to `test_scripted_brain.py` (drives the bake's inner `simulate` directly, so no file I/O):

```python
def test_bake_simulate_under_scripted_populates_chat_and_reflection():
    from backend.run_simulation import simulate
    from backend.sim_config import CognitionConfig
    from text_adventure_games.usage import UsageLedger
    from penn_world import build_penn_world, PENN_ACTION_VERBS

    pw = build_penn_world()
    brain, reflector = build_scripted_brains()
    ledger = UsageLedger()
    mems: dict = {}
    frames = simulate(
        pw.world_map, 120, ledger=ledger,
        personas=pw.personas, build_world_fn=pw.build_world_fn,
        out_memories=mems, cognition=CognitionConfig(cognition_tools=True),
        reflector_client=reflector, llm_client=brain,
        extra_action_names=PENN_ACTION_VERBS,
    )
    assert frames  # ran to completion offline, no keys
    # The brain reached the tool loop (decide went through call_tools).
    assert brain.tool_calls_log
    # A cognition tool was offered and used at least once.
    assert any("recall" in {t.get("name") for t in c["tools"]}
               for c in brain.tool_calls_log)
    # The ledger recorded calls (non-empty GET /usage surface).
    assert ledger.summary()
```

- [ ] **Step 2: Run test to verify it fails or errors**

Run: `uv run pytest godot-generative-agents/tests/test_scripted_brain.py -k bake_simulate -v`
Expected: PASS or FAIL — this test exercises the wiring `simulate` already supports; if it passes, it proves the responder drives the loop end-to-end. If it FAILs on an assertion, fix the responder before wiring the CLI. (It must be green before Step 3.)

- [ ] **Step 3: Add the `--brain` CLI + scripted branch to the bake**

In `generate_penn_replay.py`, add to its argparse (near the other args):

```python
    ap.add_argument(
        "--brain",
        choices=("mock", "scripted"),
        default="mock",
        help="mock (default): the deterministic schedule brain -- byte-identical "
        "bake. scripted: the key-free full-feature brain (#563) -- bakes a replay "
        "that exercises the tool loop, cognition tools, conversation, reflection.",
    )
```

Replace the `frames = simulate(...)` call so scripted passes the brains + cognition + a ledger:

```python
    from backend.sim_config import CognitionConfig
    from text_adventure_games.usage import UsageLedger
    from scripted_brain import build_scripted_brains

    brain = reflector = None
    cognition = None
    ledger = None
    if args.brain == "scripted":
        ledger = UsageLedger()
        brain, reflector = build_scripted_brains(ledger=ledger)
        cognition = CognitionConfig(cognition_tools=True)

    frames = simulate(
        pw.world_map,
        args.steps,
        ledger=ledger,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        out_memories=memory_streams,
        out_memory_records=memory_records,
        out_events=events,
        extra_action_names=PENN_ACTION_VERBS,
        cognition=cognition,
        reflector_client=reflector,
        llm_client=brain,
    )
```

- [ ] **Step 4: Run the bake both ways (smoke)**

Run:
```bash
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 60 --brain scripted --out /tmp/scripted_replay.json
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 60 --out /tmp/mock_replay.json
```
Expected: both print "Wrote ... (60 steps, ...)" with no key and no network.

- [ ] **Step 5: Confirm the mock bake is byte-identical to before**

Run: `uv run pytest godot-generative-agents/tests/test_replay_contract.py godot-generative-agents/tests/test_export_replay.py -v`
Expected: PASS (the default `--brain mock` bake is unchanged).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/backend/penn/generate_penn_replay.py godot-generative-agents/tests/test_scripted_brain.py
git commit -m "feat(backend): generate_penn_replay --brain scripted bake wiring (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: end-to-end feature-coverage test (`test_full_feature_mock.py`)

**Files:**
- Create: `godot-generative-agents/tests/test_full_feature_mock.py`

**Interfaces:**
- Consumes: `PennStepper(llm=SCRIPTED)`; `serve_penn`; `cognition.memory_stream_for_persona` (returns `[{kind, importance, text, created_turn}]`); `text_adventure_games.memory.MemoryKind`.
- Produces: one test that steps a scripted Penn run to completion and asserts each gated feature is *populated*.

- [ ] **Step 1: Write the test**

Create `godot-generative-agents/tests/test_full_feature_mock.py`:

```python
"""End-to-end feature coverage for the scripted mock brain (#563).

Runs the Penn stepper on --brain scripted to completion and asserts every
llm_client-gated feature is actually POPULATED (not merely contract-shaped):
the tool loop, cognition tools, conversation (CHAT memories), reflection, and a
non-empty usage ledger. This is the test that goes red when the offline mock
drifts behind the backend again. Fully offline -- no keys, no spend.

    uv run pytest godot-generative-agents/tests/test_full_feature_mock.py -v
"""

import sys
from pathlib import Path

_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

import serve_penn  # noqa: E402
from serve_penn import PennStepper  # noqa: E402
from backend.cognition import memory_stream_for_persona  # noqa: E402
from text_adventure_games.memory import MemoryKind  # noqa: E402


def _run(steps=400):
    stepper = PennStepper(num_steps=steps, llm=serve_penn.SCRIPTED)
    for _ in range(steps):
        stepper.tick()
    return stepper


def _all_memories(stepper):
    out = []
    for char in stepper.chars.values():
        out.extend(memory_stream_for_persona(char.agent))
    return out


def test_scripted_run_populates_every_gated_feature():
    stepper = _run()

    # 1. The brain reached the per-verb tool loop (decide went through call_tools).
    assert stepper.llm_client.tool_calls_log, "brain never reached the tool loop"

    # 2. Cognition tools were offered, and a recall call was actually returned
    #    (a request whose messages carry a recall tool_result proves round 2 ran).
    offered_recall = any(
        "recall" in {t.get("name") for t in c["tools"]}
        for c in stepper.llm_client.tool_calls_log
    )
    assert offered_recall, "cognition tools never offered"
    used_recall = any(
        isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_result" for b in m["content"])
        for c in stepper.llm_client.tool_calls_log
        for m in c["messages"]
    )
    assert used_recall, "cognition tool (recall) never actually ran"

    mems = _all_memories(stepper)
    kinds = {m["kind"] for m in mems}

    # 3. Conversation produced CHAT memories (real converse ran, not the injector).
    assert MemoryKind.CHAT.value in kinds, "no CHAT memories -- conversation dark"

    # 4. Reflection wrote memories.
    assert MemoryKind.REFLECTION.value in kinds, "no reflection memories"

    # 5. The usage ledger is non-empty (GET /usage surface populated offline).
    assert stepper.ledger.summary(), "empty usage ledger"


def test_scripted_run_is_deterministic():
    a = _run(steps=120)
    b = _run(steps=120)
    # Same seed/run -> identical memory streams (spot-check the texts).
    assert [m["text"] for m in _all_memories(a)] == [m["text"] for m in _all_memories(b)]
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest godot-generative-agents/tests/test_full_feature_mock.py -v`
Expected: PASS. If an assertion fails, that feature is genuinely dark — fix the responder/wiring, not the assertion.

**Notes for the implementer if an assertion is red:**
- **No CHAT memories:** the active cast may not co-locate in `steps`. Confirm the authored meetings (`build_penn_world().meetings`) put ≥2 active personas at the same place, and that the scripted decide sends them there (it follows `schedule.destination`). Raise `steps` if needed; `generate_penn_replay` defaults to a full day (~400).
- **No REFLECTION:** reflection fires when accumulated importance crosses `DEFAULT_REFLECTION_THRESHOLD`. Confirm the reflector is wired (`stepper.reflector_client is not None`) and enough steps run for memories to accrue.
- **`MemoryKind.CHAT.value` / `.REFLECTION.value` wrong name:** open `text_adventure_games/memory.py`, confirm the enum member names, and use the actual `.value` strings. Do not hardcode a guessed string. The stream dicts from `memory_stream_for_persona` carry `kind` as the enum's `.value`; if it's the enum member itself, compare against `MemoryKind.CHAT` directly.

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/tests/test_full_feature_mock.py
git commit -m "test(backend): end-to-end feature-coverage test for --brain scripted (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: document the third brain

**Files:**
- Modify: `godot-generative-agents/README.md` (the brain/live-mode section that documents `--brain mock` / `--brain llm`)

**Interfaces:** none (docs only).

- [ ] **Step 1: Find the brain docs**

Run: `grep -n "brain mock\|--brain\|brain llm" godot-generative-agents/README.md`
Expected: the section describing `serve_penn.py --brain {mock,llm}`.

- [ ] **Step 2: Add a `--brain scripted` line**

In that section, add (matching the surrounding prose style):

> **`--brain scripted`** — a deterministic, key-free brain that drives the *full*
> backend offline: the per-verb tool loop, cognition tools, conversation, and
> reflection all run (unlike `--brain mock`, which stays on the schedule driver and
> never reaches them). No `ANTHROPIC_API_KEY`, no spend. Use it to exercise or test
> the live-brain code paths without a provider. Works for both `serve_penn.py` and
> `generate_penn_replay.py`. (Issue #563.)

- [ ] **Step 3: Commit**

```bash
git add godot-generative-agents/README.md
git commit -m "docs(backend): document --brain scripted (#563)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (run before opening the PR)

- [ ] `uv run pytest godot-generative-agents/tests/test_scripted_brain.py godot-generative-agents/tests/test_full_feature_mock.py -v` — all green.
- [ ] `uv run pytest godot-generative-agents/tests/test_penn_live.py godot-generative-agents/tests/test_replay_contract.py godot-generative-agents/tests/test_export_replay.py godot-generative-agents/tests/test_cognition_wiring.py -v` — the byte-identical mock bake + contract + existing cognition wiring still green.
- [ ] `uv run pytest tests/ -q` (root engine suite) — green (no engine change, but `attach_agents`/`cognition.py` are imported by root tests via the editable install).
- [ ] `uv run black --check .` — clean.
- [ ] Manual, no key exported: `unset ANTHROPIC_API_KEY; LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/serve_penn.py --brain scripted --steps 60 --tick-seconds 0` boots and runs with zero real calls (the monitor, if `--monitor`, shows only `mock/mock` rows).
- [ ] `git status` shows only: `scripted_brain.py`, `serve_penn.py`, `generate_penn_replay.py`, `cognition.py`, `test_scripted_brain.py`, `test_full_feature_mock.py`, `README.md`, and the two docs/specs+plans files — no minified tmj, no unrelated files.

## Self-Review notes (already reconciled against the spec)

- **Spec coverage:** resolve_llm/CLI (Task 1) · decide (Task 2) · cognition + converse (Task 3) · reflect + factory (Task 4) · schedule registration (Task 5) · stepper (Task 6) · bake (Task 7) · E2E populated-coverage test (Task 8) · README (Task 9). The spec's `#357 repair` and `emergent relationship edge` items are explicitly deferred (unbuilt upstream) — no task, matching the corrected spec.
- **Byte-identical guard** appears as an explicit test step in Tasks 5 and 7.
- **The one unknown left to the implementer** is the exact `MemoryKind` member names in Task 8 — flagged inline with the instruction to read `memory.py` and use real `.value`s, never a guess.
