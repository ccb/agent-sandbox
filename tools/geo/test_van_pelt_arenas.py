import collections, os, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SRC_MATRIX = os.path.join(REPO, "godot-generative-agents", "sim", "the_upenn", "matrix")
SRC_MAP = os.path.join(REPO, "godot-generative-agents", "maps", "upenn_core_urban.tmj")
W, H = 245, 279

def _run(tmp):
    """Copy map+matrix into tmp, run add_entrances against them, return paths."""
    mdir = os.path.join(tmp, "matrix")
    shutil.copytree(SRC_MATRIX, mdir)
    tmap = os.path.join(tmp, "map.tmj")
    shutil.copy2(SRC_MAP, tmap)
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", tmap, "--matrix", mdir],
                   check=True, cwd=HERE)
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

def test_25_van_pelt_room_arenas_present(tmp_path):
    mdir = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    vp_rooms = [r for r in rows if r[2] == "Van Pelt Library" and r[3] not in ("grounds", "lobby")]
    assert len(vp_rooms) == 25
    ids = sorted(int(r[0]) for r in vp_rooms)
    assert ids == list(range(13000, 13025))
    names = {r[3] for r in vp_rooms}
    assert "Moelis Family Grand Reading Room" in names and "Kamin Gallery" in names
    # lobby retained for leftover circulation
    assert any(r[2] == "Van Pelt Library" and r[3] == "lobby" for r in rows)

def test_williams_unchanged(tmp_path):
    mdir = _run(str(tmp_path))
    rows = _arena_blocks(mdir)
    will = [r for r in rows if r[2] == "Williams Hall"]
    kinds = sorted(r[3] for r in will)
    assert kinds == ["grounds", "lobby"]  # no room subdivision

def test_every_room_arena_reachable_from_a_door(tmp_path):
    mdir = _run(str(tmp_path))
    coll = _read_flat(os.path.join(mdir, "maze", "collision_maze.csv"))
    arena = _read_flat(os.path.join(mdir, "maze", "arena_maze.csv"))
    # BFS over all walkable cells from every map-border walkable cell; collect arenas.
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
    for rid in range(13000, 13025):
        assert str(rid) in reached, f"room arena {rid} unreachable through the door"

def test_idempotent(tmp_path):
    mdir = _run(str(tmp_path))
    a = open(os.path.join(mdir, "maze", "arena_maze.csv")).read()
    c = open(os.path.join(mdir, "maze", "collision_maze.csv")).read()
    subprocess.run([sys.executable, os.path.join(HERE, "add_entrances.py"),
                    "--tmj", os.path.join(str(tmp_path), "map.tmj"), "--matrix", mdir],
                   check=True, cwd=HERE)
    assert open(os.path.join(mdir, "maze", "arena_maze.csv")).read() == a
    assert open(os.path.join(mdir, "maze", "collision_maze.csv")).read() == c
