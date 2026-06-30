import collections, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC_MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
SRC_MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
W, H = 245, 279
HOUSTON = "Houston Hall"
ROOM_IDS = list(range(11400, 11409))
ROOMS = {
    "Reception Hall", "Billiard Room", "Bathroom", "Shuffle Board Room",
    "Ladies Parlor", "Secretarys Office", "Chess Room", "Reading Room",
    "Correspond",
}


def _run(tmp):
    mdir = os.path.join(tmp, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", tmap, "--matrix", mdir], check=True, cwd=HERE)
    return mdir, tmap


def _read_flat(p):
    return open(p).read().strip().split(", ")


def _arena_blocks(mdir):
    rows = []
    with open(os.path.join(mdir, "special_blocks", "arena_blocks.csv")) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def test_9_houston_room_arenas_present(tmp_path):
    mdir, _ = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    hr = [r for r in rows if r[2] == HOUSTON and r[3] not in ("grounds", "lobby")]
    assert len(hr) == 9
    assert sorted(int(r[0]) for r in hr) == ROOM_IDS
    assert {r[3] for r in hr} == ROOMS
    assert any(r[2] == HOUSTON and r[3] == "lobby" for r in rows)


def test_partition_walls_block(tmp_path):
    import furnish_houston as fh
    mdir, tmap = _run(str(tmp_path))
    tmj = json.load(open(tmap))
    interior = fh.houston_interior_cells(tmj, mdir)
    walls = fh.houston_wall_cells(tmj, interior, W, H)
    assert walls, "expected Houston partition walls"
    coll = _read_flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    for (x, y) in walls:
        assert coll[y * W + x] == "1", f"partition cell {(x, y)} is not blocking"


def test_every_houston_room_reachable_from_a_door(tmp_path):
    mdir, _ = _run(str(tmp_path))
    coll = _read_flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _read_flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    seen = [False] * (W * H)
    q = collections.deque()
    for x in range(W):
        for y in (0, H - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True; q.append((x, y))
    for y in range(H):
        for x in (0, W - 1):
            i = y * W + x
            if coll[i] == "0" and not seen[i]:
                seen[i] = True; q.append((x, y))
    reached = set()
    while q:
        x, y = q.popleft()
        reached.add(arena[y * W + x])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H:
                j = ny * W + nx
                if coll[j] == "0" and not seen[j]:
                    seen[j] = True; q.append((nx, ny))
    for rid in ROOM_IDS:
        assert str(rid) in reached, f"Houston room arena {rid} unreachable through the door"


def test_other_buildings_unchanged_regression(tmp_path):
    mdir, _ = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    vp = [r for r in rows if r[2] == "Van Pelt Library" and r[3] not in ("grounds", "lobby")]
    fi = [r for r in rows if r[2] == "Fisher Fine Arts Library" and r[3] not in ("grounds", "lobby")]
    assert len(vp) == 25 and len(fi) == 6  # adding Houston disturbs neither


def test_idempotent(tmp_path):
    mdir, tmap = _run(str(tmp_path))
    a = open(os.path.join(mdir, "maze", "arena_maze.csv")).read()
    c = open(os.path.join(mdir, "maze", "collision_maze.csv")).read()
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", tmap, "--matrix", mdir], check=True, cwd=HERE)
    assert open(os.path.join(mdir, "maze", "arena_maze.csv")).read() == a
    assert open(os.path.join(mdir, "maze", "collision_maze.csv")).read() == c
