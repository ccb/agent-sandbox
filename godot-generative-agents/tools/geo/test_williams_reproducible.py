"""Reproducibility guard for Williams Hall (#552).

The williams_floor / williams_furniture / williams_arenas layers are authored
inputs. Everything else Williams-related is DERIVED and must regenerate
byte-identically from those inputs: the williams_walls tmj layer (furnish_williams)
and the six matrix CSVs (add_entrances -> block_grass -> block_furniture ->
gen_furniture_matrix). These tests run the derivation on temp copies of the
committed artifacts and assert byte-identity.
"""

import filecmp
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# tools/geo -> godot-generative-agents
GGA = os.path.dirname(os.path.dirname(HERE))
COMMITTED_TMJ = os.path.join(GGA, "godot", "maps", "upenn_core_urban.tmj")
COMMITTED_MATRIX = os.path.join(GGA, "backend", "penn", "the_upenn", "matrix")

MATRIX_CSVS = [
    os.path.join("maze", "collision_maze.csv"),
    os.path.join("maze", "arena_maze.csv"),
    os.path.join("maze", "furniture_maze.csv"),
    os.path.join("special_blocks", "arena_blocks.csv"),
    os.path.join("special_blocks", "furniture_blocks.csv"),
    os.path.join("special_blocks", "furniture_spots.csv"),
]


def test_furnish_williams_roundtrip_is_byte_identical():
    import furnish_williams as fw

    tmp = tempfile.mktemp(suffix=".tmj")
    shutil.copy2(COMMITTED_TMJ, tmp)
    try:
        fw.apply_to_file(tmp)
        with open(COMMITTED_TMJ, "rb") as a, open(tmp, "rb") as b:
            assert a.read() == b.read(), "furnish_williams re-run changed the tmj"
    finally:
        for p in (tmp, tmp + ".bak"):
            if os.path.exists(p):
                os.remove(p)


def test_matrix_chain_reproduces_committed_csvs():
    workdir = tempfile.mkdtemp()
    try:
        tmj = os.path.join(workdir, "map.tmj")
        matrix = os.path.join(workdir, "matrix")
        shutil.copy2(COMMITTED_TMJ, tmj)
        shutil.copytree(COMMITTED_MATRIX, matrix)

        for script in (
            "add_entrances.py",
            "block_grass.py",
            "block_furniture.py",
            "gen_furniture_matrix.py",
        ):
            r = subprocess.run(
                [
                    sys.executable,
                    os.path.join(HERE, script),
                    "--tmj",
                    tmj,
                    "--matrix",
                    matrix,
                ],
                capture_output=True,
                text=True,
            )
            assert r.returncode == 0, f"{script} failed: {r.stderr}"

        for rel in MATRIX_CSVS:
            regenerated = os.path.join(matrix, rel)
            committed = os.path.join(COMMITTED_MATRIX, rel)
            assert filecmp.cmp(
                regenerated, committed, shallow=False
            ), f"{rel} differs after regeneration"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
