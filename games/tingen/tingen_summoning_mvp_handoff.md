# Handoff — `City.tscn` context + Summoning-MVP wiring

> **For a fresh agent** (no prior conversation). Goal: finish the **cult-summons-the-god MVP** in the Godot game. **Read this first, then `tingen_summoning_canon.md` (lore/rules) and `text_adventure_games/adventures/tingen.py` on the `game/tingen` branch (a working engine reference of the same loop).**
>
> **Biggest thing to know:** most of the summoning system **already exists and is wired** (autoload singletons, an LLM-driven agent loop, a countdown "doomsday clock", cult NPCs, a rite gate, player interference). **Do not rebuild it.** The gaps are small and listed at the end.
>
> Godot project root: `Tingen-Game/tingen/`. Python sidecar: `Tingen-Game/agent-sidecar/`.

## How to run
- **Sidecar (LLM brains):** `cd agent-sidecar && python sidecar.py` (uses `ANTHROPIC_API_KEY`, model `claude-haiku-4-5`; **no key → returns `idle` for all agents**, so the game still runs on the ambient fallback).
- **Godot:** open `tingen/` in Godot 4, run `scenes/Main.tscn`. Set `HttpSidecar.base_url` to `http://127.0.0.1:8777` to use the sidecar; `""` disables networking (pure ambient fallback, no freeze).

---

## 1. `City.tscn` — exact current structure (`tingen/scenes/City.tscn`)
A small **overworld traversal hub** (121 lines, placeholder test art). Node tree:
- `City` (Node2D, `y_sort_enabled`)
  - `Ground` (StaticBody2D): `Sprite` (`assets/ui/ground_test.png`, scale 2.5) + 4 edge colliders forming a **6270×6270 boundary box** (`EdgeTop/Bottom/Left/Right`).
  - `Chapel` (StaticBody2D @ (2118,5015)): `chapel_test.png` sprite + `ChapelNave`/`ChapelTower` colliders + **`ChapelDoor`** (Area2D, `Portal.gd`, `target_scene = CathedralNave.tscn`).
  - `Blackthorn` (StaticBody2D @ (1677,1648)): `blackthorn.png` + collider + **`HQDoor`** (Area2D, `Portal.gd`, → `NighthawksHQ.tscn`).
  - `Player` (instance of `Player.tscn`) @ (1854,5523) — starts by the chapel.
  - `NeilHomeDoor` (Area2D @ (2700,3600), `Portal.gd`, → `NeilHome.tscn`).
  - `HintLayer` (CanvasLayer) → `Hint` (Label): "WASD/Arrows to move · walk onto the chapel steps to enter".

**No script on the `City` root; no NPCs in City.tscn.** Scene changes are driven by `Portal.gd` on the Area2D doors → `SceneFade.go(target)` → `WorldState.request_transition()` → `GameController._swap_world()` (swaps only the `World` subtree; the HUD persists).

**Two overworlds (open design issue):** `City.tscn` = handcrafted intro hub (chapel/Blackthorn/Neil). `CityBlocks.tscn` = the **procedural district** built from `data/city_layout.json` (building grid + colliders, `DayNight` tint, the **Iron Cross Warehouse + `WarehouseCache`**, and the placed cult NPCs Orin/Dalia). The cult rite currently lives in **CityBlocks (warehouse)**, not City.tscn. These two should be reconciled (see Decisions).

## 2. Agent architecture (already built)
**Autoload singletons:** `WorldState`, `Clock`, `Agents` (AgentRegistry), `AgentRuntime`, `SummoningPlan`, `NpcDB`, `SceneFade`, `EventBus`, `ActionSchema`, `PlayerActions`, plus `GameController` (on Main).

**Beat loop:** `Clock` emits beats → `AgentRuntime.run_beat()`:
1. Overseer directives, 2. **active agents** (within `active_radius` 240px of player) deliberate via the sidecar, 3. inactive agents run **fallback waypoint movement** (`Agent.tick_fallback` / scheduled `npcs.json` waypoints).
- **Decision flow:** `Perception.gd` builds a snapshot (id, faction, role, intent, position, nearby, recent_events, pressures, phase, beat) → `HttpSidecar.propose()` (background thread, **1-beat latency cache**) → POST `/propose` to `sidecar.py` → Claude returns `{"verb","args"}` → validated by `ActionSchema.validate()` + a Critic → executed by `ActionCommit.commit()`.
- **NPC node:** `scenes/NPC.tscn` (CharacterBody2D, group `npc`, `npc_id` export) + `src/NPC.gd`; binds to an `Agent` (`src/Agent.gd`: id, faction, role, intent, position, inventory, hp, short_memory). Steers via `NavigationAgent2D` toward agent goal or scheduled waypoint.
- **Action verbs (`data/action_schema.json`):** `move_to, talk_to, gather_item, perform_ritual_step, hide, flee, attack, recruit, report, pray, idle`.

## 3. Summoning system (ALREADY EXISTS — reuse, don't rebuild)
- **`SummoningPlan.gd`** (autoload) — the doomsday clock. Vars: `countdown_beats` (START 40), `impede_score`, `ingredients` (`{ritual_salt:3, consecrated_chalk:2, candle:3}`), `climax_fired`. Methods: `tick_countdown()`, `advance_rite(beats)` (cult hastens descent), `remove_ingredient()`/`add_ingredient()` (sabotage setback), `manifestation_strength()`, `closeness_ratio()`, `interference_band()`. **Signals:** `countdown_changed`, `summoning_climax(strength)` (fires once at countdown 0).
- **`ActionCommit.gd`** — `SITES.iron_cross_warehouse` + `RITE_RADIUS = 80`. `perform_ritual_step` only advances the rite if a **cult** agent is within 80px of the warehouse → `SummoningPlan.advance_rite(1)` + emits `ritual_advanced`.
- **Cult cast (`data/npcs.json`):** `clerk_voss` (cult **leader**, intent "Complete the warehouse summoning…"), `fishwife_dalia` (cult **logistics**, moves ingredients), `lamplighter_orin` (cult **scout_waverer**, can be flipped), `dockhand_pell` (civilian **victim/sacrifice**), `old_neil` (civilian alchemist).
- **`data/rituals.json`:** `summoning_descent` — name "The Descent", ingredients, and **4 steps** (inscribe chalk circle → light 3 candles → lay salt wards + speak the name → offer the marked sacrifice).
- **`data/gods.json`:** `outer_god` (外神, the cult's target) and `goddess_of_night` (黑夜女神, `opposes_cult:true`).
- **Player interference:** `PlayerActions.sabotage()/social_influence()` (+impede), `Interactable.gd` `sabotage_cache` (the `WarehouseCache` lets the player strip an ingredient + add setback; `social_influence` flips Orin the waverer cult→ally).
- **UI:** `CultProgressPanel` (key C) shows closeness bar + interference band + ritual stock + intel; events are allow-listed so secret agent actions never leak to the player.
- **Climax-room template:** `NeilHome.tscn` `RoomState.gd` flips normal↔`lost_control` at `corruption_threshold = 60`; `RitualTrigger` (Interactable) toggles it. Reuse this pattern for the descent room.
- **Ritual site scene:** `CathedralCrypt.tscn` exists ("sealed-artifact vault & ritual site"), reachable via CathedralNave stairs.

## 4. Current state vs. gaps (the actual MVP work)
| Piece | State |
|---|---|
| Cult NPCs + goals/intent | ✅ exist (Voss/Dalia/Orin in npcs.json) |
| LLM agent loop + sidecar | ✅ wired (mock-safe without key) |
| Ritual site + rite gate | ✅ warehouse + RITE_RADIUS + `perform_ritual_step → advance_rite` |
| Countdown / closeness / manifestation strength | ✅ `SummoningPlan` |
| Player interference (sabotage/social) | ✅ `PlayerActions` + `WarehouseCache` |
| Cult-progress UI | ✅ `CultProgressPanel` |
| **Gather → shared cache transfer** | ⚠️ `gather_item` fills *per-agent* inventory; **no hook moves it into `SummoningPlan.ingredients`** → add a `contribute_item` verb or a post-commit hook |
| **Climax scene + transition** | ❌ `summoning_climax` signal fires but nothing consumes it → build the descent scene (use `CathedralCrypt.tscn`, the NeilHome RoomState pattern) |
| **Final encounter / EndGameResolver** | ❌ not implemented → descent outcome scaled by `manifestation_strength()` |
| **Two-overworld reconciliation** | ⚠️ City.tscn vs CityBlocks.tscn (see Decisions) |

## 5. Decisions the OWNER (Mark) must make before/at handoff
1. **Where is the rite — Warehouse or Crypt?** The *code* already does it at the **Iron Cross Warehouse** (`ActionCommit.SITES`, `WarehouseCache`, CityBlocks). The *canon/design doc* (`tingen_summoning_canon.md`) and the engine reference (`tingen.py`) put it in the **Cathedral Crypt**. **Pick one** (or make the crypt the cathedral-route variant of the dynamic site). Everything downstream (climax scene, player route) depends on this.
2. **Two overworlds:** keep both (City = intro, CityBlocks = main) or unify into one walkable map?
3. **Align ingredients with canon?** `rituals.json` uses generic `ritual_salt/consecrated_chalk/candle`. The canon doc specifies **silver dagger, candles (2 deity-domain materials each), water+salt+parchment, animal hide (inscribe the Honorific Name), a tiered sacrifice, and a descent vessel (a body — or the special infant, the "真神之种")**. Decide whether to upgrade the ingredient list + add the **sacrifice** and **vessel** as required items.
4. **MVP cut line:** is the win-state the `summoning_climax` firing (countdown hits 0 undisturbed) + a simple descent scene, or a full final encounter?

## 6. Suggested minimal task (once #1–#4 are decided)
1. Add **`contribute_item`** (cult agent at the rite site moves gathered ingredients from `Agent.inventory` → `SummoningPlan.ingredients`) so gathering actually feeds the cache.
2. Give cult agents a **gather→deliver→perform_ritual_step** behavior at the chosen site (the sidecar + intent already push toward this; verify the Critic permits cultists).
3. Consume **`summoning_climax(strength)`**: fade to the ritual-site scene, flip it to a "descent" RoomState, spawn the cult cast, and resolve by `manifestation_strength()` (player interference = weaker/easier).
4. Wire the player counters end-to-end (sabotage cache, flip Orin, and — per canon — destroy the **vessel** / interrupt the rite / kill the avatar in the descent window).
5. (If aligning with canon) update `rituals.json` ingredients and add `sacrifice` + `vessel` as required gather targets.

## References
- **`tingen_summoning_canon.md`** — the verified LotM summoning rules + the deterministic cult-agent step sequence + specific materials + the vessel (Megose baby) mechanic. The design source of truth for *what* the rite is.
- **`text_adventure_games/adventures/tingen.py`** (on the `game/tingen` branch of `ccb/agent-sandbox`) — a runnable text-engine version of the same cult-vs-detective loop (Cathedral+Crypt+Blackthorn, cult NPC with a goal, corruption→threshold gate, `perform ritual`/`expose cult`). Useful as a behavioral reference.
- Key files to read first: `src/AgentRuntime.gd`, `src/ActionCommit.gd`, `src/SummoningPlan.gd`, `src/HttpSidecar.gd` + `agent-sidecar/sidecar.py`, `data/{npcs,rituals,gods,action_schema}.json`, `scenes/{Main,City,CityBlocks,CathedralCrypt,NeilHome}.tscn`.
