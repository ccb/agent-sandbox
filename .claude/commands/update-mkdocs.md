---
description: Update the local MkDocs site to match the current engine, then verify it builds
argument-hint: "[optional: subsystem or symbol that changed]"
---

The local docs site lives under `mkdocs/` (config `mkdocs/mkdocs.yml`, pages in
`mkdocs/docs/`). It is **local-only** — there is no deploy step. The site is the
generated home page (`docs/index.md`) plus an **API reference** under
`docs/api/`, whose pages pull docstrings straight from the engine via
mkdocstrings `:::` directives. Because the reference mirrors real symbols, it
drifts whenever the engine's public API moves. This command resyncs it.

This command is **invoked on demand only** — it is not a hook and does nothing
automatically. Run it after the engine's public surface changes (new/renamed/
moved classes or functions, a new subsystem, a removed export).

**Scope:** `$ARGUMENTS` if given (the subsystem or symbol that changed — focus
there). Otherwise review the whole API reference against the engine.

Work from the repo root with the project environment (`uv run`). Steps:

1. **Find the drift.** Each page in `mkdocs/docs/api/` targets specific symbols
   with `::: text_adventure_games.<module>.<Symbol>` (some list explicit
   `members:`). Compare those targets against the actual engine:
   - Renamed/moved symbol → update the dotted path.
   - New public class/function in an existing subsystem → add a `:::` block (or a
     `members:` entry) on the matching page, keeping `heading_level: 2` and the
     surrounding style.
   - Removed/private symbol → delete its block or `members:` entry.
   - A whole new subsystem → add a new `docs/api/<name>.md` page modeled on the
     existing ones (short intro sentence, then the `:::` blocks).

2. **Keep the nav in sync.** Every page under `docs/api/` must appear under the
   `API reference:` section in `mkdocs/mkdocs.yml`, and every nav entry must point
   at a real file. Add/remove/rename nav entries to match step 1.

3. **Keep the prose links accurate.** The overview at `docs/api/index.md` lists
   the subsystems with relative links, and `docs/index.md` ("Where to go next")
   points into the reference. Update both if pages were added, removed, or
   renamed so no link dangles.

4. **Verify it builds.** Build in strict mode so broken references and
   missing-docstring warnings fail loudly. `uv run --extra docs` pulls in the docs
   dependencies on the fly:

   ```
   cd mkdocs && uv run --extra docs mkdocs build --strict
   ```

   `--strict` must exit 0. Fix any warning it surfaces (a dangling link, a
   `:::` path that no longer resolves) rather than silencing it. `mkdocs build`
   writes to `mkdocs/site/`, which is git-ignored — leave it untracked.

Keep edits minimal and match the surrounding style — these docs are read by
first/second-year undergraduates. Do not commit or push; report what changed and
the `--strict` build result so it can be reviewed.
