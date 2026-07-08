# The Tomb terminal (web + iOS M1)

*Tomb of Nassak An-Rah* in a blue-phosphor terminal, running the **unmodified
Python engine in the browser** via Pyodide (design:
[docs/design/ios-tomb-app.md](../docs/design/ios-tomb-app.md)). The same
`dist/` is the web version today and what the iOS shell bundles later (M4).

## Build & play

```bash
uv run python app/build_dist.py           # wheel + terminal -> app/dist/
python3 -m http.server -d app/dist 8000   # then open http://localhost:8000
```

First load fetches Pyodide (~10 MB) from the CDN behind the phosphor warm-up;
after that the browser cache makes boot quick. The game is fully offline once
loaded — no keys, no accounts, no network calls.

## What's what

- `app_api.py` — the JS ⇄ Python bridge (the only new Python): `boot(seed)`,
  `command(text)` → `{events, status, suggestions}` as JSON, `transcript()`.
  Owns the RESTORE contract and the every-turn autosave. Runs identically
  under plain CPython — `tests/test_web_terminal.py` tests it directly.
- `terminal.js` / `index.html` / `terminal.css` — the whole UI: Pyodide boot,
  the input line, channel-colored output (♥ damage in red, ✗ blocked dim),
  the Infocom status bar, and the accessory chips (exits + verbs + the nouns
  you could actually mean here, honoring darkness).
- `build_dist.py` — builds the zero-dependency engine wheel (guarded by the
  blocked-imports audit in the test suite) and assembles `dist/`.

## Saves

SAVE / RESTORE / SCRIPT work in-game (slots 1–3 + `auto`, written every turn),
stored in the browser's `localStorage`. A save is `(seed, command journal)`;
restore is a deterministic replay — see `text_adventure_games/saves.py`.

## Roadmap

M1 (this): playable in a browser. M2: saves — done, landed with M1.
M3: full dressing (typewriter, sound, flicker, settings). M4: the SwiftUI
shell, haptics, TestFlight. See the design doc §5.
