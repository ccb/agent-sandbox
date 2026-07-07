---
description: Serve the live Penn simulation backend for the Godot viewer to follow (mock or real-LLM)
argument-hint: "[--brain llm] [--tick-seconds N] [--port N]"
---

`/serve-backend` starts the **live Penn simulation backend** — it steps the configured
Penn world in the backend's self-stepping live loop and serves it over HTTP + WebSocket
(`godot-generative-agents/backend/api.py`) so the Godot viewer (or the web companion)
follows it in real time. Pairs with `/run-viewer`. Full docs:
`godot-generative-agents/README.md`.

**One-time deps** (from the repo root):
- Mock brain: `uv sync --extra server`
- Real LLM: `uv sync --extra server --extra llm` (adds the Anthropic SDK)

The server is **long-running**, so launch it in the background (`run_in_background:
true`), then report the URL and health. Run everything from the **repo root** (so `uv`
finds the env). It binds `http://127.0.0.1:8080` by default (`--host` / `--port` to
change).

Pick the brain from `$ARGUMENTS` (default: mock):

1. **Mock brain (default) — real requests, no keys, no spend.** The go-to for
   developing the viewer:
   ```
   uv run python godot-generative-agents/backend/penn/serve_penn.py --tick-seconds 0.1
   ```
   The mock never speaks, so the scripted `meetings:` dialogue plays on the fly.

2. **Real LLM (`--brain llm`) — Anthropic Claude Haiku drives the cast (costs money).**
   Needs `ANTHROPIC_API_KEY` (export it, or put it in the repo-root `.env` — every
   backend CLI loads it; **never** `OPENAI_API_KEY`/`LLM_API_KEY`). The server refuses
   to start without it. It boots **PAUSED** — no model call fires until someone presses
   **▶ Start** in the viewer sidebar or hits `curl -X POST http://127.0.0.1:8080/resume`.
   The world YAML's `max_cost_usd` (or `--max-cost`) is a hard kill-switch (~$0.10 for a
   full 3-agent day).
   ```
   uv run python godot-generative-agents/backend/penn/serve_penn.py --brain llm
   ```

After it's up, **verify and connect:**
- Health: `curl -s http://127.0.0.1:8080/health` (and `GET /live` for the world meta).
- Point the viewer at it: `/run-viewer http://127.0.0.1:8080` (or
  `SIM_API_URL=http://127.0.0.1:8080 ./godot-generative-agents/run.sh`).

**Useful flags** (`serve_penn.py --help` for the full list): `--tick-seconds` (loop
floor), `--steps N` / `--endless`, `--host` / `--port`, `--start-paused` /
`--no-start-paused` (override the paused-boot default), `--no-monitor` (silence the
terminal LLM-request log), `--model` (override the config's model), `--token` (or
`SIM_API_TOKEN`, required for a non-loopback `--host`).

**Offline alternative — no server at all:** to just watch a *baked* replay, skip this
command and bake a file with
`LLM_PROVIDER=mock uv run python godot-generative-agents/backend/penn/generate_penn_replay.py --steps 400`,
then play it via `/run-viewer`'s landing menu.

Do not commit or push anything — this command only serves the backend.
