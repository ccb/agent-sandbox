"""Tests for the furniture-solidity server-side additions in catalog_web.py.

Run:
    cd tools/geo && uv run pytest test_catalog_web.py -q
"""

from __future__ import annotations

import json
import sys
import os

import pytest

# Make sure tools/geo is importable when run from repo root
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import block_furniture
import catalog_web


def load_catalog():
    return catalog_web.load_catalog()


def load_tmj():
    return json.load(open(catalog_web.TMJ))


# ---------------------------------------------------------------------------
# test_furniture_rows_cover_all_painted_gids
# ---------------------------------------------------------------------------


def test_furniture_rows_cover_all_painted_gids():
    catalog = load_catalog()
    rows = catalog_web.furniture_solidity_rows(catalog)
    tmj = load_tmj()

    counts = block_furniture.furniture_gid_counts(tmj)

    # One row per distinct furniture gid
    assert len(rows) == len(counts), f"rows={len(rows)}, distinct gids={len(counts)}"

    row_gids = {r["gid"] for r in rows}
    assert row_gids == set(
        counts.keys()
    ), "row gids do not match furniture gid counts keys"

    # Each row's walkable flag must mirror the current allowlist exactly (the
    # allowlist is user-editable via the menu, so assert the invariant, not
    # hardcoded gids). Both states must be represented so the flag is meaningful.
    walk = block_furniture.load_walkable_furniture()
    for r in rows:
        assert r["walkable"] is (r["gid"] in walk), (
            f"gid {r['gid']}: walkable={r['walkable']} but "
            f"{'in' if r['gid'] in walk else 'not in'} allowlist"
        )
    assert any(r["walkable"] for r in rows), "no walkable furniture rows"
    assert any(not r["walkable"] for r in rows), "no solid furniture rows"

    # Every row's sheet must be in the catalog
    catalog_sheets = set(catalog["sheets"].keys())
    for r in rows:
        assert (
            r["sheet"] in catalog_sheets
        ), f"gid {r['gid']}: sheet '{r['sheet']}' not in catalog sheets {catalog_sheets}"


# ---------------------------------------------------------------------------
# test_save_walkable_round_trips
# ---------------------------------------------------------------------------


def test_save_walkable_round_trips(tmp_path):
    path = str(tmp_path / "walkable_furniture_test.json")

    # Save a fresh payload
    catalog_web.save_walkable_json({"walkable_gids": {"5": "x"}}, path=path)
    loaded = catalog_web.load_walkable_json(path=path)
    assert loaded.get("walkable_gids") == {"5": "x"}, f"round-trip failed: {loaded}"

    # Now save a payload with a _README already in the file, then save without it
    initial = {
        "_README": "do not lose me",
        "walkable_gids": {"5": "x"},
    }
    catalog_web.save_walkable_json(initial, path=path)

    # Save a payload that omits _README — the existing _README should be preserved
    catalog_web.save_walkable_json({"walkable_gids": {"7": "y"}}, path=path)
    loaded2 = catalog_web.load_walkable_json(path=path)
    assert loaded2.get("walkable_gids") == {"7": "y"}, f"gids not updated: {loaded2}"
    assert (
        loaded2.get("_README") == "do not lose me"
    ), f"_README was not preserved: {loaded2}"
