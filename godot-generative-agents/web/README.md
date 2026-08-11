# Penn Generative Agents web companion

This Vite/React application is the public project writeup and browser replay
viewer. It embeds reviewed static artifacts; it is not the authoritative
simulation engine.

## Develop

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Run the release gates:

```bash
pnpm lint
pnpm test
pnpm build
```

## Generated artifacts

Run these from this directory:

```bash
pnpm gen:replay     # Penn browser replay from retained source
pnpm gen:promptviz  # cognition graph from backend/promptviz_chains/cognition.yaml
pnpm gen:docs       # local MkDocs build copied into public/docs
pnpm export:godot   # web export of the Godot project
```

Review generated diffs before committing. `public/replay/penn_replay.json` is the
canonical showcased run and is intentionally tracked. Exported Godot and MkDocs
directories are build outputs and remain ignored.

The build uses the pinned `pnpm-lock.yaml` and Vite configuration. Keep replay
codec changes synchronized with Python's `backend/replay_codec.py` and cover both
implementations with tests.

## Deploying to Vercel

> **Read [Publication safety](#publication-safety) first.** The web export bakes the
> licensed sprite/UI/interior art into `index.pck`, and a public URL serves that
> archive to anyone. See the root [`ASSETS.md`](../../ASSETS.md) for each pack's terms.

**The deploy source is this branch, `prod`**, from this directory — it is what
`web/`-labelled work lands on, and `src/components/home/links.ts` points every
repository link at `prod` rather than the default branch.

**Deploys are built locally and uploaded prebuilt — never built from a clone.**
`public/godot/` (the ~48 MB WASM export) is git-ignored, so a Vercel *Git* build
would ship a site with a hole where the demo goes: Vite only copies `public/`, so a
missing export is not a build error. Hence [`vercel.json`](vercel.json)'s
`git.deploymentEnabled: false` plus [`scripts/vercel-build.sh`](scripts/vercel-build.sh),
which fails the build when the export is absent. It also means the artifact you QA is
the one that gets promoted, not a rebuild of it.

One consequence worth planning around: the art packs are **not in this repository**
(they were retired under #876 and are git-ignored drop-ins). Whoever runs
`export:godot` needs them on disk per `ASSETS.md`, plus Godot 4.6 with the Web export
templates. A clean clone cannot produce a deployable build.

### One-time setup

```bash
brew install vercel-cli          # or: pnpm add -g vercel
cd godot-generative-agents/web   # link from HERE — it sets Root Directory for the monorepo
vercel login
vercel link                      # writes .vercel/ (git-ignored: ids + pulled env)
```

Then enable **Web Analytics** in the Vercel dashboard for the project. The
`<Analytics />` in `src/main.tsx` is first-party and production-gated, but the
dashboard toggle is what serves the script — without it the beacon 404s silently, and
nothing in this repository can tell you (#961).

### Every deploy

```bash
pnpm export:godot                # re-export if the Godot side changed (needs ASSETS.md art)
pnpm gen:replay                  # re-bake only if the showcased run changed
pnpm lint && pnpm test           # the same gates CI runs
vercel build                     # runs scripts/vercel-build.sh → dist/ → .vercel/output/
du -sh dist                      # ~56 MB today; Hobby caps CLI uploads at 100 MB
vercel deploy --prebuilt         # prints the preview URL
#   … run the QA suite in #882 against that URL …
vercel promote <preview-url>     # same bytes, now production
```

Rollback: `vercel rollback` (or `vercel rollback <url>`) re-points production at the
previous deployment — instant, no rebuild, and it needs nothing from this repository
or the art. `vercel ls` lists deployments and `vercel inspect <url>` prints the
identity to record on #882.

### What the public site exposes

The landing page is the whole public surface (#879 retired the nav; every other view
is a `#hash` route, which never reaches the server). Two rules keep it that way:

- **No docs.** `pnpm gen:docs` output is a local dev convenience — the dev server
  serves it at `/docs/`, but `vercel-build.sh` deletes `dist/docs` so it is never
  deployed. Whether you ran `gen:docs` before deploying makes no difference.
- **Any other path lands on the landing page**, via
  `"rewrites": [{ "source": "/(.*)", "destination": "/" }]`. It is a *rewrite*, not a
  redirect, because Vercel gives ["precedence … to the filesystem prior to rewrites
  being applied"](https://vercel.com/docs/project-configuration/vercel-json#rewrites)
  — real files (`/godot/*`, `/replay/*`, `/assets/*`, `/_vercel/*`) still serve, and
  only paths matching nothing fall through. A catch-all `redirects` entry would do the
  opposite: redirects run *before* the filesystem, so it would bounce the engine, the
  replay and the analytics beacon to `/` and the demo would never load.

The trade-off: a *missing* asset now answers 200 with the landing page's HTML instead
of 404, so a hollow deploy fails in the Godot loader rather than in the network tab.
That is what `vercel-build.sh`'s asset guard is for — the 404 is not the safety net.

**Indexing is deliberate.** Nothing sets a `robots` meta, so a promoted URL is
indexable; that is the decision, not an oversight (`index.html` records it). Reversing
it is one `<meta name="robots" content="noindex" />` — but de-indexing an indexed page
is far slower than never publishing it, so revisit the call *before* a promote, not
after.

**`/assets/*` is cached `max-age=31536000, immutable`** — Vite content-hashes every
file there, so a new build gets new URLs. Everything else keeps Vercel's
`public, max-age=0, must-revalidate` default *on purpose*: `/godot/index.wasm`,
`index.pck` and `/replay/penn_replay.json` keep the same names across deploys, so they
must revalidate or a promote would leave visitors on a stale engine.

### Verify on the deployed origin

| Check | How | Why it matters |
| --- | --- | --- |
| Cross-origin isolation | `curl -sI <url> \| grep -i cross-origin` — expect both COOP + COEP | Godot's *threaded* WASM needs `SharedArrayBuffer`. `vite.config.ts` sets these for `dev`/`preview` only; on Vercel they come from `vercel.json`. Missing ⇒ the figure says "This browser can't run the replay demo" and names them (#957) — which is also the only visitor-facing sign of a header regression, since nothing in CI boots the engine. |
| `.pck` compression | `curl -sI -H 'accept-encoding: br' <url>/godot/index.pck \| grep -i content-encoding` | `index.pck` is 13 MB raw and mostly `.tmj` JSON, so it compresses ~25×, but Vercel compresses an [MIME allowlist](https://vercel.com/docs/how-vercel-cdn-works/compression) that `.pck` is not on — hence the `application/wasm` label on that one path. Godot reads the `.pck` as an ArrayBuffer and ignores the type. No `content-encoding` ⇒ the override did not take; drop it and eat the 13 MB. |
| The demo runs | Open the page and start the replay | The one check that covers a stale export, a failed replay fetch and the headers at once. |
| Stray URLs | `curl -sI <url>/docs/ <url>/nope` → 200, and the browser shows the landing page | Proves both the `dist/docs` strip and the catch-all rewrite took. A 404 means the rewrite did not apply; MkDocs HTML at `/docs/` means the strip did not. |
| Analytics beacon | Network tab: a 200 from `/_vercel/insights/*` | Confirms the dashboard toggle *and* that the catch-all rewrite is not shadowing `/_vercel/*`. |

### Limits worth knowing

- **CLI upload cap: 100 MB on Hobby, 1 GB on Pro.** `dist/` is ~56 MB (`du -sh dist`
  after `vercel build`, i.e. with `dist/docs` already stripped). Check before the
  release build.
- **100 deployments/day** on Hobby. Web Analytics on Hobby: 50,000 events/month, a
  1-month reporting window, shared across the account.
- Preview URLs are protected by default — share QA links via the deployment's
  *Protection Bypass*, not by disabling protection.
- `COEP: require-corp` blocks **every** cross-origin `<iframe>`, `<script>` and
  `<img>`. Today the page loads nothing cross-origin (external URLs are all plain
  links, which are unaffected), and anything added later must be same-origin, send
  `CORP`, or wait for the headers to be scoped to the demo alone. This is why
  analytics has to be first-party (#961) and one reason the demo video was dropped
  rather than embedded (#881).

## Publication safety

Do not place keys, raw model requests/responses, cassettes, databases, private run
directories, or personal data under `public/`. Verify the license and attribution
of every visual asset before deployment — the art packs listed in the root
[`ASSETS.md`](../../ASSETS.md) permit use and modification but **not
redistribution**, and a web export bakes them into `index.pck`, so a public deploy
of this build is a licensing decision, not a routine one. The clean public-history
process is managed separately from this source-tree snapshot.
