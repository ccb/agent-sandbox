# Web viewer (Godot replay in the browser)

A small **React + Vite + TypeScript** shell that embeds the Godot Penn-campus
replay as a **WebAssembly** build, so you can watch the agents walk the campus in a
browser — no native Godot install needed to *view* it.

It's also the foundation for a future **generative-agents-style companion app**
(side panels with each agent's current action / location, a timeline scrubber,
etc.). Those panels will read the same `penn_replay.json` the Godot canvas plays
(typed in [`src/types/replay.ts`](src/types/replay.ts)), so they never have to pull
state out of Godot.

## How it stays "no recompile"

There are two kinds of change, and neither rebuilds the React app:

| What changed | What you run | Why no React rebuild |
| --- | --- | --- |
| **New sim / replay** | `pnpm gen:replay` | The viewer **fetches** `penn_replay.json` at runtime (it's not packed into the build). Replace the file, refresh. |
| **Godot scripts / scenes / art** | `pnpm export:godot` | Vite serves `public/` statically, so the re-exported WASM is picked up on the next refresh. |

The React/Vite dev server can keep running through both.

## Prerequisites

- **Node** 18+ and **pnpm** (this project uses pnpm; the version is pinned via the
  `packageManager` field in `package.json`). Install pnpm with `brew install pnpm`
  or `corepack enable`.
- **Godot 4.6.x** with the matching **Web export templates** installed. The first
  `pnpm export:godot` will fail with a clear message until you do this:
  *Godot editor → Editor → Manage Export Templates → Download and Install*
  (download the version that matches your editor, e.g. `4.6.3.stable`).
- **uv** (already used by this repo) for `pnpm gen:replay`, which runs the
  Python sim.

If your Godot isn't at the macOS default (`/Applications/Godot.app/Contents/MacOS/Godot`),
set `GODOT_BIN`, e.g. `GODOT_BIN=/path/to/Godot pnpm export:godot`.

## Run it

```bash
cd godot-generative-agents/web
pnpm install
pnpm gen:replay     # writes public/replay/penn_replay.json (committed copy is also fine)
pnpm export:godot   # writes public/godot/ (the WASM build)
pnpm dev            # open the printed http://localhost:… URL
```

You should see the campus load and Maya, Professor Ellis and Diego walk it with
name + activity labels — the same scene as the desktop `penn_replay.tscn`.

## How the embed works

- [`vite.config.ts`](vite.config.ts) sets the `Cross-Origin-Opener-Policy` /
  `Cross-Origin-Embedder-Policy` headers Godot's threaded WASM needs to run
  (cross-origin isolation). If headers ever fight you locally, you can instead
  export single-threaded by setting `variant/thread_support=false` in
  `../export_presets.cfg`.
- [`src/components/GodotCanvas.tsx`](src/components/GodotCanvas.tsx) loads the
  exported `index.js` (which defines Godot's `Engine`) and starts it onto a
  `<canvas>` in the component — so panels can live in the same DOM and we can later
  talk to Godot via `JavaScriptBridge`.
- [`scripts/export-godot.sh`](scripts/export-godot.sh) temporarily points the
  project's main scene at `penn_replay.tscn` for the export only (desktop F5 still
  opens `main.tscn`).

## Layout

```
web/
  package.json          # dev / build / export:godot / gen:replay scripts
  vite.config.ts        # COOP/COEP headers for cross-origin isolation
  index.html
  src/
    main.tsx
    App.tsx             # canvas now; room for agent-info panels later
    components/GodotCanvas.tsx
    types/replay.ts     # types for penn_replay.json
  public/
    godot/              # (git-ignored) Godot Web export output — built locally
    replay/penn_replay.json  # committed sample replay, fetched at runtime
  scripts/
    export-godot.sh
    gen-replay.sh
```

## Licensing — do not deploy publicly as-is

The sprite art is the **Cute Fantasy (Free)** pack (see the project
[`../README.md`](../README.md)): **free for non-commercial use, may be modified,
but not redistributed or resold.** A web build bakes that art into `index.pck`.
**Local use is fine**, but do **not** publicly deploy this build without a
licensing review (or swapping in freely-redistributable / CC0 art first).
