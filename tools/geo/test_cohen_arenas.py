import collections
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC_MATRIX = os.path.join(
    REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
)
SRC_MAP = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)
W, H = 245, 279


def _run(tmp):
    mdir = os.path.join(tmp, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    subprocess.run(
        [
            sys.executable,
            os.path.join(HERE, "add_entrances.py"),
            "--tmj",
            tmap,
            "--matrix",
            mdir,
        ],
        check=True,
        cwd=HERE,
    )
    return mdir


def _read_flat(p):
    return open(p).read().strip().split(", ")


def _arena_blocks(mdir):
    rows = []
    with open(os.path.join(mdir, "special_blocks", "arena_blocks.csv")) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def test_cohen_five_room_arenas(tmp_path):
    mdir = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    rooms = [
        r
        for r in rows
        if r[2] == "Claudia Cohen Hall" and r[3] not in ("grounds", "lobby")
    ]
    assert len(rooms) == 5
    assert sorted(int(r[0]) for r in rooms) == list(range(10700, 10705))
    names = {r[3] for r in rooms}
    assert "Cafeteria 2" in names and "Kitchen 1" in names


def test_cohen_rooms_reachable_through_a_door(tmp_path):
    mdir = _run(str(tmp_path))
    coll = _read_flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _read_flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    reached = _flood_reached_arenas(coll, arena)
    for rid in range(10700, 10705):
        assert str(rid) in reached, f"cohen room {rid} unreachable through the door"


def _flood_reached_arenas(coll, arena):
    seen = [False] * (W * H)
    q = collections.deque()
    for x in range(W):
        for y in (0, H - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True
                q.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True
                q.append((x, y))
    reached = set()
    while q:
        x, y = q.popleft()
        reached.add(arena[y * W + x])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                j = ny * W + nx
                if coll[j] == "0" and not seen[j]:
                    seen[j] = True
                    q.append((nx, ny))
    return reached
