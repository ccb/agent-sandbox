# DESIGN — Interior scenes (DONE — art + wiring both landed)

## State: COMPLETE at commit `f0ae6ac` (suite 1895/0/0; TDD 54+1+10 asserts watched red first)

**Art** (7/7 first-try, ≈$1.75, gpt-image-2 1536×1024) → `tingen/assets/backgrounds/`; door-seam
notes in `asset-gen/out_image2/interiors/` metas + RUNLOG "INTERIOR ART". **Wiring** → 7 scenes,
RoomGraph ids, two-way portals, city-side doors, per-room round-trip tests (`test_interiors`
130/0). RUNLOG entry `## 11:5x — INTERIOR WIRING` has the full table; the essentials:

| room | scene | world size | city door |
|---|---|---|---|
| klein_living_room | KleinLivingRoom.tscn | 896×597 | KleinHouse (3070, 2655) |
| klein_room (bedroom = IntroRoom.tscn) | IntroRoom.tscn | 896×597 | via parlor ONLY (layered) |
| butcher_shop_inner | ButcherShopInner.tscn | 1306×870 | IronCrossMarket east face (3590, 3650) |
| laughing_eel_tavern | LaughingEelTavern.tscn | 1536×1024 | (2157.5, 4170.5) |
| police_station_inner | PoliceStationInner.tscn | 1459×973 | (3885, 4735) |
| selena_almshouse_inner | SelenaAlmshouseInner.tscn | 1152×768 | (4260, 1831.75) |
| mr_frankys_inner | MrFrankysInner.tscn | 1075×717 | (4735, 3645) |
| warehouse_inner | WarehouseInner.tscn | **2688×1792 (3.0× Klein)** | south face (5129.6, 2321.8) |

**Load-bearing judgment calls (do not casually undo):**
1. **There is no standalone butcher building** — Kell's shop door rides IronCrossMarket's east
   face, ~70px clear of his stall waypoints so approaching him can't accidentally portal.
2. **Warehouse door sits WEST of the RiteCache** on the south face so the cult's cache
   approaches never cross the portal; the painted west-side door is a second visual exit only.
3. **KleinHouse was restored verbatim from HEAD** (fill churn had deleted it; its door pin is
   suite-load-bearing) and RowhouseA's geometry reverted to HEAD. **RaphaelCemetery remains
   REMOVED — the fill-rework session (P0.1) owns re-placing it.**
4. Painted-but-unwired seams (deliberate): tavern stairs, police cell, butcher BACK door (the
   M6 deed seam — wire it when a deed needs it). IntroRoom's IntroCard replays on parlor
   re-entry (matches the nave establishing-shot precedent).

Next: play-test every portal round-trip (TESTING_WORKFLOW.md §4 step 8).

## Binding design requirements (user-set)

- **Scale-aware grounds**: warehouse VERY LARGE (~3× Klein rooms in world units — a bigger
  walkable room, never a stretched sprite); tavern/police/butcher mid; almshouse modest.
- **Layered wiring where the fiction wants it**: city → klein_living_room → (inner door) →
  klein_room (existing bedroom). Cathedral→crypt layering already exists — don't disturb.
- Every room: RoomGraph id, TWO-WAY portal, colliders on walls/furniture, city-side door on the
  building's street-facing footprint edge. Doors must not be blocked by furniture colliders.
- npcs.json waypoints stay legal (suite-checked).

## Follow-ups nobody owns yet

1. **Populate the interiors**: furniture Interactables, room-specific items (RoomItems),
   NPC schedule stops INSIDE rooms (butcher behind his counter mid-day; tavern patrons at
   night). Schedules currently target city coordinates for most NPCs.
2. **Interior stimulus/vision tuning**: vision_r appropriate to rooms (a warehouse fight should
   not be visible from the street; Perception.can_perceive is same-room-gated already, so mostly
   ok — but sound/stimulus design through open doors is an open design question).
3. **Interior combat QA**: fight Kell INSIDE butcher_shop_inner — colliders, projectile walls,
   telegraph readability against those backgrounds. Scenario for live_butcher exists in the
   arena; an interior variant would pin room-scale combat.
4. Klein bedroom (klein_room.png) predates the living-room layering — check its door now chains
   through the living room, not straight to city.
