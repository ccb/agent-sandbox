"""Format-preserving writer for the committed Tiled map (#641).

Thirteen geo scripts used to rewrite ``godot/maps/upenn_core_urban.tmj``
minified (``json.dump(..., separators=(",", ":"))``), collapsing a 16,900-line
reviewable file to one line, and each clobbered its ``.bak`` on every re-run.
This module gives them one shared writer that keeps Tiled's pretty layout --
tile-layer ``data`` wrapped one map-row per line, keys sorted -- so a regen is
a per-cell reviewable diff, plus a first-run-wins backup that never clobbers
the pristine copy.

The serializer follows the committed map's dominant convention: array-of-object
elements separated by ", " then newline, object arrays closed with "]" inline.
It byte-reproduces the committed map (pinned in test_tmj_io.py). ponytail: it
assumes finite maps with flat tile-layer data arrays -- the only kind this
project uses; infinite/chunked maps are out of scope.
"""

from __future__ import annotations

import json
import os
import shutil


def _fmt_data(data, width, cont):
    """Render a flat gid array Tiled-style: `width` values per line joined by
    ", ", successive rows joined by ",\\n" + the continuation indent `cont`."""
    rows = [
        ", ".join(str(g) for g in data[r : r + width])
        for r in range(0, len(data), width)
    ]
    return (",\n" + cont).join(rows)


def _enc_value(value, keypad, key=None, width=None):
    if isinstance(value, dict):
        return _enc_obj(value, keypad + " ", brace_pad=keypad)
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(isinstance(e, dict) for e in value):
            brace_pad = " " * (len(keypad) + 7)  # Tiled indents array items keypad+7
            item_pad = brace_pad + " "
            items = [_enc_obj(e, item_pad, brace_pad=brace_pad) for e in value]
            return "[\n" + brace_pad + (", \n" + brace_pad).join(items) + "]"
        if key == "data" and width is not None:  # tile-layer data: one map-row/line
            return "[" + _fmt_data(value, width, keypad + "   ") + "]"
        return "[" + ", ".join(json.dumps(e) for e in value) + "]"
    return json.dumps(value)  # exact float repr, true/false, string escaping


def _enc_obj(obj, keypad, top=False, brace_pad=""):
    # A tile layer carries both "data" and "width" -- wrap its data by that width.
    width = obj.get("width") if ("data" in obj and "width" in obj) else None
    pairs = [f'"{k}":{_enc_value(obj[k], keypad, k, width)}' for k in sorted(obj)]
    body = (",\n" + keypad).join(pairs)
    if top:  # the map object: first key inline after "{ ", no closing indent
        return "{ " + body + "\n}"
    return "{\n" + keypad + body + "\n" + brace_pad + "}"


def dump_tiled(tmj: dict) -> str:
    """Serialize a Tiled map dict to its pretty JSON text (no trailing newline)."""
    return _enc_obj(tmj, " ", top=True)


def backup_once(path: str) -> str | None:
    """Copy `path` -> `path`.bak only if the .bak is absent (first-run-wins), so a
    re-run never overwrites the pristine backup with already-modified output.
    Returns the .bak path, or None if it already existed."""
    bak = path + ".bak"
    if os.path.exists(bak):
        return None
    shutil.copy2(path, bak)
    return bak


def write_tmj(path: str, tmj: dict, backup: bool = True) -> str | None:
    """Back up (first-run-wins) then write `tmj` in Tiled-pretty format.
    Returns the .bak path if a backup was taken this call, else None (so a
    caller's log can tell the truth: first-run-wins means no backup on re-runs)."""
    bak = backup_once(path) if backup else None
    with open(path, "w") as fh:
        fh.write(dump_tiled(tmj))
    return bak
