# Reading the game's output

A guide to **interpreting what the game prints** — the colors, prefixes, and
indented blocks you see when you play in the terminal or the browser, and how to
read an agent's thoughts as it takes a turn.

This is a *user* guide: it explains what the output **means**, not how it's built.
If you want the internals (the `Message`/`Channel`/`Renderer` design), see
[`design/output-and-trace-rendering.md`](design/output-and-trace-rendering.md).

> **TL;DR** — Every line the engine prints has a *kind*: world narration, an
> NPC's action, a blocked action, your command, or one of an agent's private
> thoughts (think / act / reflect / observe). Each kind gets its own color and
> prefix so you can tell them apart at a glance. Indented blocks under a name
> are that character's **reasoning**, not things that happened in the world.

---

## The quick legend

When you run the game in a normal color terminal, this is what each line means:

| You see… | Means | Color & prefix |
|----------|-------|----------------|
| `» You are on a drawbridge…` | **World narration** — a room description or the result of an action | green, `»` |
| `» Troll growls menacingly.` | **An NPC's action** played out in the world | magenta, `»` |
| `✗ troll doesn't have a weapon.` | **Blocked** — an action was rejected because its preconditions weren't met | red, `✗` |
| `> go north` | **A command** being entered (see the note on the prompt below) | yellow, `>` |
| `troll` *(on its own line)* | The **agent whose turn it is**; the indented lines below belong to it | bold magenta |
| `  think    Escalate — warn them off.` | The agent's **reasoning** (its private "Think" step) | dim |
| `  · act     snarl player` | The **command the agent chose** to run | cyan |
| `  reflect  My attack needs a weapon.` | The agent **rethinking** after an action failed | yellow |
| `  observe  You are on the drawbridge…` | What the agent **perceived** this turn (only at `verbose`) | dim |
| `── Turn 3 ──────────` | A **new turn** started | cyan rule |

The two big things to internalize:

1. **A `»` line is the world; an indented line under a name is a thought.** The
   troll *thinking* "attack the intruder" is not the same as the troll actually
   attacking — only a `»` narration line means something happened.
2. **An agent's whole turn is grouped under its name.** Everything indented below
   `troll` is the troll reasoning, choosing an action, and (if needed) reflecting.
   When the next character acts, its name prints and a new block begins.

---

## Walking through a turn

Here's a real moment from the offline demo
(`LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play`), as it looks in a color
terminal. The troll growls, that doesn't work, so it escalates to an attack —
which **fails** because it has no weapon — then it reflects and retries with its
club:

```
── Turn 3 ──────────────────────────────────────────────
troll
  think    Growling and snarling didn't drive the intruder off. Attack.
  · act     attack player
✗ troll doesn't have a weapon.
  reflect  My attack failed because I never said which weapon to use.
  · act     attack player with club
» Troll attacked The player with the club.
```

Read it top to bottom as the agent's **ReAct cycle** — Observe → Think → Act →
Reflect:

- **`── Turn 3 ──`** — a new turn began. The rule appears the first time a
  character acts in that turn. (If the game tracks time, you'll also see it here,
  e.g. `── Turn 3 · 8:45 AM ──`.)
- **`troll`** — the troll is taking its turn; the indented lines are *its* thoughts.
- **`  think`** — the troll's reasoning. This is *internal*. Nothing has happened
  in the world yet.
- **`  · act     attack player`** — the command the troll decided to run. It still
  has to pass the same rules a player's command does.
- **`✗ troll doesn't have a weapon.`** — the action was **blocked**. The red `✗`
  line is the engine's reason: `attack` needs a weapon, and the troll named none.
  *This is a feature, not a bug* — the agent has to play by the world's rules.
- **`  reflect`** — the troll reads that failure reason back and figures out what
  went wrong (it never said *which* weapon).
- **`  · act     attack player with club`** — its retry, now with the weapon named.
- **`» Troll attacked The player with the club.`** — a magenta `»` line: this one
  succeeded and actually happened in the world.

The failed-then-retried pattern above is the **Reflect** step working as
intended. Seeing a red `✗` followed by a `reflect` line and a successful retry
means the agent recovered from a mistake — exactly what you want to see.

> **Why two characters never get tangled up.** Each agent's trace is grouped
> under its own name, so if a troll *and* a guard both act in one turn, you get
> two separate indented blocks — one agent's thoughts never interleave with
> another's.

---

## What the `>` prompt is

In the terminal, the line where you type looks like:

```
> 
```

…or, if the game has a clock running:

```
[8:00 AM] > 
```

That `>` is just the **input prompt** — where you type your next command. After
you press Enter, your command is on that line and the result prints below it. (In
the **web app** your command is echoed back as its own yellow `> …` line; in the
terminal it's simply whatever you typed at the prompt.)

---

## In the browser

The web app (`uv run python -m text_adventure_games.webapp.app`,
<http://localhost:8080>) shows the same information, color-coded the same way —
just as a scrolling HTML transcript instead of a turn-ruled terminal:

| Color | What it is |
|-------|------------|
| **green** | World narration / action results |
| **purple, italic** | An NPC's action |
| **red** | A blocked action (precondition not met) |
| **yellow** | A command that was entered |
| **green-gray, italic** | An agent's reasoning and chosen action (`troll [reasoning] …` / `troll [action] …`) |
| **gold, italic** | An agent's reflection after a failure (`troll [reflect] …`) |
| **blue-gray, italic** | The agent's observation block (only at `verbose`) |
| **gray** | System notices (clock, game-over) |

The browser writes the agent trace as labeled one-liners
(`troll [reasoning] …`, `troll [action] …`) rather than the terminal's indented
block, but the meaning is identical: italic, muted lines are the agent's private
thoughts; solid colored lines are things that happened.

---

## Showing more or less: verbosity

How much of the agent trace you see is controlled by one setting. Set the
`OUTPUT_LEVEL` environment variable before launching:

```bash
OUTPUT_LEVEL=quiet   LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play
OUTPUT_LEVEL=verbose LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play
```

| Level | What you see | Good for |
|-------|--------------|----------|
| `quiet` | World narration, NPC actions, blocked actions, your commands, system notices — **no agent thoughts** | A clean playthrough; agents act "off-screen" |
| `normal` *(default)* | The above **plus** each agent's `think`, `act`, and `reflect` lines | Normal play — watch the NPCs reason |
| `verbose` | Everything, **plus** the `observe` block: the full context (persona, goals, what it perceives) the agent saw before deciding | Debugging an agent — *why* did it choose that? |

At `quiet`, the troll still growls and attacks; you just don't see it thinking.
At `verbose`, you additionally see the `observe` block — the prompt the agent was
actually working from — which is the first thing to check when an agent does
something surprising.

---

## Plain (no-color) mode

Sometimes you'll get **plain text with no colors** instead of the formatted
terminal output. This happens automatically when any of these is true:

- The output is **piped or redirected** to a file or another program (so logs
  stay clean), e.g. `… | tee run.log`.
- The `NO_COLOR` environment variable is set.
- The `rich` library isn't installed (it ships by default, but the engine never
  *requires* it).

In plain mode the same information is still all there — it just uses labeled
lines instead of color and indentation:

```
troll [reasoning] Growling and snarling didn't drive the intruder off. Attack.
troll [action] attack player
troll doesn't have a weapon.
troll [reflect] My attack failed because I never said which weapon to use.
troll [action] attack player with club
Troll attacked The player with the club.
```

Read it the same way: `[reasoning]` / `[action]` / `[reflect]` / `[observe]`
lines are the agent's private trace; un-labeled lines are world narration and
blocked actions. This is also exactly the format the test suite reads, so it
stays stable.

---

## Quick "why am I seeing this?"

- **"I see the troll *thinking* about attacking but it never attacks."** A
  `think` or `· act` line is intent, not outcome. Look for the line *after* it: a
  green/magenta `»` means it worked; a red `✗` means it was blocked (and the `✗`
  line tells you why).
- **"An action shows a red `✗` and a reason."** The action failed its
  preconditions — the same gate the player's commands go through. The agent will
  usually `reflect` and try something else on the next line.
- **"I want to see *why* an agent chose what it did."** Run with
  `OUTPUT_LEVEL=verbose` to reveal the `observe` block — the persona, goals, and
  perceptions it decided from.
- **"There are no colors / no `── Turn N ──` rules."** You're in plain mode (piped
  output, `NO_COLOR`, or no `rich`). The content is identical; see the section
  above.
- **"I see no agent thoughts at all, just narration."** You're at
  `OUTPUT_LEVEL=quiet`. Switch to `normal` (the default) to see them.

---

*For how this is implemented under the hood, see the design doc:*
[`design/output-and-trace-rendering.md`](design/output-and-trace-rendering.md).
