# Web viewer — Godot Penn replay in the browser

A small **React + Vite + TypeScript** shell that embeds the Godot Penn-campus
replay as a **WebAssembly** build, so you can watch the agents walk the real campus
in a browser — no native Godot install needed just to *view* it.

It's also the **foundation for a generative-agents-style companion app**: side
panels showing each agent's current action / location / emoji, a timeline scrubber,
and so on. Those panels read the *same* `penn_replay.json` the Godot canvas plays
(typed in [`src/types/replay.ts`](src/types/replay.ts)), so they never have to pull
state out of Godot.

> **Status:** local viewer only — not deployed yet. The Vercel path is configured
> ([Deploying to Vercel](#deploying-to-vercel-882)); read [Licensing](#licensing)
> before you put this on a public URL.

---

## Tech stack

| Piece | Version | Role |
| --- | --- | --- |
| **Godot** | 4.6.x (tested 4.6.3) | The actual renderer. Exported to WebAssembly; runs in the browser, pixel-identical to desktop. |
| **React** | 18.3 | The page shell / component model — the home for future agent-info panels. |
| **Vite** | 5.4 | Dev server (with the COOP/COEP headers Godot needs) + static build. |
| **TypeScript** | 5.x | Type-safe app code, incl. the replay-JSON schema and the JS↔Godot seam. |
| **Biome** | 2.x | One tool for format + lint (replaces Prettier + ESLint). `pnpm format` / `pnpm lint`. |
| **Vitest** | 3.x | Vite-native unit tests (`pnpm test`); shares `vite.config.ts`, no extra setup. |
| **lucide-react** | 1.x | Tree-shakeable line-icon set (nav icons); only the icons you import ship. |
| **esbuild** | 0.21 (via Vite) | Vite's bundler/transpiler (native binary; see [Troubleshooting](#troubleshooting)). |
| **pnpm** | 11.x | Package manager. Version pinned via `packageManager` in `package.json`. |
| **Node** | 18+ | Runtime for the tooling (tested on 25). |
| **uv** | repo default | Runs the Python sim behind `pnpm gen:replay`. |

---

## How it works

### Data flow

```
Python sim ──▶ godot/maps/penn_replay.json ──(copied)──▶ web/public/replay/penn_replay.json
(backend/penn/generate_penn_replay.py)                              │  Vite serves it at /replay/...
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
   [`../godot/export_presets.cfg`](../godot/export_presets.cfg). It writes a self-contained
   build to `public/godot/`: `index.wasm` (the engine, ~37 MB), `index.pck` (the
   packed game — scenes, scripts, imported textures, **and the `.tmj` maps**), and
   `index.js` (the JS loader that defines Godot's `Engine` class). The script
   temporarily pins the project's main scene to `main_menu.tscn` for the export
   only (the landing page — the same default desktop F5 opens), then restores
   `project.godot`. On web the menu hides its "Open a local file…" button and the
   bundled replay is fetched over HTTP rather than packed (see below).

2. **Replay fetched at runtime, not packed.** `../godot/scripts/viewer.gd` (in
   the Godot project) has a `web` branch: on web it `HTTPRequest`s the replay from
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
setting `variant/thread_support=false` in `../godot/export_presets.cfg`.

### The data contract (replay JSON)

Produced by `backend/penn/generate_penn_replay.py`, consumed by both the Godot
canvas and the companion's agent cards. The contract is pinned on the Python
side (`../backend/contract.py`, #305); [`src/types/replay.ts`](src/types/replay.ts)
is its field-for-field mirror, held in lock-step by
`../tests/test_replay_contract.py`. Abridged:

```jsonc
{
  "meta": {
    "tile_px": 16,            // pixels per tile
    "width": 237, "height": 271,
    "steps": 400,             // == frames.length
    "sec_per_step": 10,       // in-game seconds per step
    "personas": [{ "name": "Diego Torres", "emoji": "✏️" }, …]
  },
  "frames": [                 // one entry per step
    { "Diego Torres": { "x": 13, "y": 15, "act": "sketching @ …", "e": "✏️" }, … },
    …
  ]
}
```

Current files carry more than this sketch: `meta.schema_version`, richer
personas (blurb / home / schedule, #408), the seed social graph
(`meta.relationships`, #252), per-frame `reasoning` / `chat` / `memories`,
plus top-level `memory_streams` and the `events` run record — all optional
in the TS types, so older files still load. See `replay.ts` for the full shape.

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

You should see the landing menu load over a live campus backdrop; click **Play the
bundled replay** and Diego, Professor Tanaka and Sofia walk the campus with name +
activity labels — the same viewer as the desktop `viewer.tscn`.

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

### Live mode: follow a running backend

The **Agent cards** page can follow a *running* live backend instead of the
baked replay: point the page at the server with an `?api=` query param and the
whole agents view goes live — roster from the backend's `GET /live` meta,
current position/action/reasoning/conversation from the change feed's frame
records, the **Full memory history** column from `GET /agents/{name}/memory`
(refetched as the run advances), and an **LLM requests** log — the same
one-line-per-model-call stream the backend's terminal monitor prints (and the
Godot HUD shows), filtered to the selected agent via each record's `actor`
field. A pill in the navigator shows the connection state (`live · step N`,
`paused`, or `reconnecting`). Only the Godot **canvas** stays replay-driven —
the live scene is the desktop viewer's job.

```bash
uv run python godot-generative-agents/backend/penn/serve_penn.py            # terminal 1 (add --brain llm for real calls)
pnpm dev                                                           # terminal 2
# then open  http://localhost:5173/?api=http://127.0.0.1:8080#agents
```

Each LLM-log row is `time · role · tokens in→out · $cost`; hover for the full
detail (model, cache split, latency, turn, running total). Under the default
mock brain the calls are free ($0.0000 rows) — real numbers appear when the
server runs `--brain llm`. `VITE_SIM_API_URL` works as a `pnpm dev` default for
the same setting; with neither given, the page stays fully static and the
agents view plays the baked replay exactly as before.

The **LLM dashboard** page (`#llm`, issue #519) is the "sit back and monitor
the run" surface over the same stream — no URL editing required: with no
backend connected it shows a **connect form** (type the server URL, hit
Connect; the page updates `?api=` to match so a refresh sticks). One cell per
agent — client-side aggregates (calls, tokens in→out with the cache-read
share, cost, latency) over that agent's recent calls, a recency pulse so a
stalled agent is spottable at a glance, and the agent's own slice of the
request log — under a run strip with **Start / Stop / Reset buttons** (the
backend's resume/pause/reset controls, so you can drive the whole sim from
this page and watch the calls instead of the Godot map), the exact run totals,
the remaining budget, this run's **social opportunity** (co-settled pair-steps +
conversations, #795/#819), and the driving model. The budget and social counters
are seeded by one `GET /usage` read at connect and then ride the live feed's
`run_usage` (below), so they move with the run and clear on reset without a
second poll. Agents seen on the stream but missing from the roster get their own
cells, and calls with no `actor` land in an *Unattributed* catch-all, so the
dashboard works pointed at any live backend.

How it works: [`src/useLive.ts`](src/useLive.ts) reads the `GET /live`
handshake once (the world's replay-meta shape) plus one `GET /usage` for the
opening budget/social snapshot, then polls the backend's change feed
(`GET /events?since=<cursor>`) and keeps the latest `frame` and `status`
records plus every `engine` record whose payload is `kind: "llm_call"`. The
`frame` record (and the `reset` status record) also carries `run_usage` — the
run-scoped call/cost counters and the #795 social block — which the reducer
merges over the handshake snapshot, so those counters stay live off the one
feed rather than a separate `/usage` poll. The wire contract is documented in
[`backend/README.md`](../backend/README.md). The backend's CORS already
allows any localhost origin, so the dev server needs no proxy.

### Scripts

| Command | What it does |
| --- | --- |
| `pnpm dev` | Vite dev server (COOP/COEP headers on). |
| `pnpm build` | `tsc -b` typecheck + `vite build` → `dist/`. |
| `pnpm lint` | Biome check — formatting + lint (the CI gate; lint warnings don't fail, errors do). |
| `pnpm format` | Biome — rewrite files to the canonical format. |
| `pnpm test` | Vitest — run the unit suite once (use `pnpm exec vitest` to watch). |
| `pnpm preview` | Serve the production `dist/` build locally. |
| `pnpm export:godot` | Headless Godot Web export → `public/godot/`. |
| `pnpm gen:replay [-- <args>]` | Run the sim and copy the replay into `public/replay/`. Args pass through, e.g. `pnpm gen:replay --steps 600`. |
| `pnpm gen:docs` | Build the MkDocs site (`mkdocs build --strict`) into `public/docs/`, served at `/docs/`. |

---

## Deploying to Vercel (#882)

> **Read [Licensing](#licensing) first.** The web export bakes the *Cute Fantasy
> (Free)* sprite art into `index.pck`, and a public URL **redistributes** it. That
> audit is [#876](https://github.com/ccb/agent-sandbox/issues/876); it gates the
> production promote, not a preview.

**Deploys are built locally and uploaded prebuilt — never built from a clone.**
`public/godot/` (the ~52 MB WASM export) is git-ignored, so a Vercel *Git* build
would ship a site with a hole where the demo goes: Vite only copies `public/`, so
a missing export isn't a build error. Hence
[`vercel.json`](vercel.json)'s `git.deploymentEnabled: false` plus
[`scripts/vercel-build.sh`](scripts/vercel-build.sh), which fails the build when
the export is absent. Building locally is also what [#882](https://github.com/ccb/agent-sandbox/issues/882)
asks for: the artifact you QA'd is the one that gets promoted, not a rebuild.

### One-time setup

```bash
brew install vercel-cli          # or: pnpm add -g vercel
cd godot-generative-agents/web   # link from HERE — it sets Root Directory for the monorepo
vercel login
vercel link                      # writes .vercel/ (git-ignored: ids + pulled env)
```

### Every deploy

```bash
pnpm export:godot                # re-export if the Godot side changed
pnpm gen:replay                  # re-bake if the sim/replay changed
pnpm lint && pnpm test           # the same gates CI runs
vercel build                     # runs scripts/vercel-build.sh → dist/ → .vercel/output/
vercel deploy --prebuilt         # prints the preview URL
#   … run the #882 QA suite against that URL …
vercel promote <preview-url>     # same bytes, now production
```

Rollback: `vercel rollback` (or `vercel rollback <url>`) re-points production at
the previous deployment — instant, no rebuild. `vercel ls` lists deployments and
`vercel inspect <url>` prints the identity to record in #882.

### What the public site exposes

The landing page is the whole public surface (#879 retired the nav; every other view
is a `#hash` route, which never reaches the server). Two rules keep it that way:

- **No docs.** `pnpm gen:docs` output is a local dev convenience — the dev server
  serves it at `/docs/`, but `vercel-build.sh` deletes `dist/docs` so it is never
  deployed. Whether or not you ran `gen:docs` before deploying makes no difference.
- **Any other path lands on the landing page**, via
  `"rewrites": [{ "source": "/(.*)", "destination": "/" }]`. It's a *rewrite*, not a
  redirect, because Vercel gives ["precedence … to the filesystem prior to rewrites
  being applied"](https://vercel.com/docs/project-configuration/vercel-json#rewrites)
  — real files (`/godot/*`, `/replay/*`, `/assets/*`) still serve, and only paths that
  match nothing fall through. A catch-all `redirects` entry would do the opposite:
  redirects run *before* the filesystem, so it would bounce the engine and the replay
  to `/` too and the demo would never load. The URL bar keeps `/xyz` rather than
  snapping to `/`; if you'd rather it snapped, that needs a redirect with every asset
  prefix negated by hand — brittle, and one forgotten prefix silently breaks an asset.

The trade-off: a *missing* asset now answers 200 with the landing page's HTML instead
of 404, so a hollow deploy fails in the Godot loader rather than at the network tab.
That's what `vercel-build.sh`'s asset guard is for — the 404 isn't the safety net.

Two more launch details:

- **Shared-link metadata** lives in `index.html`: title (matching the `<h1>`), the
  favicon, and a description/OG card condensed from the page's own Abstract. There is
  no `og:image` yet — #881's video produces a poster frame, which is the right thing to
  point at; until then link previews render as a text card rather than a broken image.
- **`/assets/*` is cached `max-age=31536000, immutable`** — Vite content-hashes every
  file there, so a new build gets new URLs. Everything else keeps Vercel's
  `public, max-age=0, must-revalidate` default *on purpose*: `/godot/index.wasm`,
  `index.pck` and `/replay/penn_replay.json` keep the same names across deploys, so
  they must revalidate or a promote would leave visitors on a stale engine.

**Open decision — indexing.** Nothing sets `robots` today, so a promoted production URL
is indexable. If #876 hasn't cleared, add `<meta name="robots" content="noindex" />` to
`index.html` before promoting rather than after.

### Verify on the deployed origin

| Check | How | Why it matters |
| --- | --- | --- |
| Cross-origin isolation | `curl -sI <url> \| grep -i cross-origin` — expect both COOP + COEP | Godot's *threaded* WASM needs `SharedArrayBuffer`. `vite.config.ts` sets these for `dev`/`preview` only; on Vercel they come from `vercel.json`. Missing ⇒ the figure says "This browser can't run the replay demo" and names them (#957) — which is also the only visitor-facing sign of a header regression, since nothing in CI boots the engine. |
| `.pck` compression | `curl -sI -H 'accept-encoding: br' <url>/godot/index.pck \| grep -i content-encoding` | `index.pck` is 16 MB raw and **4 %** gzipped, but Vercel compresses an [MIME allowlist](https://vercel.com/docs/how-vercel-cdn-works/compression) that `.pck` isn't on — so `vercel.json` labels that one path `application/wasm`, which is. Godot's loader reads the `.pck` as an ArrayBuffer and ignores the type. No `content-encoding` ⇒ the override didn't take; drop it and eat the 16 MB. |
| Payload | DevTools → Network, hard reload | ~10 MB compressed per cold visit (the 35 MB engine gzips to ~9 MB) against 57 MB of `dist/`. Hobby includes 100 GB/month of transfer. |
| Stray URLs | `curl -sI <url>/docs/ <url>/nope` → 200, and the browser shows the landing page | Proves both the `dist/docs` strip and the catch-all rewrite took. A 404 means the rewrite didn't apply; MkDocs HTML at `/docs/` means the strip didn't. |

### Limits worth knowing

- **CLI upload cap: 100 MB on Hobby, 1 GB on Pro.** `dist/` is ~57 MB today
  (`du -sh dist` after `vercel build`, i.e. with `dist/docs` already stripped).
  Check before the release build.
- **100 deployments/day** on Hobby.
- Preview URLs are protected by default — share QA links via the deployment's
  *Protection Bypass*, not by disabling protection.
- `COEP: require-corp` blocks **every** cross-origin `<iframe>`, `<script>` and
  `<img>`. Today the page loads nothing cross-origin (external URLs are all plain
  links, which are unaffected), but the [#881](https://github.com/ccb/agent-sandbox/issues/881)
  video must be self-hosted — a YouTube/Vimeo embed will be blocked — or the
  headers have to be scoped to the demo first.

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
    export-godot.sh     # Godot → WASM (temporarily boots main_menu.tscn)
    gen-replay.sh       # run the sim → copy replay into public/
```

What's **committed** vs **generated**: `src/`, configs, `scripts/`, the lockfile, and
one sample `public/replay/penn_replay.json` are committed. `node_modules/`, `dist/`,
and `public/godot/` are git-ignored — regenerate them with `pnpm install` /
`pnpm build` / `pnpm export:godot`.

### Adding more companion panels

The first panels exist (the **Agent cards** view — `src/components/AgentPanel.tsx`
— plus the prompt views); new ones are a pure-data feature and don't need Godot:

1. Read the replay via [`src/useReplay.ts`](src/useReplay.ts) (typed as `Replay`
   from [`src/types/replay.ts`](src/types/replay.ts)); for live-backend data,
   follow the [`src/useLive.ts`](src/useLive.ts) pattern against the
   endpoints in [`../backend/README.md`](../backend/README.md).
2. Add panel components under `src/components/` and give them a view in
   [`App.tsx`](src/App.tsx)'s hash-routed menu.
3. To keep panels in step with the canvas, use `useReplayStep` — Godot's
   `viewer.gd` already posts the current step out through `JavaScriptBridge`
   (`window.__pennReplayStep`), with a fallback clock when the bridge is absent.

### Conventions / gotchas

- **TypeScript is strict** (`noUnusedLocals`/`noUnusedParameters` on). `pnpm build`
  must typecheck clean.
- **Run `pnpm lint` before pushing** (CI runs it). It's Biome — format check + lint
  in one. `pnpm format` fixes formatting. A handful of pre-existing lint rules are set
  to `warn` in `biome.json` (mostly a11y in the older modals); warnings don't fail CI,
  but new code should avoid adding to them.
- **Styling: tokens + CSS Modules.** Shared colours/radii live as CSS custom properties
  in `src/theme.css` (imported once from `index.css`) — reference `var(--color-…)` /
  `var(--radius-…)` instead of hard-coding a hex or a `Npx` radius. A future dark theme
  is just a `@media (prefers-color-scheme: dark)` block re-pointing those names. **New
  components should use a co-located CSS Module** (`Foo.module.css`, imported as
  `import styles from "./Foo.module.css"`, used as `styles.thing`) so class names are
  scoped and can't collide — see `components/GodotCanvas.tsx` for the pattern. The older
  global stylesheets (`App.css`, `AgentPanel.css`, …) migrate opportunistically.
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
| `Invalid URL scheme` / replay won't load on web | Godot's `HTTPRequest` needs an absolute URL; `viewer.gd` resolves the relative path via `JavaScriptBridge`. Make sure the replay is reachable at `/replay/penn_replay.json` (run `pnpm gen:replay`). |
| The demo says **"This browser can't run the replay demo"** | The engine's preflight found something missing — the names are in the message, the full strings in the console (#957). Almost always cross-origin isolation: use `pnpm dev`/`pnpm preview` (they set COOP/COEP). If serving another way, send those headers, or export single-threaded (`variant/thread_support=false`). |
| Port 5173 already in use | Another Vite is running. Stop it, or Vite will pick the next free port (check its printed URL). |

---

## Licensing

The sprite art is the **Cute Fantasy (Free)** pack (see the project
[`../README.md`](../README.md)): **free for non-commercial use, may be modified, but
not redistributed or resold.** A web build bakes that art into `index.pck`. **Local
use is fine**, but do **not** publicly deploy this build without a licensing review
(or swapping in freely-redistributable / CC0 art first).
