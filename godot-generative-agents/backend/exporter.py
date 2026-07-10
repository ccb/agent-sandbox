"""Write a simulation into the layout the Django frontend replays.

The frontend (in replay mode) reads, per step, ``storage/<sim>/movement/<step>.json``
and serves it to the browser; it also needs ``environment/0.json`` (initial
tiles), ``reverie/meta.json`` (sim metadata), and a ``personas/<Name>/`` memory
folder (for the click-a-persona state panel). This module writes all of that.

See the contract in ``docs/design/generative-agents-port.md`` and the upstream
``translator/views.py`` (``replay`` / ``update_environment``).
"""

import datetime
import json
import os
import shutil

# The sim's clock: one step is 10 seconds of in-game time.
SEC_PER_STEP = 10
MAZE_NAME = "the_ville"


def _fmt_time(dt: datetime.datetime) -> str:
    """Upstream's curr_time format, e.g. 'February 13, 2023, 08:00:10'."""
    return f"{dt:%B} {dt.day}, {dt.year}, {dt:%H:%M:%S}"


def _fmt_date(dt: datetime.datetime) -> str:
    """Upstream's start_date format (date only), e.g. 'February 13, 2023'."""
    return f"{dt:%B} {dt.day}, {dt.year}"


def _fmt_clock(dt: datetime.datetime) -> str:
    """Compact wall-clock for a memory's timestamp on the card, e.g. '08:16'."""
    return f"{dt:%H:%M}"


def _stamp_memory_times(
    frame: dict, start_dt: datetime.datetime, sec_per_step: int
) -> None:
    """Add a human ``time`` to each retrieved memory in *frame*, in place.

    A memory carries ``created_turn`` (the step it was formed); we turn that into
    the same wall-clock the replay's navbar shows (``start_dt + turn * step``), so
    the agent card can label *when* each memory entered the stream. Idempotent --
    a memory dict shared across consecutive frames is stamped once (same value),
    so re-running is harmless.
    """
    for entry in frame.values():
        _stamp_memory_list(entry.get("memories", []), start_dt, sec_per_step)


def _stamp_memory_list(
    memories: list, start_dt: datetime.datetime, sec_per_step: int
) -> None:
    """Add a wall-clock ``time`` to each memory dict in *memories*, in place.

    The same ``created_turn`` -> ``time`` math used for the per-frame retrieved
    memories (above), reused for a persona's full exported stream so both the
    State Details "retrieved" and "all memories" lists carry consistent labels.
    """
    for mem in memories:
        if "time" not in mem and "created_turn" in mem:
            mem_dt = start_dt + datetime.timedelta(
                seconds=mem["created_turn"] * sec_per_step
            )
            mem["time"] = _fmt_clock(mem_dt)


def write_simulation(
    storage_root: str,
    sim_code: str,
    frames: list[dict],
    start_dt: datetime.datetime,
    start_tiles: dict[str, tuple[int, int]],
    base_personas_dir: str,
    sec_per_step: int = SEC_PER_STEP,
    memory_streams: dict | None = None,
    plans: dict | None = None,
) -> str:
    """Materialize a replayable sim folder under ``storage_root/sim_code``.

    ``frames`` is one dict per step: ``{persona_name: {movement, pronunciatio,
    description, chat}}``. ``start_tiles`` seeds ``environment/0.json``.
    ``base_personas_dir`` is the base sim's ``personas/`` folder, copied in so the
    frontend's persona state panel has memory to show.

    ``memory_streams`` (``{persona_name: [memory dicts]}``, from
    ``simulate(out_memories=...)``) is each agent's *full* memory stream; we write
    it to ``personas/<Name>/memory_stream.json`` so the State Details panel can
    show every memory an agent formed, not just the per-step retrieved set the
    cards render.

    ``plans`` (``{persona_name: DailyPlan.to_primitive()}``, from
    ``simulate(out_plans=...)``) is each agent's generated daily plan; we write it
    to ``personas/<Name>/daily_plan.json`` so the plan a run used is an inspectable
    artifact a reader can load back without any model calls. Returns the
    sim folder path.
    """
    sim_dir = os.path.join(storage_root, sim_code)
    movement_dir = os.path.join(sim_dir, "movement")
    environment_dir = os.path.join(sim_dir, "environment")
    reverie_dir = os.path.join(sim_dir, "reverie")
    personas_dir = os.path.join(sim_dir, "personas")
    for d in (movement_dir, environment_dir, reverie_dir):
        os.makedirs(d, exist_ok=True)

    persona_names = list(start_tiles.keys())

    # Per-step movement files.
    for step, frame in enumerate(frames):
        curr = start_dt + datetime.timedelta(seconds=step * sec_per_step)
        # Label each retrieved memory with the time it was formed (see card).
        _stamp_memory_times(frame, start_dt, sec_per_step)
        payload = {"persona": frame, "meta": {"curr_time": _fmt_time(curr)}}
        _dump(os.path.join(movement_dir, f"{step}.json"), payload)

    # Initial positions the frontend places sprites at before replay starts.
    environment0 = {
        name: {"maze": MAZE_NAME, "x": int(xy[0]), "y": int(xy[1])}
        for name, xy in start_tiles.items()
    }
    _dump(os.path.join(environment_dir, "0.json"), environment0)

    # Simulation metadata.
    meta = {
        "fork_sim_code": sim_code,
        "start_date": _fmt_date(start_dt),
        "curr_time": _fmt_time(start_dt),
        "sec_per_step": sec_per_step,
        "maze_name": MAZE_NAME,
        "persona_names": persona_names,
        "step": len(frames),
    }
    _dump(os.path.join(reverie_dir, "meta.json"), meta)

    # Persona memory folders, copied from the base sim, so the replay state
    # panel (replay_persona_state) has scratch/spatial/associative to render.
    if os.path.isdir(base_personas_dir):
        for name in persona_names:
            src = os.path.join(base_personas_dir, name)
            dst = os.path.join(personas_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)

    # Each agent's full memory stream, written beside its copied memory folder.
    # The State Details panel reads this to show every memory the agent formed
    # (newest first), labelled with the same wall-clock the cards use.
    if memory_streams:
        for name, memories in memory_streams.items():
            _stamp_memory_list(memories, start_dt, sec_per_step)
            ordered = sorted(
                memories, key=lambda m: m.get("created_turn", 0), reverse=True
            )
            persona_dir = os.path.join(personas_dir, name)
            os.makedirs(persona_dir, exist_ok=True)
            _dump(
                os.path.join(persona_dir, "memory_stream.json"),
                {"persona_name": name, "memories": ordered},
            )

    # Each agent's generated daily plan (day outline / hourly / stops), so the
    # plan a run used can be inspected without re-calling the model.
    if plans:
        for name, plan in plans.items():
            persona_dir = os.path.join(personas_dir, name)
            os.makedirs(persona_dir, exist_ok=True)
            _dump(os.path.join(persona_dir, "daily_plan.json"), plan)

    return sim_dir


def _dump(path: str, obj) -> None:
    with open(path, "w") as f:
        # ensure_ascii=False keeps emoji pronunciatios as literal characters.
        json.dump(obj, f, indent=2, ensure_ascii=False)
