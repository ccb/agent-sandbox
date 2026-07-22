---
description: Launch the Godot viewer (the frontend) — landing menu, a baked replay, or a live backend
argument-hint: "[scene.tscn | backend URL]"
---

`/run-viewer` launches the **Godot viewer** — the frontend for the
`godot-generative-agents/` Penn campus sim. It's a *viewer*: the simulation runs in
Python (a baked replay file, or a live backend served by `/serve-backend`) and Godot
draws the campus + the agents moving across it. Full docs:
`godot-generative-agents/README.md`.

**Prerequisite:** Godot **4.6** must be reachable — on your `PATH` as `godot` or
`godot4`, or the standard macOS app bundle (`/Applications/Godot.app`). `run.sh` finds
it and prints an install hint if it can't. (No Python env needed to *launch* the
viewer — that's the backend's job.)

The launcher is `godot-generative-agents/run.sh` (it works from any directory, finds
the project, auto-imports assets on the first run, and warns if the bundled replay is
missing/stale). **Godot opens a GUI window and blocks until closed, so launch it in
the background** (`run_in_background: true`) and report that the window opened — don't
wait on it in the foreground.

Pick the invocation from `$ARGUMENTS`:

1. **No argument → the landing menu (default).** Boots the front door where the user
   picks *Watch a replay*, *open a local `.json`*, or *Run a live simulation*:
   ```
   ./godot-generative-agents/run.sh
   ```
2. **A scene path (ends in `.tscn`) → deep-link, skipping the menu.** e.g.
   `scenes/viewer.tscn` (agents on the campus) or `scenes/campus_urban.tscn` (bare
   campus):
   ```
   ./godot-generative-agents/run.sh scenes/viewer.tscn
   ```
3. **A backend URL (starts with `http`) → live mode.** Point the viewer at a running
   backend (start one first with `/serve-backend`):
   ```
   SIM_API_URL=<url> ./godot-generative-agents/run.sh
   ```
   (Equivalently, leave `$ARGUMENTS` empty and type the URL into the menu's *Run a
   live simulation* field — it probes `GET /live` before connecting.)

**Bundled replay stale/missing?** `run.sh` prints a warning if
`godot/maps/penn_replay.json` (a git-ignored, per-checkout artifact) is absent or
older than its inputs. Bake it from the **repo root**, then relaunch:
```
LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py
```

Do not commit or push anything — this command only launches the viewer.
