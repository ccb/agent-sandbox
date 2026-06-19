# CLAUDE.md — generative-agents (Smallville port)

Guidance for Claude Code when working in `generative-agents/`. The repo-root
`../CLAUDE.md` (the engine) still applies; this file adds what's specific to this
subproject. See `README.md` here for setup, architecture, and how the replay works.

## ⚠️ Edit the replay UI under `frontend_overrides/`, NOT `frontend/`

`frontend/` is **git-ignored**. `setup.sh` regenerates it on every run by rsyncing the
upstream clone with `--delete` and then copying `frontend_overrides/` on top — so any edit
made directly under `frontend/` is **untracked and gets wiped**.

The committed source of truth for the replay UI lives in `frontend_overrides/`, mirroring
the `frontend/` layout. For example:

| You want to change… | Edit this (tracked) | which setup.sh copies to (ignored) |
| --- | --- | --- |
| Replay page layout | `frontend_overrides/templates/home/home.html` | `frontend/templates/home/home.html` |
| Replay styles | `frontend_overrides/static_dirs/css/style.css` | `frontend/static_dirs/css/style.css` |
| Phaser / replay JS | `frontend_overrides/templates/home/main_script.html` | `frontend/templates/home/main_script.html` |

Workflow: edit the `frontend_overrides/` file, then mirror the same change into the live
`frontend/` copy so you can test against a running server without re-running `setup.sh`
(e.g. `cp frontend_overrides/<path> frontend/<path>`). Commit only the
`frontend_overrides/` files — `git status` won't even show the `frontend/` copies.

`style.css` is shared by both `templates/home/home.html` (the redesigned map+agent layout)
and `templates/demo/demo.html` (the upstream demo, a plain block layout). Scope new
layout rules so you don't break the other page — e.g. the map fills its column via
`#sim-map-col #game-container` while the bare `#game-container` keeps a fixed-height
default for the demo.

## Two Python environments

The **backend/engine** runs in the repo's `uv` project env (one level up):
`uv run python -m backend.run_simulation`. The **Django frontend** needs its own
Python 3.9 venv (`frontend-venv/`, Django 2.2) — `run-replay.sh` provisions both. Don't
try to run the frontend from the engine env.
