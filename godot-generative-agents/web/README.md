# Web viewer — Godot Penn replay in the browser

A small **React + Vite + TypeScript** shell that embeds the Godot Penn-campus
replay as a **WebAssembly** build, so you can watch the agents walk the real campus
in a browser — no native Godot install needed just to *view* it.

It's also the **foundation for a generative-agents-style companion app**: side
panels showing each agent's current action / location / emoji, a timeline scrubber,
and so on. Those panels read the *same* `penn_replay.json` the Godot canvas plays
(typed in [`src/types/replay.ts`](src/types/replay.ts)), so they never have to pull
state out of Godot.

> **Status:** local viewer only — not deployed. See [Licensing](#licensing) before
> you ever put this on a public URL.

---

## Tech stack

| Piece | Version | Role |
| --- | --- | --- |
| **Godot** | 4.6.x (tested 4.6.3) | The actual renderer. Exported to WebAssembly; runs in the browser, pixel-identical to desktop. |
| **React** | 18.3 | The page shell / component model — the home for future agent-info panels. |
| **Vite** | 5.4 | Dev server (with the COOP/COEP headers Godot needs) + static build. |
| **TypeScript** | 5.x | Type-safe app code, incl. the replay-JSON schema and the JS↔Godot seam. |
| **esbuild** | 0.21 (via Vite) | Vite's bundler/transpiler (native binary; see [Troubleshooting](#troubleshooting)). |
| **pnpm** | 11.x | Package manager. Version pinned via `packageManager` in `package.json`. |
| **Node** | 18+ | Runtime for the tooling (tested on 25). |
| **uv** | repo default | Runs the Python sim behind `pnpm gen:replay`. |

---

## How it works

### Data flow

```
Python sim ──▶ maps/penn_replay.json ──(copied)──▶ web/public/replay/penn_replay.json
(sim/generate_penn_replay.py)                              │  Vite serves it at /replay/...
                                                           ▼
Godot project ──(headless export)──▶ web/public/godot/index.{js,wasm,pck,…}
(scripts/export-godot.sh)                                  │  Vite serves it at /godot/...
                                                           ▼
                       React app (Vite dev server, COOP/COEP headers)
                       ├─ <GodotCanvas/> loads /godot/index.js → Engine → <canvas>
                       │     Godot packs the .tmj map + tilesets (in the .pck) but
                       │     FETCHES /replay/penn_replay.json over HTTP at runtime
                       └─ (future) agent-info panels reading the same replay JSON
```

### The three methods that make this work

1. **Godot → WebAssembly export.** `scripts/export-godot.sh` runs Godot headless
   (`--export-release "Web"`) using the `Web` preset in
   [`../export_presets.cfg`](../export_presets.cfg). It writes a self-contained
   build to `public/godot/`: `index.wasm` (the engine, ~37 MB), `index.pck` (the
   packed game — scenes, scripts, imported textures, **and the `.tmj` maps**), and
   `index.js` (the JS loader that defines Godot's `Engine` class). The script
   temporarily points the project's main scene at `penn_replay.tscn` for the export
   only, then restores `project.godot` (so desktop F5 still opens `main.tscn`).

2. **Replay fetched at runtime, not packed.** `scripts/penn_replay.gd` (in the
   Godot project) has a `web` branch: on web it `HTTPRequest`s the replay from
   `/replay/penn_replay.json` instead of reading it from the `.pck`. So a new sim is
   a one-file swap — no re-export. (The desktop `FileAccess` path is unchanged.)

3. **The embed.** [`src/components/GodotCanvas.tsx`](src/components/GodotCanvas.tsx)
   injects `/godot/index.js`, then `new Engine({...}).startGame()` onto a `<canvas>`
   that lives inside a React component (not an `<iframe>`). That keeps future panels
   in the same DOM/CSS and leaves room for two-way messaging via Godot's
   `JavaScriptBridge`.

Cross-origin isolation: Godot's *threaded* WASM only runs on a page that sends
`Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy:
require-corp`. [`vite.config.ts`](vite.config.ts) sets both (on `dev` and
`preview`). If they ever cause trouble locally, export single-threaded instead by
setting `variant/thread_support=false` in `../export_presets.cfg`.

### The data contract (replay JSON)

Produced by `sim/generate_penn_replay.py`, consumed by both the Godot canvas and
(soon) the companion panels. Typed in [`src/types/replay.ts`](src/types/replay.ts):

```jsonc
{
  "meta": {
    "tile_px": 16,            // pixels per tile
    "width": 237, "height": 271,
    "steps": 400,             // == frames.length
    "sec_per_step": 10,       // in-game seconds per step
    "personas": [{ "name": "Maya Chen", "emoji": "📚" }, …]
  },
  "frames": [                 // one entry per step
    { "Maya Chen": { "x": 13, "y": 15, "act": "studying @ …", "e": "📚" }, … },
    …
  ]
}
```

---

## Prerequisites

- **pnpm** (and **Node** 18+). Install pnpm with `brew install pnpm` or
  `corepack enable`. The exact version is pinned via `packageManager` in
  `package.json`.
- **Godot 4.6.x** with the matching **Web export templates** installed. The first
  `pnpm export:godot` fails with a clear message until you do this:
  *Godot editor → Editor → Manage Export Templates → Download and Install* (pick the
  version that matches your editor, e.g. `4.6.3.stable`).
- **uv** (already used by this repo) — `pnpm gen:replay` runs the Python sim through it.

If your Godot isn't at the macOS default
(`/Applications/Godot.app/Contents/MacOS/Godot`), set `GODOT_BIN`, e.g.
`GODOT_BIN=/path/to/Godot pnpm export:godot`.

## Run it

```bash
cd godot-generative-agents/web
pnpm install
pnpm gen:replay     # writes public/replay/penn_replay.json (a copy is committed too)
pnpm export:godot   # writes public/godot/ (the WASM build)
pnpm gen:docs       # optional: builds the MkDocs site into public/docs/ (the "Docs" link)
pnpm dev            # open the printed http://localhost:… URL
```

You should see the campus load and Maya, Professor Ellis and Diego walk it with
name + activity labels — the same scene as the desktop `penn_replay.tscn`.

The header's **Docs** link opens the project's MkDocs site at `/docs/` on this
same origin. It's served as plain static files out of `public/docs/`, so run
`pnpm gen:docs` once to populate it (until then the link 404s). The docs are
built `highlightjs: false` so they carry no cross-origin scripts and load fine
under this app's COOP/COEP policy.

### The dev loop — why you rarely rebuild

Two kinds of change, and **neither rebuilds the React app** (the Vite dev server can
stay running through both — just refresh the browser):

| What changed | What you run | Why no React rebuild |
| --- | --- | --- |
| **New sim / replay** | `pnpm gen:replay` | The viewer **fetches** the replay JSON at runtime (it's not in the build). Swap the file, refresh. |
| **Godot scripts / scenes / art** | `pnpm export:godot` | Vite serves `public/` statically, so the re-exported WASM is picked up on the next refresh. |
| **Docs (mkdocs/)** | `pnpm gen:docs` | Same deal — `public/docs/` is served statically, so the rebuilt site shows up at `/docs/` on the next refresh. |

### Live mode: the LLM-request stream (#398)

The **Agent cards** page can follow a *running* live backend on top of the baked
replay it plays: point the page at the server with an `?api=` query param and the
selected agent's card grows an **LLM requests** log — the same
one-line-per-model-call stream the backend's terminal monitor prints (and the
Godot HUD shows), filtered to that agent via each record's `actor` field.

```bash
uv run python godot-generative-agents/sim/serve_penn.py            # terminal 1 (add --brain llm for real calls)
pnpm dev                                                           # terminal 2
# then open  http://localhost:5173/?api=http://127.0.0.1:8080#agents
```

Each row is `time · role · tokens in→out · $cost`; hover for the full detail
(model, cache split, latency, turn, running total). Under the default mock brain
the calls are free ($0.0000 rows) — real numbers appear when the server runs
`--brain llm`. `VITE_SIM_API_URL` works as a `pnpm dev` default for the same
setting; with neither given, the page stays fully static.

How it works: [`src/useLlmCalls.ts`](src/useLlmCalls.ts) polls the backend's
change feed (`GET /events?since=<cursor>`) and keeps the `engine` records whose
payload is `kind: "llm_call"` — the wire contract is documented in
[`backend/README.md`](../../backend/README.md). The backend's CORS already
allows any localhost origin, so the dev server needs no proxy.

### Scripts

| Command | What it does |
| --- | --- |
| `pnpm dev` | Vite dev server (COOP/COEP headers on). |
| `pnpm build` | `tsc -b` typecheck + `vite build` → `dist/`. |
| `pnpm preview` | Serve the production `dist/` build locally. |
| `pnpm export:godot` | Headless Godot Web export → `public/godot/`. |
| `pnpm gen:replay [-- <args>]` | Run the sim and copy the replay into `public/replay/`. Args pass through, e.g. `pnpm gen:replay --steps 600`. |
| `pnpm gen:docs` | Build the MkDocs site (`mkdocs build --strict`) into `public/docs/`, served at `/docs/`. |

---

## Contributing

### Project layout

```
web/
  package.json          # scripts + pinned pnpm (packageManager)
  pnpm-workspace.yaml   # pnpm settings (allowBuilds for esbuild — see Troubleshooting)
  vite.config.ts        # COOP/COEP headers for cross-origin isolation
  index.html
  src/
    main.tsx            # React entry (no StrictMode — see note below)
    App.tsx             # layout: Godot canvas now; room for agent-info panels
    components/
      GodotCanvas.tsx   # loads + starts the Godot WASM engine onto a <canvas>
    types/
      replay.ts         # TypeScript types for penn_replay.json (the data contract)
  public/
    godot/              # (git-ignored) Godot Web export output — built locally
    replay/penn_replay.json  # committed sample replay, fetched at runtime
  scripts/
    export-godot.sh     # Godot → WASM (temporarily boots penn_replay.tscn)
    gen-replay.sh       # run the sim → copy replay into public/
```

What's **committed** vs **generated**: `src/`, configs, `scripts/`, the lockfile, and
one sample `public/replay/penn_replay.json` are committed. `node_modules/`, `dist/`,
and `public/godot/` are git-ignored — regenerate them with `pnpm install` /
`pnpm build` / `pnpm export:godot`.

### Adding the companion app (the intended next step)

The panels are a pure-data feature — you don't need to touch Godot:

1. `fetch('/replay/penn_replay.json')` and parse it as the `Replay` type from
   [`src/types/replay.ts`](src/types/replay.ts).
2. Add panel components under `src/components/` and lay them out alongside
   `<GodotCanvas/>` in [`App.tsx`](src/App.tsx) (the `.app-stage` is a positioned
   container ready for a sidebar).
3. To keep panels in step with the canvas, track the current step the same way
   `penn_replay.gd` does — `floor(elapsed_seconds / step_seconds)` — or, for tight
   coupling (e.g. click a panel → highlight that agent in Godot), use Godot's
   `JavaScriptBridge` to post the current step out and accept calls in. `GodotCanvas`
   already embeds the engine in-DOM specifically to make that bridge possible.

### Conventions / gotchas

- **TypeScript is strict** (`noUnusedLocals`/`noUnusedParameters` on). `pnpm build`
  must typecheck clean.
- **No `<StrictMode>`** in `main.tsx`: it double-invokes effects in dev, which would
  boot the Godot engine twice onto one canvas. Wrap your own (non-Godot) components
  in StrictMode if you want the extra checks.
- **Don't commit build output** (`public/godot/`, `dist/`) or `node_modules/` — they're
  git-ignored on purpose.
- Editing the Godot side (scenes/scripts/art) means re-running `pnpm export:godot`;
  editing only the replay data means `pnpm gen:replay`.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `export:godot` fails about templates | Web export templates not installed — *Godot → Editor → Manage Export Templates → Download and Install* (matching version). |
| `ERR_PNPM_IGNORED_BUILDS: esbuild` on `pnpm install`/`build` | pnpm blocks dependency build scripts by default. We allow esbuild in `pnpm-workspace.yaml` (`allowBuilds: { esbuild: true }`). On pnpm 11 this setting lives in `pnpm-workspace.yaml`, **not** the `package.json` `pnpm` field. Run `pnpm install` after editing it. |
| Canvas loads but the map is blank/grey | The `.tmj` maps weren't packed. They're plain JSON (not Godot resources), so the `Web` preset must keep `include_filter="*.tmj"`. (Note: `export_presets.cfg` uses `;` for comments, **not `#`** — a `#` silently drops the next setting.) |
| `Invalid URL scheme` / replay won't load on web | Godot's `HTTPRequest` needs an absolute URL; `penn_replay.gd` resolves the relative path via `JavaScriptBridge`. Make sure the replay is reachable at `/replay/penn_replay.json` (run `pnpm gen:replay`). |
| Blank page / `SharedArrayBuffer is not defined` | The page isn't cross-origin isolated. Use `pnpm dev`/`pnpm preview` (they set COOP/COEP). If serving another way, send those headers, or export single-threaded (`variant/thread_support=false`). |
| Port 5173 already in use | Another Vite is running. Stop it, or Vite will pick the next free port (check its printed URL). |

---

## Licensing

The sprite art is the **Cute Fantasy (Free)** pack (see the project
[`../README.md`](../README.md)): **free for non-commercial use, may be modified, but
not redistributed or resold.** A web build bakes that art into `index.pck`. **Local
use is fine**, but do **not** publicly deploy this build without a licensing review
(or swapping in freely-redistributable / CC0 art first).
