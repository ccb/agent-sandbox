# TOMB OF NASSAK AN-RAH — the iPhone app

**Status:** design spec, not yet implemented.

Ship *Tomb of Nassak An-Rah* as an iPhone app with old-school terminal vibes: a
blue-phosphor CRT (the classic green-phosphor look, swatched to Vaarn's blue)
playing the exact game that lives in this repo, offline, with
a modern mercy or two at the keyboard. The engine is not ported, wrapped in a
server, or rewritten — the **unmodified Python engine runs on the phone** (in
WASM), so the app inherits every fix and feature the repo lands, forever, by
rebuilding a wheel.

Decisions locked (CCB interview, 2026-07-08):

| Question       | Decision                                                     |
| -------------- | ------------------------------------------------------------ |
| Engine runtime | **Pyodide (CPython/WASM) inside a WKWebView**                 |
| Scope          | **Tomb-only, done well** (player-shaped later, not now)       |
| Input          | **Typing + context-aware accessory bar** (verbs + live nouns) |
| Aesthetic      | **Blue phosphor terminal** — the classic phosphor CRT look with green swapped for blue: the Vaarn vibe (the Blue Ruins on a blue screen) |
| Saves          | **Manual SAVE/RESTORE slots** + background autosave slot      |
| LLM            | **None in v1** — zero network calls                           |
| Distribution   | **TestFlight + public web URL** first; App Store later        |
| Dressing       | CRT visuals, typewriter reveal, sound, haptics — **all, each toggleable in Settings** |

---

## 1. Architecture

```
┌────────────────────────────────────────────┐
│ SwiftUI shell (thin)                       │
│  - WKWebView (the whole UI)                │
│  - WKURLSchemeHandler serves the bundle    │
│  - JS message handlers: haptics, share     │
│ ┌────────────────────────────────────────┐ │
│ │ terminal.html + terminal.js + CSS      │ │
│ │  phosphor CRT · typewriter · WebAudio  │ │
│ │  accessory bar · settings · save UI    │ │
│ │        ↕ postMessage bridge            │ │
│ │ Pyodide (CPython 3.12 in WASM)         │ │
│ │  text_adventure_games-*.whl (pure py)  │ │
│ │  app_api.py  (the ONLY new Python)     │ │
│ └────────────────────────────────────────┘ │
└────────────────────────────────────────────┘
```

Why this shape won: the engine ships **unmodified** (a pure-Python wheel loaded
by Pyodide); the terminal aesthetic is CSS, where CRT effects are a solved,
gorgeous problem; the identical bundle deploys to **a public URL** so students
and anyone else can play in a browser with zero install; and the Swift layer is
small enough that the iOS build is packaging, not development. Startup pays
~2–3s of interpreter boot behind the phosphor warm-up animation (a CRT takes a
moment to glow — the loading screen is diegetic).

The same architecture rejected: embedded CPython + native SwiftUI (more build
plumbing, aesthetic rebuilt natively, no free web version); thin client + server
(kills offline, the soul of the genre); Swift port (parity with the evolving
engine dies on day one).

### 1.1 The JS ⇄ Python API (`app_api.py`)

One small Python module, the only new Python in the project. Everything crosses
the bridge as JSON:

- `boot(seed: int | None) -> Scene` — builds the Tomb (seeding `tomb._RNG`),
  returns the opening narration as events.
- `command(text: str) -> TurnResult` — one turn:
  `{events: [{channel, text}, ...], turn, score, room, game_over, won}`.
  Channels are the engine's existing ones (`narration`, `damage`, `blocked`,
  …) — the UI colors ♥ red against the blue and ✗ dim, no parsing of prose
  ever.
- `suggestions() -> {verbs: [...], nouns: [...]}` — for the accessory bar:
  verbs from the registered actions, nouns from `perceive()` (visible items,
  characters, exits) **plus inventory**. The bar shows what the player could
  mean *here*, in the dark it thins out accordingly — perception-honest UI.
- `snapshot() -> SaveBlob` / `restore(blob) -> Scene` — see §2.

### 1.2 The Swift shell (near-trivial by design)

- `WKWebView` + `WKURLSchemeHandler` serving the bundled `dist/` (Pyodide,
  wheel, HTML/JS/CSS) from the app bundle — no local HTTP server, no network.
- Script message handlers: `haptic(kind)` → `UIImpactFeedbackGenerator`
  (damage = medium, death = heavy), `share(text)` → share sheet (transcripts).
- Keyboard: the input line is an HTML field; the accessory bar is **our own
  HTML strip pinned above the keyboard via the `visualViewport` API** — not a
  native `inputAccessoryView` (fighting WKWebView for that is a known tar pit).
- Settings, save slots, everything else: HTML. The Swift file count should be
  ~3.

## 2. Saves: slots in the UI, journal replay underneath

The save **format** is not a pickle of the world — it's the *expedition log*:

```json
{ "v": 1, "engine": "0.9.x", "seed": 7041,
  "commands": ["go north", "take glowstone", "..."],
  "meta": {"room": "Burial Sphere", "turn": 87, "score": 12,
           "saved_at": "2026-07-08T14:12:00Z"} }
```

Restore = reseed, rebuild, replay the commands with rendering suppressed
(hundreds of turns in milliseconds — the engine is deterministic once
`tomb._RNG` is seeded, which is already how the test suite works). Why this
beats serializing object state: it's a few KB, human-readable, robust to
engine refactors (state classes can change; the command grammar barely does),
and **transcripts fall out for free** — `SCRIPT` prints the full playthrough,
`share` exports it.

- **Slots:** `SAVE` / `RESTORE` as in-game commands (Infocom style) listing
  positions 1–3, plus a fourth **autosave** slot written every turn — iOS can
  kill the process whenever it likes; backgrounding must never lose a turn.
  Slot storage: `localStorage` on web, with the Swift side mirroring to app
  storage (and later, iCloud KV — v2).
- **Death:** the death screen offers `RESTORE` (the Tomb kills a lot; the
  playtests prove it) — but restoring is a choice, not an auto-rewind.
- **Version guard:** a save records the engine version. On mismatch, attempt
  the replay anyway and verify `meta.room/turn/score` — if drift is detected,
  say so honestly ("this expedition was logged by an older tomb") and offer
  the transcript instead of a corrupt resume.

**Engine work this needs (small, general, PR-able now):**
1. `SAVE`/`RESTORE`/`SCRIPT` as engine actions (`FREE_ACTION = True` — reading
   the ledger costs no turn, saving shouldn't either) with a pluggable storage
   seam the app and the CLI both implement.
2. A **replay mode** on `Game`: run a command list with rendering suppressed
   (`CaptureRenderer` already exists; this is a loop and a flag).
3. A **determinism audit**: every random draw in the Tomb must flow through
   `tomb._RNG` (they do today — keep it that way with a test that replays the
   `--win` route twice and diffs the transcripts).
4. `build_game(seed=None)` so the app can seed without reaching into module
   globals.

## 3. The terminal (HTML/CSS/JS)

**Phosphor:** blue (`#4db8ff`-ish, phthalo-adjacent — the Blue Ruins on a
blue screen) on near-black, monospace (JetBrains Mono or
IBM Plex Mono — both open), bloom via layered `text-shadow`, scanlines as a
repeating-gradient overlay, subtle flicker (`opacity` keyframes, ±1%), gentle
barrel curvature + vignette on the container. Bright channel = ♥ damage
(rendered red-orange, the one color exception — a wound should *interrupt*
the blue; the Horror's fungus is orange for the same reason),
dim channel = ✗ blocked. All pure CSS; no images, no WebGL required.

**Typewriter reveal:** narration types at ~baud-rate speed with per-character
variance; tap anywhere to complete instantly; a Settings speed (slow/fast/off).
Replay-restores always render instantly.

**Accessory bar:** two rows above the keyboard — verbs (a curated dozen:
N/S/E/W/UP/DOWN, LOOK, TAKE, EXAMINE, ATTACK, BURN, I) and the **live nouns**
from `suggestions()`. Tapping appends a word; the player still sees and owns
the command line. The bar is a mercy, not a menu — pure typing must remain
fully sufficient, and Settings can hide the bar entirely.

**Sound (WebAudio, all synthesized — no assets, no licenses):** low phosphor
hum, mechanical keyclick per keystroke, a flat beep on ✗, something low and wet
on ♥, a rising boot chirp. **Haptics** via the Swift bridge (no-op on web).

**Settings screen:** every dressing individually toggleable — CRT effects,
typewriter, sound, haptics, accessory bar — plus text size. Honest defaults:
all on. (Also the accessibility story: effects off + system text size = a
plain, readable terminal; VoiceOver reads the transcript div.)

## 4. Packaging & deployment

- **Wheel:** the engine is pure Python. Runtime imports needed by the game
  loop: `rich` is already optional (plain fallback confirmed), YAML is
  lazy-imported, `jinja2/prompty/flask/jupyter/graphviz` are LLM/tooling-side.
  Action item: an import audit under Pyodide (`boot + play the --win route in
  a browser`) and, if anything heavy sneaks in, make it lazy — which is the
  right engine hygiene anyway.
- **Web deploy:** `dist/` is static files — GitHub Pages / any static host.
  This is also the **CI check**: a headless-browser test that boots Pyodide
  and replays the win route guards the app against engine drift.
- **iOS:** Xcode project in `ios/` at the repo root; the build script copies
  `dist/` into the bundle. TestFlight via CCB's Apple Developer account.
  App Review notes (for the later App Store push): fully offline, no accounts,
  no tracking, empty privacy nutrition label; WKWebView-executed code is ours
  and bundled (no remote code — 2.5.2-clean).

## 5. Milestones (each independently shippable)

- **M1 — Playable in a browser.** `dist/` with Pyodide + wheel + a minimal
  terminal (no dressing): boot, type, play the Tomb to 100/100 in Safari.
  *Proves the whole architecture; no Apple anything yet.*
- **M2 — Saves.** Engine PRs (§2), slots UI, autosave, death-RESTORE,
  the determinism-replay CI test.
- **M3 — The phosphor.** CRT visuals, typewriter, sound, accessory bar,
  settings. The web URL becomes shareable-proud. Deploy it.
- **M4 — The app.** Swift shell, haptics, share sheet, icon (a blue-glow
  glyph on black), TestFlight to the summer students.
- **v2 candidates:** App Store release; iCloud save sync; the Layer-3 LLM
  narrator behind a toggle (needs the key-proxy design first); the game-picker
  shell for Action Castle and student games; iPad two-column (map notes?).

## 6. Risks & mitigations

- **Pyodide boot time (~2–3s) and size (~10 MB core + wheel).** Acceptable for
  a game; hidden behind the diegetic CRT warm-up. Cache aggressively on web.
- **WKWebView keyboard jank** (accessory positioning, viewport jumps on focus).
  Mitigated by owning the bar in HTML via `visualViewport` instead of native
  accessory views; M1-in-Safari surfaces this early on real hardware.
- **Engine determinism regressions** would corrupt saves silently — the
  replay-twice-and-diff CI test (§2.3) plus the save version guard make this
  loud instead.
- **Prose width:** the engine's CLI renderer wraps with `textwrap`; the app's
  JSON renderer must emit **unwrapped** text and let CSS wrap to the viewport.
  (Renderer-level; zero engine change.)
- **App Review** (later): text-only games with no purchases sail through;
  the one prep item is good review notes and screenshots that explain the
  genre to a reviewer born after 1990.
