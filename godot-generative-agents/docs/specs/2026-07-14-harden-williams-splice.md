# Harden the furnish_williams tmj splice — re-run safety + loud-failure guards (#553)

**Issue:** #553 · **Branch:** `feat/harden-williams-splice-553` off `godot-ga-main` ·
**Track:** godot-ga-main (tools/geo only). Follow-up to #538; companion to #552.

## Goal

`tools/geo/furnish_williams.py` splices `williams_walls` + `williams_arenas`
into the committed Tiled map via format-preserving text surgery. The shipped
artifact is correct (a run-once step), but the splice has sharper edges than the
idempotent `_strip`-then-reinsert pattern every other `furnish_*` script uses.
Make it re-run-safe and fail loudly on the assumptions it silently relies on —
matching the geo pipeline's conventions so the next run (a fresh osm bake, the
#552 art realignment) can't silently corrupt the tmj.

## Current state (verified)

- **`apply_to_file` is not re-run-safe.** `compute_relayer` is already
  idempotent (an existing `williams_walls` seeds its output), but the splice
  *unconditionally* inserts fresh `williams_walls` + `williams_arenas` blocks
  (ids `maxid+1/+2`) before `williams_furniture`. Re-running on the
  already-spliced committed tmj produces **duplicate layer names + duplicate
  arena objects**; `_replace_layer_data`/`read_sections` first-match lookups
  would then silently target the wrong copy.
- **`_replace_layer_data` assumes a flat integer `data` array** — `dend =
  text.find("]", dstart)` stops at the first `]`, which is only correct because
  tile-layer data has no nested brackets. Undocumented invariant.
- **Layer-name lookups take the first match** (`text.find('"name":"<layer>"')`)
  with no uniqueness guard — safe today (names unique in the committed tmj) but a
  duplicate silently mistargets.
- Every sibling (`furnish_college_hall`, `furnish_houston`, …) makes its picture
  writes idempotent by `_strip`-ping its own layers before re-inserting. This
  splice is the outlier.

## Design

### 1. `_strip_layer(text, name)` — excise a layer block (new)

Remove a named layer's complete JSON object from the raw tmj text,
format-preserving, so the file is byte-identical to never having had it:

- Locate the block: find `"name":"<name>"`, `rfind("{")` before it for the
  block start, and walk a brace counter from that `{` to its matching `}` for
  the block end (the object may contain nested braces/arrays — objectgroups do,
  so a brace-depth walk is required, not a naive `}` search).
- Excise the block **and one adjacent separator**: the `,\n<indent>` that joins
  it to its sibling (drop the leading separator if the block is last in the
  layers array, else the trailing one), so the surviving `layers` array stays
  valid JSON with no dangling/double commas.
- If `<name>` is absent, return `text` unchanged (makes the strip a safe no-op).
- Assert the name occurs **at most once** before stripping (see §3); strip the
  single occurrence.

### 2. `apply_to_file` becomes idempotent

Before inserting, strip any existing `williams_walls` and `williams_arenas`
from the text (§1). Then the current relayer + insert runs on a clean base.
Because `compute_relayer` already reproduces identical arrays from the seeded
walls, **re-running `apply_to_file` on an already-spliced tmj yields a
byte-identical file** — this byte-identity is the idempotency test and the
binding correctness bar.

**Id stability (the subtle part):** the byte-identical requirement covers the
new layers' `id`s *and* the arena objects' `id`s. Deriving ids from the
`"nextlayerid"`/`"nextobjectid"` header fields is wrong two ways: a strip does
not lower them (so ids would climb on re-run), and the committed objects' ids
came from the *pre-splice* `nextobjectid`, which may have had gaps — so a
"max present + 1" recompute isn't guaranteed to reproduce them either. Use
**capture-and-reuse**: read the ids off the layers *before* stripping and reuse
them on re-insert.
- `williams_walls` / `williams_arenas` layer `id`: if that layer currently
  exists, reuse its `id`; else assign `max(layer ids)+1` / `+2`.
- arena object `id` base: if `williams_arenas` currently exists, reuse the
  `min` of its object ids; else `max(object ids across all objectgroups)+1`.
- header `nextlayerid`/`nextobjectid`: `max(current header value, last id
  assigned + 1)` so they never regress.
On the committed tmj this reuses the exact ids already there → byte-identical;
on a never-spliced tmj it derives fresh. The idempotency + committed-round-trip
tests enforce it.

### 3. Loud-failure guards on the splice helpers

- **Uniqueness:** a small helper (or inline in `_replace_layer_data` and
  `_strip_layer`) asserts `text.count('"name":"<name>"') == 1` and raises
  `ValueError(f"expected exactly one '{name}' layer, found {n}")` otherwise.
  Fails loudly instead of mistargeting the first of several.
- **Flat-array:** in `_replace_layer_data`, after locating `dstart..dend`, assert
  the extracted data segment contains no `[` (i.e. it is a flat array) and raise
  a clear error otherwise; add a one-line comment stating the invariant.

### 4. Out of scope

- The splice **insertion format** and `compute_relayer` logic (unchanged —
  already correct/idempotent).
- #552's `furnish_building` art realignment (separate issue).
- Any matrix regeneration or tmj re-commit — this task changes *only*
  `furnish_williams.py` + its tests; the committed tmj is untouched (running the
  hardened `apply_to_file` on the current committed tmj must reproduce it
  byte-identically, which is the idempotency test).

## Verification

- **Unit tests** (`test_furnish_williams.py`, appended):
  - `apply_to_file` run twice on a temp copy of the committed tmj → the file is
    byte-identical after the second run (idempotency).
  - `apply_to_file` on the committed (already-spliced) tmj still yields exactly
    one `williams_walls` + one `williams_arenas` (no duplication) and re-parses.
  - `_strip_layer` removes a named layer cleanly (re-parses as valid JSON, layer
    absent, sibling layers intact) and is a no-op when the layer is absent.
  - A tmj text with two `williams_walls` names raises `ValueError` from the
    uniqueness guard.
  - The existing `test_apply_to_file_content_and_order` stays green (now a
    strip-then-reinsert round-trip rather than a duplicating insert).
- `uv run pytest godot-generative-agents/tools/geo/test_furnish_williams.py -q`
  + `uv run black --check` on the touched files. The committed tmj must NOT
  appear in `git status` after running the tests (byte-identical).
