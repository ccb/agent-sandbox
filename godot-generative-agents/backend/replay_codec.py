"""Carry-forward codec for replay frames (#941).

The emitter (``penn_world.replay_frame_entry``) snapshots every agent's whole
``memories`` list and ``chat`` transcript on **every** frame, even though the
values change only a handful of times per agent per run — on the #878 showcase
replay (4,320 steps x 5 agents) that redundancy is 93% of a 76 MB file, which
the Godot WASM viewer cannot parse (it hangs; see #941).

``slim_frames`` removes exactly that redundancy from a *written file*: a
carry-forward field is omitted when it deep-equals the previous frame's value
for the same agent. ``fatten_frames`` reverses it on read, so in-memory
consumers (the Godot viewer, the web companion, the believability eval) see
the exact frames the emitter produced::

    fatten_frames(slim_frames(frames)) == frames     # the round-trip law

Semantics of a slim file: **absent = unchanged from the previous frame;
present (including an explicit null) = a new value.** ``x``/``y``/``act``/
``e`` are never omitted — they are the non-Optional ``AgentFrame`` fields, and
a slim row must stay contract-valid. Fattening an already-fat file is the identity,
so one reader handles both pre- and post-#941 replays; the run store and the
live feed stay fat and are untouched by this module.

Like ``contract.py``, this module is deliberately **stdlib-only**: the offline
bake runs in the base install (no extras).
"""

from __future__ import annotations

from .contract import AGENT_FRAME_FIELDS

# The sticky fields: written at decisions/conversations, carried forward
# unchanged between them (see run_simulation.step's frame assembly).
CARRY_FIELDS = ("reasoning", "chat", "memories", "trace")


def slim_frames(frames: list[dict]) -> list[dict]:
    """Return a slim copy of *frames*; the input is never mutated.

    An agent's first frame is passed through verbatim; later frames drop each
    ``CARRY_FIELDS`` key whose value equals that agent's previous frame.
    Emitted key order is the input's order (the pinned contract order for
    emitter-shaped input), so a slim bake stays byte-deterministic.
    """
    out: list[dict] = []
    prev: dict[str, dict] = {}  # agent name -> that agent's previous fat entry
    for frame in frames:
        if not isinstance(frame, dict):
            out.append(frame)  # version-skewed row: pass through, like fatten
            continue
        row: dict = {}
        for name, entry in frame.items():
            seen = prev.get(name)
            if not isinstance(entry, dict) or seen is None:
                row[name] = entry
            else:
                # `k not in seen`, not seen.get(k): an explicit null after an
                # absent key must stay explicit -- fatten never invents a
                # value for a key it hasn't seen, so dropping it here would
                # break the round-trip law on mixed-vintage frames.
                row[name] = {
                    k: v
                    for k, v in entry.items()
                    if k not in CARRY_FIELDS or k not in seen or seen[k] != v
                }
            if isinstance(entry, dict):
                prev[name] = entry
        out.append(row)
    return out


def fatten_frames(frames: list[dict]) -> list[dict]:
    """Reverse ``slim_frames``: carry absent ``CARRY_FIELDS`` forward.

    Rebuilds each entry in the pinned ``AGENT_FRAME_FIELDS`` order (so a
    fatten -> slim -> ``json.dump`` pipeline reproduces the bake's bytes) and
    is the identity, value-wise, on already-fat frames. Conservative: a key
    an agent has *never* carried stays absent rather than gaining an invented
    default — pre-#359 replays have no ``trace`` anywhere, and fattening one
    must not change its content (readers ``.get()`` absent keys already).
    Carried values are shared by reference — cheap, and safe because nothing
    downstream mutates frame entries.
    """
    out: list[dict] = []
    carried: dict[str, dict] = {}  # agent name -> {field: last explicit value}
    for frame in frames:
        if not isinstance(frame, dict):
            # Version-skewed row: pass through untouched, mirroring the gd/ts
            # readers -- degrade to "skip + warn elsewhere" (#638), not crash.
            out.append(frame)
            continue
        row: dict = {}
        for name, entry in frame.items():
            if not isinstance(entry, dict):
                row[name] = entry
                continue
            agent_carry = carried.setdefault(name, {})
            fat: dict = {}
            for k in AGENT_FRAME_FIELDS:
                if k in entry:
                    fat[k] = entry[k]
                elif k in CARRY_FIELDS and k in agent_carry:
                    fat[k] = agent_carry[k]
            for k, v in entry.items():  # future-proof: unknown keys pass through
                if k not in fat:
                    fat[k] = v
            for k in CARRY_FIELDS:
                if k in entry:
                    agent_carry[k] = entry[k]
            row[name] = fat
        out.append(row)
    return out
