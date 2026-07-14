import collections, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC_MATRIX = os.path.join(
    REPO, "godot-generative-agents", "backend", "penn", "the_upenn", "matrix"
)
SRC_MAP = os.path.join(
    REPO, "godot-generative-agents", "godot", "maps", "upenn_core_urban.tmj"
)
W, H = 245, 279
WILLIAMS = "Williams Hall"
ROOM_IDS = list(range(13200, 13205))
ROOMS = {"Classroom A", "Classroom B", "Classroom C", "Office", "Restroom"}


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
    return mdir, tmap


def _flat(p):
    return open(p).read().strip().split(", ")


def _arena_blocks(mdir):
    rows = []
    with open(os.path.join(mdir, "special_blocks", "arena_blocks.csv")) as fh:
        for line in fh:
            if line.strip():
                rows.append([p.strip() for p in line.split(",")])
    return rows


def test_williams_room_arenas_present(tmp_path):
    mdir, _ = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    wr = [r for r in rows if r[2] == WILLIAMS and r[3] not in ("grounds", "lobby")]
    assert sorted(int(r[0]) for r in wr) == ROOM_IDS
    assert {r[3] for r in wr} == ROOMS
    assert any(r[2] == WILLIAMS and r[3] == "lobby" for r in rows)  # atrium stays lobby


def test_williams_partition_walls_sealed(tmp_path):
    import furnish_williams as fw
    import json

    mdir, tmap = _run(str(tmp_path))
    tmj = json.load(open(tmap))
    coll = _flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    # interior partition wall cells must be blocking (fixes walk-through-walls)
    walls = fw.williams_wall_cells(tmj)
    arena = _flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    interior_walls = [
        (x, y) for (x, y) in walls if arena[y * W + x] != "32"
    ]  # not grounds
    assert interior_walls, "expected Williams interior partition walls"
    sealed = sum(1 for (x, y) in interior_walls if coll[y * W + x] == "1")
    assert sealed == len(
        interior_walls
    ), f"only {sealed}/{len(interior_walls)} williams interior wall cells sealed"


def test_every_williams_room_reachable(tmp_path):
    mdir, _ = _run(str(tmp_path))
    coll = _flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _flat(os.path.join(mdir, "maze", "arena_maze.csv"))
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
    for rid in ROOM_IDS:
        assert str(rid) in reached, f"Williams room {rid} unreachable"


def test_no_windows_left_on_furniture(tmp_path):
    import furnish_building as fb
    import json

    _, tmap = _run(str(tmp_path))
    tmj = json.load(open(tmap))
    furn = next(L for L in tmj["layers"] if L.get("name") == "williams_furniture")
    assert not any((g & 0x1FFFFFFF) == fb.WINDOW for g in furn["data"])
