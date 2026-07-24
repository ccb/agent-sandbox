"""Run the UPenn agent simulation and write a replay the Godot frontend can play.

Godot can't run Python, so (exactly like the Phaser/Django replay) the sim runs
offline here and we dump a compact per-step "replay" JSON; the Godot scene
`scenes/viewer.tscn` reads it and animates a sprite per persona walking the
campus map.

The Penn *world* lives next to this script (`world_data_upenn.yaml` + the
`the_upenn/` matrix) and is configured by the sibling ``penn_world`` module --
the same :func:`~penn_world.build_penn_world` the live server (``serve_penn.py``)
uses, so the baked and live Penns can never drift apart (#297). The agent
*engine* (build the world, attach mock brains, step the loop, pathfind) is
imported from the shared `backend` package so improvements there flow through
automatically. Only genuinely bake-only work remains here: running the sim to
completion, the post-hoc conversation injector, and writing the JSON.

Run from the repo root (so `uv run` finds the engine env)::

    uv run python godot-generative-agents/backend/penn/generate_penn_replay.py
    uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 600

Writes: godot-generative-agents/godot/maps/penn_replay.json
"""

import argparse
import json
import os

# Reuse the tested agent engine (not a fork). It's the installed top-level
# `backend` package now, so a plain import works -- no sys.path juggling. The
# sibling `penn_world` import works because Python puts this script's own
# directory on sys.path when it is run as a script.
from backend.contract import SCHEMA_VERSION
from backend.run_store import DEFAULT_RUNS_DIR, RunStore
from backend.run_simulation import simulate
from backend.cognition import DEFAULT_VISION_R
from penn_world import (
    DIALOGUE_FADE_STEPS,
    DIALOGUE_LINE_STEPS,
    PENN_ACTION_VERBS,
    SEC_PER_STEP,
    SIM_START,
    WORLD_DATA,
    WORLD_DATA_BOIL,
    build_penn_world,
    persona_meta_entry,
    replay_frame_entry,
)

_SIM_DIR = os.path.dirname(
    os.path.abspath(__file__)
)  # .../godot-generative-agents/backend/penn
_GG_DIR = os.path.dirname(os.path.dirname(_SIM_DIR))  # .../godot-generative-agents
_GODOT_DIR = os.path.join(_GG_DIR, "godot")  # the Godot project (its res:// root)
_REPO = os.path.dirname(_GG_DIR)

# Output paths live in the SCENARIOS table below (each scenario names its own file
# under maps/), resolved against _GODOT_DIR in main().

# A full campus day: every persona crosses the (large) map several times AND now
# walks a multi-room circuit inside Van Pelt. At one tile per step a single
# cross-campus leg is ~200 steps, so 400 ended mid-morning -- agents barely reached
# their first building. 1200 lets the whole cast complete its day, including the
# in-library room-to-room movement (Maya's two Van Pelt visits, Ellis's stacks run,
# Diego's gallery circuit). The viewer's playback speed is independent of this.
DEFAULT_STEPS = 1200

# The boil-water demo (#592) is a short, single-persona bake -- long enough for the
# whole arc plus a recovered-agent tail, no more. The arc's three events land at
# ~step 11/40/69 (a lead-in, then drink/boil/drink ~29 steps apart), leaving a short
# recovered tail; see world_data_boil.yaml for the stop-by-stop budget.
DEFAULT_BOIL_STEPS = 90

# Named scenarios select {world YAML, default step budget, default output file}.
# `--scenario boil` bakes the de-clumped demo alongside (not over) the bundled
# replay, so the viewer can offer it as its own menu entry (#592). `--steps`/`--out`
# still override the per-scenario defaults.
SCENARIOS = {
    "penn": {
        "world_data": WORLD_DATA,
        "steps": DEFAULT_STEPS,
        "out": "penn_replay.json",
    },
    "boil": {
        "world_data": WORLD_DATA_BOIL,
        "steps": DEFAULT_BOIL_STEPS,
        "out": "penn_replay_boil.json",
    },
}


def _inject_scripted_conversations(replay, meetings, vision_r):
    """Paint authored dialogue into the replay's `chat` field -- proximity-honestly.

    The mock brain never speaks, so the viewer's speech-bubble + conversation-link
    feature would otherwise never fire. For each authored meeting we find the
    longest stretch of the bake where *every* participant is within ``vision_r``
    tiles of each other (the same radius the viewer draws as perception fog), and
    only if that stretch is long enough to play the whole exchange do we write the
    transcript onto each participant's `chat` for that window. The viewer keys the
    bubble/link off `chat`, so a conversation is only ever drawn between agents who
    are genuinely standing together on the map.

    If a meeting's participants never co-locate long enough in this bake, it is
    SKIPPED with a warning rather than faked across the map -- so changing a
    schedule can quietly drop a meeting, and the log says which and why.

    This whole-run window scan is genuinely bake-only (it needs the finished
    frames); the live server ports the same rules to an on-the-fly state machine
    (``serve_penn.LiveMeetingInjector``) because it can't see the future.
    """
    frames = replay["frames"]
    n = len(frames)
    if n == 0:
        return

    def co_located(i, participants):
        pts = []
        for p in participants:
            ent = frames[i].get(p)
            if ent is None:
                return False
            pts.append((ent["x"], ent["y"]))
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                dx, dy = pts[a][0] - pts[b][0], pts[a][1] - pts[b][1]
                if (dx * dx + dy * dy) ** 0.5 > vision_r:
                    return False
        return True

    cast = set(frames[0].keys())
    print(f"Injecting scripted conversations (vision_r={vision_r} tiles):")
    fired = 0
    for m in meetings:
        participants = m.get("participants", [])
        dialogue = [[str(s), str(t)] for s, t in m.get("dialogue", [])]
        label = m.get("label", " + ".join(participants))
        missing = [p for p in participants if p not in cast]
        if len(participants) < 2 or not dialogue or missing:
            print(f"  - SKIP  {label}: bad spec (missing {missing or 'dialogue'}).")
            continue

        # Frames the whole exchange needs to play (incl. the final fade).
        need = len(dialogue) * DIALOGUE_LINE_STEPS + DIALOGUE_FADE_STEPS

        # Longest contiguous run where all participants are mutually within range.
        best_start, best_len, cur_start = -1, 0, None
        for i in range(n):
            if co_located(i, participants):
                cur_start = i if cur_start is None else cur_start
                if i - cur_start + 1 > best_len:
                    best_len, best_start = i - cur_start + 1, cur_start
            else:
                cur_start = None

        if best_len < need:
            print(
                f"  - SKIP  {label}: longest co-located window {best_len} steps "
                f"< {need} needed for {len(dialogue)} lines."
            )
            continue

        start, end = best_start, best_start + need
        # Don't garble a participant who is already mid-conversation in this window.
        clash = any(
            frames[i][p].get("chat") for i in range(start, end) for p in participants
        )
        if clash:
            print(f"  - SKIP  {label}: overlaps another meeting's window.")
            continue

        for i in range(start, end):
            for p in participants:
                frames[i][p]["chat"] = dialogue
        fired += 1
        print(
            f"  - FIRE  {label}: steps {start}-{end} "
            f"({len(participants)} agents, window {best_len} steps)."
        )
    print(f"Injected {fired}/{len(meetings)} meetings.")


def _build_parser() -> argparse.ArgumentParser:
    """The bake's CLI, as a seam so the defaults can be pinned offline (#752)."""
    ap = argparse.ArgumentParser(description="Generate the Penn replay for Godot.")
    ap.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="penn",
        help="which world to bake: 'penn' (the full campus cast, the bundled "
        "replay) or 'boil' (the one-persona boil-water demo, #592). Sets the "
        "default world YAML, step budget, and output file.",
    )
    ap.add_argument(
        "--steps",
        type=int,
        default=None,
        help="override the scenario's default step budget",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="output file path, used verbatim (relative to the current directory, "
        "not maps/); the scenario default lives under maps/. For the viewer's menu "
        "button to find the boil demo it must land at maps/penn_replay_boil.json.",
    )
    ap.add_argument(
        "--persist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="record this bake durably (#304), ON BY DEFAULT: a runs/<run_id>/ "
        "entry (frames + events + wishes) plus a sim.db row, under "
        "godot-generative-agents/runs/ -- so every entry point (viewer/script/web) "
        "default-saves the run to the one shared store (#752). --no-persist makes "
        "the bake ephemeral (replay file only, no store rows) for dev/throwaway bakes.",
    )
    ap.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="RunStore root for --persist (default: godot-generative-agents/runs/)",
    )
    ap.add_argument(
        "--brain",
        choices=("mock", "scripted"),
        default="mock",
        help="mock (default): the deterministic schedule brain -- byte-identical "
        "bake. scripted: the key-free full-feature brain (#563) -- bakes a replay "
        "that exercises the tool loop, cognition tools, conversation, reflection.",
    )
    return ap


def main() -> int:
    args = _build_parser().parse_args()

    # Resolve the scenario's world/steps/out, letting explicit flags win.
    scenario = SCENARIOS[args.scenario]
    steps = args.steps if args.steps is not None else scenario["steps"]
    out_path = args.out or os.path.join(_GODOT_DIR, "maps", scenario["out"])

    # The configured Penn: personas + locations + meetings, the routing-patched
    # world_map, and the perception-gated build_world_fn (#297). Shared verbatim
    # with the live server, so this bake and a live run walk the same campus. The
    # boil scenario swaps only the world YAML (one persona, the arc); the map,
    # factory, and boil props (_furnish_boil_water) are identical.
    pw = build_penn_world(world_data=scenario["world_data"])

    print(
        f"Loaded the_upenn ({pw.world_map.width}x{pw.world_map.height}); "
        f"{len(pw.personas)} personas. Simulating {steps} steps "
        f"(scenario '{args.scenario}')..."
    )

    # `simulate` fills this with each persona's *full* memory stream (the same
    # UI-ready dicts the exporter writes). The agent-info companion
    # panel renders it as a per-agent "memory history" that grows over the
    # replay; the per-frame `reasoning`/`chat` below feed that agent's card.
    # Under the mock brain reasoning is a stub and chat is null, but travel/
    # perform reflections and perception observations still accrue, so the
    # history is populated either way -- it just gets richer with a real model.
    memory_streams: dict = {}
    # The same streams as full engine records (ids/embeddings included) -- what
    # --persist hands the RunStore; the lean memory_streams cannot rehydrate.
    memory_records: dict = {}
    events: list = []
    # The run's ActionWish demand log (#622) -- empty under the mock brain by
    # construction (it never proposes and its authored commands always parse).
    wishes: list = []

    # --brain scripted (#563): a key-free, deterministic brain that still drives
    # the full tool loop -- cognition tools, conversation, reflection -- so the
    # baked replay exercises those paths without a real LLM. --brain mock (the
    # default) leaves brain/reflector/cognition/ledger at None, which is exactly
    # what `simulate` saw before this flag existed, so that bake stays
    # byte-identical.
    brain = reflector = None
    cognition = None
    ledger = None
    if args.brain == "scripted":
        from backend.sim_config import CognitionConfig
        from text_adventure_games.usage import UsageLedger
        from scripted_brain import build_scripted_brains

        ledger = UsageLedger()
        brain, reflector = build_scripted_brains(ledger=ledger)
        cognition = CognitionConfig(cognition_tools=True)

    frames = simulate(
        pw.world_map,
        steps,
        ledger=ledger,
        personas=pw.personas,
        build_world_fn=pw.build_world_fn,
        out_memories=memory_streams,
        out_memory_records=memory_records,
        out_events=events,
        out_wishes=wishes,
        extra_action_names=PENN_ACTION_VERBS,
        cognition=cognition,
        reflector_client=reflector,
        llm_client=brain,
    )

    # Godot-friendly replay: meta + one entry per step per persona (see
    # penn_world.replay_frame_entry for the per-agent shape and who reads what).
    order = [p["name"] for p in pw.personas]
    replay = {
        "meta": {
            # The pinned replay contract this file conforms to (#305) -- see
            # backend/contract.py for the schema and the bump policy.
            "schema_version": SCHEMA_VERSION,
            "tile_px": pw.world_map.tile_size,
            "width": pw.world_map.width,
            "height": pw.world_map.height,
            "steps": len(frames),
            "sec_per_step": SEC_PER_STEP,
            "start": SIM_START,
            # Perception radius (tiles) the sim used to gate sight + conversation,
            # so the viewer can draw the matching "perception fog" when tracking an
            # agent. Personas don't override it in world_data_upenn.yaml, so the
            # global default describes every agent.
            "vision_r": DEFAULT_VISION_R,
            # name/emoji drive the sprite + sidebar; persona/home/schedule feed the
            # State Details inspector modal (viewer.gd, issue #408). See
            # penn_world.persona_meta_entry -- the projection the live server shares.
            "personas": [persona_meta_entry(p) for p in pw.personas],
            # The t=0 seed social graph (world YAML `relationships:` block,
            # validated by penn_world.relationships_meta -- shared with the live
            # server). The viewer's social-graph pop-up (#252) contrasts it with
            # the conversations that actually happen over the run.
            "relationships": pw.relationships,
        },
        "frames": [
            {name: replay_frame_entry(f[name]) for name in order} for f in frames
        ],
        # Per-persona full memory stream: [{kind, importance, text, created_turn}].
        # The panel filters to created_turn <= current step to show history so far.
        "memory_streams": memory_streams,
        # The run's GameEvent log (#467): EventState-shaped records straight
        # from GameEvent.to_primitive(). The viewer ignores unknown top-level
        # keys; post-hoc metrics (#299) read this instead of the memory stream.
        "events": events,
        # The run's ActionWish demand log (#622): WishState-shaped records
        # straight from ActionWish.to_primitive() -- empty under the mock
        # brain by construction. The eventual #623 "most wanted" report reads
        # this instead of re-deriving demand from the memory stream.
        "wishes": wishes,
    }

    # Light up the viewer's speech-bubble + conversation-link feature with authored
    # dialogue, but only across the frames where the participants are actually
    # standing together (see _inject_scripted_conversations). No-op if the world
    # has no `meetings` block.
    _inject_scripted_conversations(replay, pw.meetings, DEFAULT_VISION_R)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(replay, fh, ensure_ascii=False)
    print(
        f"Wrote {os.path.relpath(out_path, _REPO)} "
        f"({len(frames)} steps, {len(order)} personas)."
    )

    # Optionally mirror the bake into the durable store (#304) -- AFTER the
    # meeting injection above, so the persisted frames byte-match the file's.
    # The mock bake runs without a ledger, so cost is simply 0.
    if args.persist:
        store = RunStore(args.runs_dir)
        run_id = store.create_run(replay["meta"])
        for step_idx, frame in enumerate(replay["frames"]):
            store.append_frame(run_id, step_idx, frame)
        for name in order:
            store.record_memories(run_id, name, memory_records.get(name, []))
        store.append_events(run_id, replay["events"])
        store.append_wishes(run_id, replay["wishes"])
        store.update_run(
            run_id, status="finished", steps=len(replay["frames"]), cost=0.0
        )
        print(
            f"Persisted run {run_id} to {store.root} (frames + events + wishes + sim.db)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
