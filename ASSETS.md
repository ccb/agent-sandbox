# Licensed art assets

The Godot viewer uses three third-party pixel-art packs whose licenses allow
**use and modification but not redistribution** ("even if modified"). They are
therefore **not in this repository or its git history** — a fresh clone will not
run the viewer until you obtain them and drop the files in at the paths below.

Everything else the map needs (Kenney's RPG Urban Pack under
`godot-generative-agents/tools/geo/assets/kenney/` and the sheets derived from
it in `godot-generative-agents/godot/maps/`) is CC0 and stays committed.

## The packs

| Pack | Author | Get it | Price | License (summary) |
| --- | --- | --- | --- | --- |
| Cute Fantasy RPG | Kenmi | <https://kenmi-art.itch.io/cute-fantasy-rpg> | Free tier (premium ≥ $3.99) | Free tier: non-commercial use, credit Kenmi; no redistribution/resale, even if modified |
| Cute Fantasy UI | Kenmi | <https://kenmi-art.itch.io/cute-fantasy-ui> | ≥ $2.99 | Commercial + non-commercial use; no redistribution/resale, even if modified |
| Fantasy RPG Interior Pack | Franuka | <https://franuka.itch.io/fantasy-rpg-interior-pack> | ≥ $3.99 | Commercial + non-commercial use; link-back requested; no redistribution/resale. The School/Bath/Alchemy/Bedroom/Clockwork/Music expansions are free updates included in the base pack. |

## Where the files go

All paths are relative to the repository root. These paths are gitignored, so
the dropped-in files stay out of version control.

### 1. Cute Fantasy RPG (free tier) → `godot-generative-agents/godot/Cute_Fantasy_Free/`

Unzip the free pack so its folders (`Animals/`, `Enemies/`, `Outdoor decoration/`,
`Player/`, `Tiles/`, `read_me.txt`) sit directly under `Cute_Fantasy_Free/`.
The viewer animates `Player/Player.png` (a 6×10 grid of 32×32 frames) as the
agent sprite (`godot/scenes/viewer.tscn`, `godot/scripts/viewer.gd`).

Then make the two derived copies the map and the web writeup expect:

```bash
cd godot-generative-agents
cp "godot/Cute_Fantasy_Free/Outdoor decoration/Outdoor_Decor_Free.png" \
   godot/maps/decor_plants.png            # campus plants tileset (112x192, 16px tiles)
cp godot/Cute_Fantasy_Free/Player/Player.png \
   web/public/sprites/player.png          # agent-card portrait in the web writeup
```

### 2. Cute Fantasy UI → `godot-generative-agents/godot/Cute_Fantasy_UI/`

Unzip the UI pack so the `UI/` folder sits under `Cute_Fantasy_UI/`. The theme
(`godot/theme/cute_fantasy_ui.tres`) reads `UI/UI_Frames.png`, `UI_Buttons.png`,
`UI_Sliders.png`, `UI_Ribbons.png`; the sidebar reads `UI/UI_Button_Icons.png`
and `UI/UI_Icons.png` (`godot/scripts/agent_panel.gd`).

### 3. Fantasy RPG Interior Pack → `godot-generative-agents/godot/maps/`

Copy the **`1x/` (16 px)** sheets out of the pack and rename them:

| Pack sheet (`1x/`) | Repo path | Size |
| --- | --- | --- |
| `Fantasy RPG Interior Pack (16x16 grid).png` | `godot/maps/interior_franuka.png` | 512×512 |
| `Expansion_School.png` | `godot/maps/interior_school.png` | 256×256 |
| `Expansion_Bath.png` | `godot/maps/interior_bath.png` | 256×256 |
| `Expansion_Alchemy.png` | `godot/maps/interior_alchemy.png` | 512×512 |
| `Expansion_Bedroom.png` | `godot/maps/interior_bedroom.png` | 512×512 |
| `Expansion_Clockwork.png` | `godot/maps/interior_clockwork.png` | 512×512 |
| `Expansion_Music.png` | `godot/maps/interior_music.png` | 512×512 |

(Exact expansion filenames may differ slightly between pack versions — match by
theme and the pixel sizes above. The campus map, `godot/maps/upenn_core_urban.tmj`,
references these sheets by the repo filenames.)

## First launch

Godot regenerates the `*.import` sidecars for the dropped-in files on first
import (`godot --headless --import`, or just open the project). Because the
sidecars are regenerated, the first launch may log `uid://` remap warnings for
`viewer.tscn` and `cute_fantasy_ui.tres` — Godot falls back to the file path
and everything loads; the warnings disappear once the editor re-saves.

Verify with `./godot-generative-agents/run_smoke_test.sh` — it fails loudly if
any sheet is missing or misplaced.

## Exported builds (the `.pck` decision)

Exported native and WASM builds (including the `index.pck` served by the web
companion) **do bundle this art**. That is the packs' intended, licensed use —
shipping assets inside a game build. What the licenses prohibit, and what this
repository therefore avoids, is redistributing the **source asset files**
themselves. Web deploys are built locally from a tree that has the assets
present (see `godot-generative-agents/web/`); CI restores them from a private
bundle available only to the team.

## Credits

- **Kenmi** — Cute Fantasy RPG & Cute Fantasy UI: <https://kenmi-art.itch.io/>
- **Franuka** — Fantasy RPG Interior Pack: <https://franuka.itch.io/> · <https://twitter.com/franuka_art>
- **Kenney** — RPG Urban Pack (CC0): <https://kenney.nl/assets/rpg-urban-pack>

Per-sheet provenance detail lives next to the map:
`godot-generative-agents/godot/maps/DECOR_CREDITS.md` and `INTERIOR_CREDITS.md`.
