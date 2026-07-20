# Harden furnish_williams tmj splice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `furnish_williams.apply_to_file` idempotent (strip-then-reinsert with capture-and-reuse ids) and add loud-failure guards to the splice helpers, so re-running the tool can't silently duplicate layers or mistarget.

**Architecture:** Add a `_strip_layer(text, name)` text-surgery helper + a uniqueness guard + a flat-array guard (Task 1); rewire `apply_to_file` to strip any existing `williams_walls`/`williams_arenas` before inserting and reuse their exact ids so the committed tmj round-trips byte-identically (Task 2). Only `tools/geo/furnish_williams.py` + its tests change; the committed tmj, `compute_relayer`, and the insertion format are untouched.

**Tech Stack:** Python 3.12, `uv run pytest`, `uv run black`. `tools/geo`.

## Global Constraints

- **Branch/track:** `feat/harden-williams-splice-553` off `godot-ga-main`; PR → `godot-ga-main`. Work in the worktree `.claude/worktrees/harden-splice-553/`.
- **Only** `godot-generative-agents/tools/geo/furnish_williams.py` and `godot-generative-agents/tools/geo/test_furnish_williams.py` change. The committed tmj (`upenn_core_urban.tmj`) must remain byte-identical (no `git status` entry) — the tests run on temp copies.
- **Byte-identity is the correctness bar:** running the hardened `apply_to_file` on a copy of the committed tmj must reproduce it exactly, and running it twice must be a no-op — including layer `id`s and arena-object `id`s (capture-and-reuse; never derive ids from the `nextlayerid`/`nextobjectid` headers).
- Do NOT change `compute_relayer`, the `_tile_layer_block`/`_object_layer_block`/`_fmt_data` output format, or `WILLIAMS_ARENA_OBJECTS`.
- Preserve Tiled formatting in all text surgery (no whole-file `json.dump`).
- Commit trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Explicit `git add` paths only.
- Reference: sibling `furnish_*` scripts achieve idempotency by `_strip`-ping their own layers before re-inserting — this brings `furnish_williams` in line.

---

### Task 1: `_strip_layer` + uniqueness & flat-array guards

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py`
- Test: `godot-generative-agents/tools/geo/test_furnish_williams.py`

**Interfaces:**
- Produces: `_layer_name_count(text, name) -> int`, `_strip_layer(text, name) -> str` (removes the one named layer's JSON block + one adjacent separator, format-preserving; no-op if absent; raises if the name appears more than once). Adds a duplicate-name guard + a flat-array assertion inside `_replace_layer_data`.

- [ ] **Step 1: Write the failing tests**

```python
# append to test_furnish_williams.py
def _layers_text(*blocks):
    """A minimal tmj-shaped text: a layers array of the given raw layer blocks,
    joined Tiled-style (',\\n        ' between blocks, 8-space indent)."""
    joined = ",\n        ".join(blocks)
    return '{\n "nextlayerid":9,\n "layers":[\n        ' + joined + "\n ]\n}"


def _tile_block(name, lid, data="0, 0, 0"):
    return (
        "{\n"
        f'         "data":[{data}],\n'
        f'         "id":{lid},\n'
        f'         "name":"{name}",\n'
        '         "type":"tilelayer"\n'
        "        }"
    )


def _obj_block(name, lid):
    return (
        "{\n"
        f'         "id":{lid},\n'
        f'         "name":"{name}",\n'
        '         "objects":[\n                {\n                 "id":1,\n                 "name":"R"\n                }],\n'
        '         "type":"objectgroup"\n'
        "        }"
    )


def test_strip_layer_removes_middle_block_valid_json():
    import json
    text = _layers_text(_tile_block("a", 1), _tile_block("williams_walls", 2), _tile_block("b", 3))
    out = fw._strip_layer(text, "williams_walls")
    parsed = json.loads(out)  # still valid JSON
    names = [L["name"] for L in parsed["layers"]]
    assert names == ["a", "b"]


def test_strip_layer_removes_last_block_valid_json():
    import json
    text = _layers_text(_tile_block("a", 1), _obj_block("williams_arenas", 2))
    out = fw._strip_layer(text, "williams_arenas")
    parsed = json.loads(out)
    assert [L["name"] for L in parsed["layers"]] == ["a"]


def test_strip_layer_absent_is_noop():
    text = _layers_text(_tile_block("a", 1))
    assert fw._strip_layer(text, "williams_walls") == text


def test_strip_layer_duplicate_raises():
    import pytest
    text = _layers_text(_tile_block("williams_walls", 1), _tile_block("williams_walls", 2))
    with pytest.raises(ValueError):
        fw._strip_layer(text, "williams_walls")


def test_replace_layer_data_duplicate_name_raises():
    import pytest
    text = _layers_text(_tile_block("dup", 1), _tile_block("dup", 2))
    with pytest.raises(ValueError):
        fw._replace_layer_data(text, "dup", [1, 2, 3], 3)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -q` (from the worktree root)
Expected: FAIL — `_strip_layer` doesn't exist; `_replace_layer_data` doesn't yet raise on duplicates.

- [ ] **Step 3: Implement the helpers**

Add near the other text helpers (after `_wrap_indent`):

```python
def _layer_name_count(text, name):
    return text.count(f'"name":"{name}"')


def _find_block_bounds(text, name):
    """(start, end) byte offsets of the JSON object whose "name" is `name` — the
    enclosing `{` before the name key through its matching `}` (brace-depth walk,
    string-aware so braces inside string values don't miscount). Raises unless the
    name occurs exactly once."""
    n = _layer_name_count(text, name)
    if n != 1:
        raise ValueError(f"expected exactly one '{name}' layer, found {n}")
    nidx = text.find(f'"name":"{name}"')
    bstart = text.rfind("{", 0, nidx)
    depth, i, in_str, esc = 0, bstart, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return bstart, i + 1
        i += 1
    raise ValueError(f"unterminated layer block for {name}")


def _strip_layer(text, name):
    """Remove the one named layer's JSON block + one adjacent separator, leaving
    the layers array valid and Tiled-formatted. No-op if the layer is absent.
    Raises (via _find_block_bounds) if the name appears more than once."""
    if _layer_name_count(text, name) == 0:
        return text
    bstart, bend = _find_block_bounds(text, name)
    after = text[bend:]
    m = re.match(r",\s*", after)
    if m:  # not the last layer: drop block + trailing separator
        return text[:bstart] + after[m.end():]
    before = text[:bstart]  # last layer: drop the leading separator instead
    m2 = re.search(r",\s*$", before)
    return (before[: m2.start()] if m2 else before) + after
```

Then harden `_replace_layer_data` — add the uniqueness + flat-array guards (replace the current body):

```python
def _replace_layer_data(text, layer_name, new_data, W):
    """Replace the data array of one named tile layer, preserving Tiled's
    W-per-line wrapping so unchanged rows stay byte-identical. Fails loudly if the
    name is not unique or the data array is not flat."""
    n = _layer_name_count(text, layer_name)
    if n != 1:
        raise ValueError(f"expected exactly one '{layer_name}' layer, found {n}")
    nidx = text.find(f'"name":"{layer_name}"')
    bstart = text.rfind("{", 0, nidx)
    dstart = text.find('"data":[', bstart)
    dend = text.find("]", dstart)
    # flat-array invariant: tile-layer data is a flat int array (no nested [...]),
    # which is what lets us stop at the first ']'.
    if "[" in text[dstart + len('"data":[') : dend]:
        raise ValueError(f"{layer_name} data is not a flat array")
    wi = _wrap_indent(text, dstart)
    return text[:dstart] + '"data":[' + _fmt_data(new_data, W, wi) + text[dend:]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -q`
Expected: PASS (existing tests + 5 new).

- [ ] **Step 5: Commit**

```bash
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git commit -m "feat(geo): _strip_layer + uniqueness/flat-array guards for the williams splice (#553)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: idempotent `apply_to_file` (capture-and-reuse ids)

**Files:**
- Modify: `godot-generative-agents/tools/geo/furnish_williams.py`
- Test: `godot-generative-agents/tools/geo/test_furnish_williams.py`

**Interfaces:**
- Consumes: `_strip_layer` (Task 1), `compute_relayer`, the block builders, `WILLIAMS_ARENA_OBJECTS`.
- Produces: an idempotent `apply_to_file(tmj_path)` + a `_bump_header(text, key, atleast)` helper.

- [ ] **Step 1: Write the failing tests**

```python
# append to test_furnish_williams.py
import os, shutil, subprocess, sys

def _committed_tmj():
    return os.path.normpath(
        os.path.join(HERE, "..", "..", "godot", "maps", "upenn_core_urban.tmj")
    )


def test_apply_to_file_reproduces_committed_tmj(tmp_path):
    """Running the hardened splice on a copy of the committed tmj yields a
    byte-identical file (strip-then-reinsert reuses the existing ids)."""
    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    with open(src, "rb") as a, open(dst, "rb") as b:
        assert a.read() == b.read(), "hardened apply_to_file changed the committed tmj"


def test_apply_to_file_idempotent_second_run(tmp_path):
    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    after_one = open(dst, "rb").read()
    fw.apply_to_file(dst)
    assert open(dst, "rb").read() == after_one, "second run was not a no-op"


def test_apply_to_file_no_duplicate_layers(tmp_path):
    import json
    src = _committed_tmj()
    dst = str(tmp_path / "map.tmj")
    shutil.copy2(src, dst)
    fw.apply_to_file(dst)
    fw.apply_to_file(dst)  # twice
    t = json.load(open(dst))
    names = [L["name"] for L in t["layers"]]
    assert names.count("williams_walls") == 1
    assert names.count("williams_arenas") == 1
```

Note: `test_apply_to_file_content_and_order` (existing) must still pass — it now exercises the strip-then-reinsert round-trip.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -q`
Expected: FAIL — current `apply_to_file` inserts unconditionally, so on a committed (already-spliced) tmj it duplicates the two layers (`test_apply_to_file_reproduces_committed_tmj` + `_no_duplicate_layers` fail).

- [ ] **Step 3: Rewrite `apply_to_file` + add `_bump_header`**

Add the header helper near the text helpers:

```python
def _bump_header(text, key, atleast):
    """Set a top-level header field to max(current, atleast) so ids never regress."""
    m = re.search(rf'"{key}":(\d+)', text)
    cur = int(m.group(1)) if m else 0
    return re.sub(rf'"{key}":\d+', f'"{key}":{max(cur, atleast)}', text, count=1)
```

Replace `apply_to_file` with:

```python
def apply_to_file(tmj_path):
    """Idempotently splice williams_walls + williams_arenas into the committed tmj
    and update williams_floor/williams_furniture data, preserving Tiled formatting.
    Strips any prior spliced layers first and reuses their exact ids, so a re-run
    (and a run on the already-spliced committed tmj) is byte-identical. Backs up to
    <path>.bak first."""
    tmj = json.load(open(tmj_path))
    W, H = tmj["width"], tmj["height"]
    new_walls, new_floor, new_furn = compute_relayer(tmj)

    # Capture-and-reuse ids: if a spliced layer already exists, reuse its id;
    # else derive from the max id among the OTHER layers. Never read the
    # nextlayerid/nextobjectid headers for this (a strip doesn't lower them).
    by_name = {L.get("name"): L for L in tmj["layers"]}
    other_max_layer = max(
        (L.get("id", 0) for L in tmj["layers"]
         if L.get("name") not in ("williams_walls", "williams_arenas")),
        default=0,
    )
    walls_id = by_name["williams_walls"]["id"] if "williams_walls" in by_name else other_max_layer + 1
    arenas_id = by_name["williams_arenas"]["id"] if "williams_arenas" in by_name else other_max_layer + 2

    arenas_layer = by_name.get("williams_arenas")
    if arenas_layer and arenas_layer.get("objects"):
        obj_base = min(o["id"] for o in arenas_layer["objects"])
    else:
        other_obj_max = max(
            (o["id"] for L in tmj["layers"]
             if L.get("type") == "objectgroup" and L.get("name") != "williams_arenas"
             for o in L.get("objects", [])),
            default=0,
        )
        obj_base = other_obj_max + 1

    text = open(tmj_path).read()
    shutil.copy2(tmj_path, tmj_path + ".bak")

    # Idempotency: remove any prior spliced layers before re-inserting.
    text = _strip_layer(text, "williams_walls")
    text = _strip_layer(text, "williams_arenas")
    text = _replace_layer_data(text, "williams_floor", new_floor, W)
    text = _replace_layer_data(text, "williams_furniture", new_furn, W)

    fidx = text.find('"name":"williams_furniture"')
    fstart = text.rfind("{", 0, fidx)
    line0 = text.rfind("\n", 0, fstart) + 1
    k8 = text[line0:fstart]
    k9 = k8 + " "
    walls_block = _tile_layer_block(new_walls, walls_id, "williams_walls", W, H, k9)
    arenas_block = _object_layer_block(
        WILLIAMS_ARENA_OBJECTS, arenas_id, "williams_arenas", obj_base, k9
    )
    insertion = walls_block + ",\n" + k8 + arenas_block + ",\n" + k8
    text = text[:line0] + k8 + insertion + text[line0 + len(k8):]

    text = _bump_header(text, "nextlayerid", max(walls_id, arenas_id) + 1)
    text = _bump_header(text, "nextobjectid", obj_base + len(WILLIAMS_ARENA_OBJECTS))
    with open(tmj_path, "w") as fh:
        fh.write(text)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -q`
Expected: PASS (all — including the existing `test_apply_to_file_content_and_order` and the 3 new idempotency tests).

- [ ] **Step 5: Verify the committed tmj is untouched + format**

```bash
cd /Users/yh/Documents/GitHub/agent-sandbox/.claude/worktrees/harden-splice-553
git status --porcelain godot-generative-agents/godot/maps/upenn_core_urban.tmj   # expect empty
uv run black --check godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
```
Expected: no tmj change; black clean (run `uv run black` on the two files and re-stage if it reformats).

- [ ] **Step 6: Commit**

```bash
git add godot-generative-agents/tools/geo/furnish_williams.py godot-generative-agents/tools/geo/test_furnish_williams.py
git commit -m "feat(geo): idempotent apply_to_file — strip-then-reinsert, reuse ids (#553)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** §1 `_strip_layer` → Task 1; §2 idempotent `apply_to_file` + capture-and-reuse ids → Task 2; §3 uniqueness guard → Task 1 (`_find_block_bounds`/`_replace_layer_data`), flat-array guard → Task 1 (`_replace_layer_data`); §4 out-of-scope respected (no tmj/compute_relayer/format change). Verification (idempotency, committed round-trip, strip clean/no-op, duplicate raises, existing test green) → Tasks 1–2 tests. ✓

**Placeholder scan:** none — all code is complete.

**Type consistency:** `_strip_layer`/`_layer_name_count`/`_find_block_bounds` operate on `text: str`. `apply_to_file` reuses ids as ints. `_bump_header(text, key, atleast)` signature matches both call sites. `obj_base`/`walls_id`/`arenas_id` are ints threaded into the existing block builders unchanged.
