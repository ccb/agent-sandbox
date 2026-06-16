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

START_DATE = "February 13, 2023"
# Smallville's clock: one step is 10 seconds of in-game time.
SEC_PER_STEP = 10
MAZE_NAME = "the_ville"


def _fmt_time(dt: datetime.datetime) -> str:
    """Upstream's curr_time format, e.g. 'February 13, 2023, 08:00:10'."""
    return f"{dt:%B} {dt.day}, {dt.year}, {dt:%H:%M:%S}"


def write_simulation(
    storage_root: str,
    sim_code: str,
    frames: list[dict],
    start_dt: datetime.datetime,
    start_tiles: dict[str, tuple[int, int]],
    base_personas_dir: str,
    sec_per_step: int = SEC_PER_STEP,
) -> str:
    """Materialize a replayable sim folder under ``storage_root/sim_code``.

    ``frames`` is one dict per step: ``{persona_name: {movement, pronunciatio,
    description, chat}}``. ``start_tiles`` seeds ``environment/0.json``.
    ``base_personas_dir`` is the base sim's ``personas/`` folder, copied in so the
    frontend's persona state panel has memory to show. Returns the sim folder path.
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
        "start_date": START_DATE,
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

    return sim_dir


def _dump(path: str, obj) -> None:
    with open(path, "w") as f:
        # ensure_ascii=False keeps emoji pronunciatios as literal characters.
        json.dump(obj, f, indent=2, ensure_ascii=False)
