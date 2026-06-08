# Output & Agent-Trace Rendering — Design

**Status:** Proposal — not yet adopted. A design doc for discussion, not a
description of current behavior.

**Author:** Alistair King.

*A unified design for how the engine surfaces (1) what's happening in the game and
(2) what the agents are thinking and doing. It promotes the web UI's message types
into a first-class engine concept and renders them well on every surface — the human
terminal, the notebooks, the web app, and (later) a 2D renderer. This is the
**Presentation** layer sketched in
[multi-character-play.md](multi-character-play.md) §5 and the `reporting.py`
("Message, Reporter — decouple output from effects") named in its appendix.*

---

## 1. What we're building

One typed **`Message`** for everything the engine wants to show, and a pluggable
**`Renderer`** that turns those messages into output for a specific surface. The
engine decides *what* happened and *what kind* of information it is; the renderer
decides *how it looks*. Swap the renderer and the same game prints colored,
turn-structured text in a terminal, buffers HTML-ready dicts for the web app, or
emits structured JSON for a renderer — without the game loop or the parser knowing
which.

This is the top layer of the stack from
[multi-character-play.md](multi-character-play.md); everything below it already
exists or is being built:

```
┌─────────────────────────────────────────────────────────┐
│  Presentation   Message + Renderer: terminal · web · JSON │  ← THIS DOC
├─────────────────────────────────────────────────────────┤
│  Agents         persona, goals, ReAct (Observe→…→Reflect) │
├─────────────────────────────────────────────────────────┤
│  Orchestration  turn loop · phases · events · time        │
├─────────────────────────────────────────────────────────┤
│  World model    Location · Item · Character · Action       │
└─────────────────────────────────────────────────────────┘
```

The win is concentrated where the team actually demos and debugs agents — the
terminal and notebooks (`Game.game_loop`, `notebooks/hw1_llm/play.py`,
`test_npc_behaviors.py`) — which today are the weakest surface.

---

## 2. The problem today

Output works, but it's uneven and duplicated. The engine emits text through four
parser methods — `ok()` (success narration), `fail()` (a blocked action),
`npc_ok()` (an NPC's action), and `npc_log()` (an agent's private reasoning/action
trace) — and each of the four parser classes implements them again:

| Parser class | Where | How it outputs |
|--------------|-------|----------------|
| `Parser` | `parsing.py` | `print(wrap_text(...))` — one monochrome stream |
| `WebParser` | `webapp/web_parser.py` | appends `{"type", "text"}` dicts, tagged by kind |
| `LlmParser` | `llm_parser.py` | narrates via the LLM, then `print(...)` |
| `WebLlmParser` | `llm_parser.py` | narrates, then appends `{"type", "text"}` dicts |

Concrete problems this causes:

- **The terminal is monochrome.** In `Parser`, `ok` / `fail` / `npc_ok` /
  `npc_log` all funnel into the same `print(wrap_text(...))`. Game narration, the
  player's command, an error, an NPC's action, and an agent's *private* reasoning
  all look identical. The reader can't tell a troll's inner thought from the room
  description.
- **No turn structure.** When the player types `wait`, the troll's reasoning, its
  action, and the resulting narration print back-to-back with no "Turn N" marker
  and no per-character grouping. With several NPCs it becomes an undifferentiated
  wall of text.
- **The taxonomy is web-only.** `WebParser` already knows messages come in kinds —
  `output`, `command`, `error`, `npc_action`, `npc_log` — and `static/style.css`
  color-codes them (green narration, yellow commands, red errors, purple NPC
  actions, gray agent traces). But that knowledge lives in the web subclass. The
  base `Parser` throws it away, so the terminal *cannot* make the same
  distinctions even though the information exists one layer up.
- **The ReAct trace is flat.** `npc.py:_log_decision` collapses a whole
  Observe→Think→Act→Reflect cycle into two lines, `troll [reasoning] …` and
  `troll [action] …`. The observation the agent saw and the reflection-after-failure
  retry (which `react_behavior` does perform) aren't legible as a cycle.
- **"Verbose" is a raw JSON dump.** Debugging an agent means setting
  `verbose=True`, which makes `llm_client.py` `print(json.dumps(messages,
  indent=2))` — the raw prompt, not a readable trace.

The information needed to fix all of this already exists; it just isn't modeled
where every surface can use it. That's what §3–§4 introduce.

---

## 3. The `Message` and its `Channel`

Promote the web UI's ad-hoc message types into a single engine type. Everything the
engine wants to show becomes a `Message`:

```python
@dataclass
class Message:
    channel: Channel            # what KIND of information this is
    text: str                   # the human-readable content
    actor: str | None = None    # which character it's about (e.g. "troll")
    turn: int | None = None     # which turn, for grouping / headers
    meta: dict = field(default_factory=dict)  # command, failure_reason, ok flag, …
```

The `channel` is the heart of the design: it's the *meaning* of the message,
independent of how any surface draws it. Each channel maps 1:1 to something the code
already produces today:

| Channel | Meaning | Today's source | Terminal style (proposed) | Web CSS class (exists) |
|---------|---------|----------------|---------------------------|------------------------|
| `NARRATION` | World/action result | `Parser.ok()` | default green, `»` prefix | `.msg-output` |
| `BLOCKED` | Action failed a precondition | `Parser.fail()` | red | `.msg-error` |
| `COMMAND` | The actor's echoed command | app echoes `> cmd` | bold yellow, `>` prefix | `.msg-command` |
| `AGENT_OBSERVATION` | ReAct "Observe" | `build_npc_context` (verbose) | dim, indented `↳ observe` | *(new)* `.msg-npc_observation` |
| `AGENT_REASONING` | ReAct "Think" | `npc_log` `[reasoning]` line | dim, indented `↳ think` | `.msg-npc_log` |
| `AGENT_ACTION` | ReAct chosen command | `npc_log` `[action]` line | `✓`/`✗`, indented `act` | `.msg-npc_log` |
| `AGENT_REFLECTION` | ReAct "Reflect" after a failure | `_reflect` (currently unshown) | dim, indented `↳ reflect` | *(new)* `.msg-npc_reflection` |
| `SYSTEM` | Turn header, clock, meta-commands, game-over | game loop / clock | rule + muted header | *(new)* `.msg-system` |

`NARRATION`, `BLOCKED`, `COMMAND`, `AGENT_REASONING`, and `AGENT_ACTION` already
have a web class today; the rest are small additions. Nothing is invented — every
channel corresponds to a line the engine already emits or builds.

---

## 4. The `Renderer` seam

A `Renderer` consumes `Message`s and draws them for one surface. The interface is
deliberately tiny:

```python
class Renderer:
    def emit(self, message: Message) -> None: ...      # show one message
    def turn_header(self, turn: int, time: str | None) -> None: ...  # optional separator
    def flush(self) -> None: ...                        # finish a turn / batch
```

The parser holds one renderer and forwards to it; the game loop calls
`turn_header()` once per turn. Surfaces differ *only* by which renderer is
installed:

| Renderer | Surface | What it does |
|----------|---------|--------------|
| `RichTerminalRenderer` | terminal, notebooks | **Default.** Uses [`rich`](https://rich.readthedocs.io): turn rules, per-channel color, grouped & indented agent-trace blocks, `✓`/`✗` action glyphs. Auto-detects a non-TTY / `NO_COLOR` and degrades to plain text. |
| `PlainRenderer` | tests, logs, CI, no-`rich` fallback | No color or markup; one stable line per message. Guarantees the engine runs even if `rich` isn't installed, and keeps test output deterministic. |
| `WebRenderer` | Flask web app | Emits today's `{"type": ..., "text": ...}` dicts via a `channel → CSS class` map. The template and `style.css` are essentially unchanged. |
| `JSONRenderer` *(future)* | Godot / external renderer | One JSON record per message — the structured change feed the 2D renderer subscribes to. Realizes the export-API idea in [multi-character-play.md](multi-character-play.md) §5/§7. |

`rich` is chosen for the terminal because it gives colored, panel/rule-structured,
TTY-aware output out of the box, so the trace formatting stays declarative instead
of hand-rolled escape codes — see §8 for the dependency trade-off.

---

## 5. The agent ReAct trace — the big terminal win

This is the payoff. Channels let the `RichTerminalRenderer` group consecutive
`AGENT_*` messages under their actor, indent them as one block, and render world
`NARRATION` at the turn level.

**Before** (today's terminal — flat, monochrome, indistinguishable from narration):

```
troll [reasoning] My growl didn't scare the intruder off. Escalate.
troll [action] snarl player
The troll snarls at you, baring its teeth.
troll [reasoning] Still here. Attack.
troll [action] attack player
The troll doesn't have a weapon.
troll [reasoning] I need a weapon -- I have a club.
troll [action] attack player with club
The troll swings its club at you!
```

**After** (proposed — turn-structured, colored, the ReAct cycle legible at a glance):

```
── Turn 3 · 8:45 AM (morning) ───────────────────────────────
troll
  ↳ observe   You are on the drawbridge. An intruder blocks the way…
  ↳ think     My growl didn't scare them off — escalate.
  ✗ act       attack player        → blocked: the troll has no weapon
  ↳ reflect   I need a weapon; I'm holding a club.
  ✓ act       attack player with club
  » The troll swings its club at you!
```

In a real terminal the actor name and rule are colored, the `↳` lines are dim, `✗`
is red, `✓` is green, and `»` narration is the default green. Multiple NPCs in one
turn each get their own indented block, so two agents' thoughts never interleave.

The web app keeps its existing look (the colored message types it already renders),
now driven by the same channels:

```
> wait                                   ← yellow, bold        (COMMAND)
troll [think] My growl didn't scare…     ← gray, italic        (AGENT_REASONING)
troll [act ✗] attack player — no weapon  ← gray, italic        (AGENT_ACTION)
troll [act ✓] attack player with club    ← gray, italic        (AGENT_ACTION)
The troll swings its club at you!        ← purple, italic      (NARRATION/npc_action)
```

---

## 6. Verbosity levels

A single knob on the renderer decides which channels are shown — so the *same*
stream of messages can be a clean playthrough or a full agent debug trace:

| Level | Channels shown | For |
|-------|----------------|-----|
| `quiet` | `NARRATION`, `BLOCKED`, `COMMAND`, `SYSTEM` | clean play; agents act "off-screen" |
| `normal` *(default)* | + `AGENT_REASONING`, `AGENT_ACTION` | today's behavior: see thoughts + actions |
| `verbose` | + `AGENT_OBSERVATION`, `AGENT_REFLECTION`, raw prompt | debugging an agent |

`verbose` replaces the ad-hoc `print(json.dumps(messages))` in `llm_client.py`: the
raw prompt becomes an `AGENT_OBSERVATION` message the renderer can show or hide,
instead of an unconditional JSON dump bolted onto the client.

---

## 7. How the parser collapses

The four parser output methods become thin shims that build a `Message` and hand it
to the installed renderer. The four parser *classes* collapse to one output path;
terminal vs. web is just a different renderer.

**Before** — each class reimplements each method (`parsing.py`):

```python
def ok(self, description):
    print(Parser.wrap_text(description))
    self.add_description_to_history(description)

def npc_log(self, message):
    print(Parser.wrap_text(message))   # never added to history
```

…and `WebParser` / `LlmParser` / `WebLlmParser` each write their own variants.

**After** — one shim per channel, shared by every surface:

```python
def ok(self, description):
    self.renderer.emit(Message(NARRATION, description, turn=self.game.turn))
    self.add_description_to_history(description)

def npc_log_reasoning(self, actor, text):
    self.renderer.emit(Message(AGENT_REASONING, text, actor=actor, turn=self.game.turn))
    # still NOT added to command_history
```

What stays exactly the same — these are load-bearing and must not regress:

- **`command_history` is fed by the same shims.** `ok`/`npc_ok` still call
  `add_description_to_history`; player/NPC commands still go in via
  `add_command_to_history`. The LLM's conversation context is unchanged.
- **Agent channels never enter `command_history`.** `AGENT_*` messages are emitted
  to the renderer only — preserving the privacy invariant from
  `npc.py:_log_decision` (an NPC's reasoning must never leak into another
  character's observations).
- **Preconditions still gate everything.** Rendering is strictly downstream of
  `apply_effects()`; nothing about this layer touches the precondition gate.
- **`last_fail_message` still works.** `fail()` keeps setting it (now alongside
  emitting a `BLOCKED` message) so the ReAct `_reflect` step still reads the reason.

---

## 8. The `rich` dependency

Adopting `rich` adds a runtime dependency to a deliberately dependency-light,
undergraduate-facing teaching codebase — that's a real cost and worth stating
plainly. The case for it: `rich` is pure-Python, widely used, well-documented, and
gives colored, rule/panel-structured, TTY-aware output declaratively, so the trace
formatting in §5 stays readable instead of a thicket of ANSI escape codes the
students would have to decode.

Recommendation, to keep the cost contained:

- **`PlainRenderer` is always available** and `rich`-free. If `import rich` fails,
  the engine falls back to it automatically — so the project never *hard*-requires
  `rich` and CI/tests stay green without it.
- **Where it lands in `setup.py`:** add `rich` to core `install_requires` (next to
  `flask`) so the default `pip install -e .` gives the good terminal experience out
  of the box. The lighter-touch alternative is a `rich` extra
  (`pip install -e .[rich]`, mirroring `[llm]`); pick this if the team wants the
  base install to stay minimal. Either way the fallback in the previous bullet keeps
  a no-`rich` install fully functional.

---

## 9. Design invariants

- **One message taxonomy, many renderers.** The engine emits `Message`s by
  `channel`; how they look is the renderer's job alone. No surface re-invents the
  taxonomy.
- **Agent reasoning stays private.** `AGENT_*` channels go to the renderer, never
  into `command_history`. One NPC's thoughts never leak into another's
  observations.
- **Rendering is downstream of effects.** Messages describe what already happened;
  the precondition → effect gate is untouched. Output can never change the world.
- **World vs. view vs. render are three concerns.** State lives in the world graph;
  what a viewer perceives is a `View` (multi-character-play.md §5); how that's drawn
  is a `Renderer`. This doc only adds the third.
- **The seam is additive and backward-compatible.** A game with no agents emits only
  `NARRATION`/`COMMAND`/`SYSTEM` and looks like today's game (with nicer
  formatting). Drop in a different renderer and nothing upstream changes.
- **`PlainRenderer` keeps tests deterministic.** Tests assert on captured `Message`s
  (channel + text), not on colored bytes — more robust than today's string-matching
  against `npc_log` lines.

---

## 10. Build order

Sequenced so single-character games keep working at every step. Aligns with the
`reporting.py` step already listed in
[multi-character-play.md](multi-character-play.md)'s migration checklist.

| Stage | Deliverable | Keeps working |
|-------|-------------|---------------|
| 1 | `reporting.py`: `Channel`, `Message`, `Renderer` ABC, `PlainRenderer` | everything; nothing wired yet |
| 2 | Parser shims emit `Message`s to a renderer (default `PlainRenderer`) | terminal play, just via the seam |
| 3 | `RichTerminalRenderer` + turn headers in the game loop | terminal/notebooks gain color + structure |
| 4 | `WebRenderer`: port `WebParser`/`WebLlmParser` onto the seam | web app, with the same look |
| 5 | Richer ReAct trace in `npc.py` (observation/reasoning/action/reflection channels) | the §5 trace |
| 6 | Fold `LlmParser` narration into the seam; collapse the duplicate classes | LLM-narrated play |
| 7 | Tests switch to a `CaptureRenderer`; assert on channels not strings | the offline suites |
| 8 *(future)* | `JSONRenderer` / export feed for the Godot renderer | the 2D renderer |

Each stage is independently shippable; stop after any of them and the game still
runs.

---

## Appendix: implementation sketches

Illustrative starting points, not final API.

### `reporting.py` core

```python
from dataclasses import dataclass, field
from enum import Enum

class Channel(Enum):
    NARRATION = "narration"
    BLOCKED = "blocked"
    COMMAND = "command"
    AGENT_OBSERVATION = "agent_observation"
    AGENT_REASONING = "agent_reasoning"
    AGENT_ACTION = "agent_action"
    AGENT_REFLECTION = "agent_reflection"
    SYSTEM = "system"

@dataclass
class Message:
    channel: Channel
    text: str
    actor: str | None = None
    turn: int | None = None
    meta: dict = field(default_factory=dict)

class Renderer:
    """Turn Messages into output for one surface."""
    def emit(self, message: Message) -> None:
        raise NotImplementedError
    def turn_header(self, turn: int, time: str | None = None) -> None:
        pass
    def flush(self) -> None:
        pass
```

### `RichTerminalRenderer` (sketch)

```python
class RichTerminalRenderer(Renderer):
    def __init__(self, level="normal"):
        from rich.console import Console      # imported lazily; PlainRenderer if it fails
        self.console = Console()              # rich auto-detects TTY / NO_COLOR
        self.level = level

    _STYLE = {
        Channel.NARRATION: ("» ", "green"),
        Channel.BLOCKED:   ("",   "red"),
        Channel.COMMAND:   ("> ", "bold yellow"),
        Channel.AGENT_REASONING: ("  ↳ think    ", "dim"),
        Channel.AGENT_ACTION:    ("  ", "default"),
        # …
    }

    def turn_header(self, turn, time=None):
        label = f"Turn {turn}" + (f" · {time}" if time else "")
        self.console.rule(label)

    def emit(self, message):
        if not self._visible(message.channel):   # §6 verbosity gate
            return
        if message.channel == Channel.AGENT_ACTION:
            ok = message.meta.get("ok", True)
            glyph, color = ("✓", "green") if ok else ("✗", "red")
            reason = "" if ok else f"  → blocked: {message.meta.get('failure_reason','')}"
            self.console.print(f"  [{color}]{glyph} act[/]      {message.text}{reason}")
            return
        prefix, style = self._STYLE[message.channel]
        self.console.print(f"[{style}]{prefix}{message.text}[/]")
```

### Parser shim (before → after)

```python
# before (parsing.py)
def fail(self, description):
    self.last_fail_message = description
    print(Parser.wrap_text(description))

# after
def fail(self, description):
    self.last_fail_message = description                       # ReAct reflect still reads this
    self.renderer.emit(Message(Channel.BLOCKED, description, turn=self.game.turn))
```

### `CaptureRenderer` for tests

```python
class CaptureRenderer(Renderer):
    def __init__(self):
        self.messages = []
    def emit(self, message):
        self.messages.append(message)

# in a test:
#   assert any(m.channel is Channel.AGENT_ACTION and m.text == "growl player"
#              for m in renderer.messages)
# — channel-based, no brittle string prefixes like "troll [action] …"
```

### Example terminal session (mock provider, free offline)

```text
$ LLM_PROVIDER=mock python -m notebooks.hw1_llm.play

── Turn 0 · 8:00 AM (morning) ────────────────────────────────
DRAWBRIDGE
You are on a drawbridge over the moat. A troll blocks the way north.
Exits:
  » North to the gatehouse

> wait

── Turn 1 · 8:15 AM (morning) ────────────────────────────────
troll
  ↳ think     An intruder is on my drawbridge. Warn them off.
  ✓ act       growl player
  » The troll growls menacingly.
```

### Notes

- **Glyphs/Unicode:** `rich` handles the box-drawing and arrows; `PlainRenderer`
  substitutes ASCII (`->`, `[x]`/`[ok]`) so logs stay 7-bit clean.
- **`wrap_text`:** `rich` wraps to the console width on its own; `PlainRenderer`
  keeps the existing `wrap_text(..., 80)` for stable fixtures.
- **Where the renderer lives:** the `Game`/`Parser` holds one renderer (default
  resolved from `rich`-availability + `NO_COLOR`); the webapp injects `WebRenderer`,
  tests inject `CaptureRenderer`.
