# DESIGN — Weapon/tool item system: as built + designed extensions

## As built (commit `cc4e2e2` — done, reviewed SHIP, do not rework)

User directive: "I don't want ammo to be a built-in variable, that should be tied with the
weapon/tool system."

- `data/items.json` (ARRAY shape, pre-existing loader): `revolver` {category "weapon",
  `grants: ["revolver_shot"]`, `ammo_item: "revolver_round"`}; `revolver_round` {category "ammo"}.
  `ItemDef.gd` parses grants/ammo_item shape-guarded; categories extended.
- `ItemDB.weapon_for_ability(agent, ability_id)` — the ONE resolution helper: a CARRIED
  (inventory count > 0) weapon whose grants includes the ability; stable ascending-id pick;
  plain-Dictionary return; agent-generic (duck-typed `item_count`).
- `PlayerCombat.try_pay` (the executor cost seam, check-all-then-deduct-all): `ammo` cost →
  resolve weapon (`no_weapon` refusal) → count rounds (`no_ammo`) → consume
  `remove_item(ammo_item, n)`. Refusal precedence no_weapon > no_ammo, pinned by assert.
  The old pool (`ammo` var, `AMMO_META`, `REVOLVER_START_AMMO`) is DELETED.
- Starting loadout: `data/scenario.json` `player_loadout {revolver: 1, revolver_round: 12}`,
  granted ONCE in `AgentRegistry.ensure_player_proxy`'s creation branch (re-ensure never
  re-grants; registry rebuild = intentional re-arm, matching old died-with-proxy semantics).
- HUD reads `PlayerCombat.ammo_count()` — data-driven (first kit ability with an ammo cost →
  its granting carried weapon → ammo_item count; −1 → "—").
- COMBAT_SPEC §2 cost row documents all of this for the Yumina port (its id→count inventory is
  already the right shape). Stamina/spirituality remain body pools BY DECISION (metabolic, not
  equipment) — user was offered the choice and did not take it; ask before changing.

## Designed but UNBUILT (in rough priority order)

1. **Reload / ammo pickups.** SHIPPED in M13. Design:
   - **World spawn table** (`data/scenario.json` `ammo_spawn.spawns`): 24 rounds across 8 piles —
     city 12r (4×3), cathedral_nave 6r (2×3), cathedral_crypt 6r (2×3). Seeded by
     `AmmoSpawn.seed_run()` in `RunManager._reset_run_world` after `RoomItems.clear()`. Resets
     clean per run (no carry/leak). `AmmoSpawn.seed_run_room(room)` available for per-room re-seed.
   - **Economy tuning (TUNING numbers, 2026-07-11):** 12 starting rounds + 24 world pickups = 36
     total per run if all found. A careful player can maintain fire for a ~60-minute run; ammo
     stays a resource (not infinite — average fight uses 3–6 rounds, so ~6 full engagements from
     the loadout alone). Mr Franky buy source: SHIPPED in M15 as the Shop autoload — 6 rounds for
     4 shillings, max 3 restocks/run (coin-gated, stock-latched). Economy: 12 starting + 24 world
     pickups = 36 found, plus up to 18 bought = 54 ceiling per run.
   - **Pickup seam:** `PlayerCombat._try_pickup_nearby()` — proximity auto-take (48 px) each
     physics frame via `RoomItems.take_near` → `proxy.add_item`. Engine-neutral; same path as NPC
     `gather_item`. `RoomView._make_item_node` renders the pile as a labelled sprite.
   - **Empty-gun feedback:** `PlayerCombat._on_weapon_empty()` emits `weapon_empty` on EventBus
     + calls `CombatFeedback.flash()` (gated by `hit_flash` Settings toggle — cosmetic only, never
     alters `try_pay` semantics). `CombatHUD` listens to `weapon_empty` and pulses the ammo label
     red (also `hit_flash`-gated). The event fires even with flash OFF.
   - **CitySummoning fix:** `_bootstrap` now calls `_clear_room("city")` + `AmmoSpawn.seed_run_room("city")`
     instead of `RoomItems.clear()` — cathedral pickups survive the City scene re-entry.
   - **Mr Franky buy source:** DONE in M15 (the shop/economy sprint). `Shop` autoload owns the
     coin loop (scenario.json `shop` block: shilling coin item, buy 6 rounds/4sh with a 3-restock
     per-run stock latch, sell table tainted=6/hunter=10). `Interactable.gd` gained the generic
     `shop_sell_harvest` / `shop_buy_ammo` export flags (ritual_interrupt pattern); the counter
     lives in `MrFrankysInner.tscn` (`ShopCounter`). `AmmoSpawn.franky_buy()` now DELEGATES to
     `Shop.buy_ammo()` — costed + latched, the free-tap warning is closed. The opening fork's
     SELL option is honest: `GMOpening.choose_harvest("sell")` stores the choice and surfaces the
     authored `opening.sell_hint` pointing at the counter. Harness: `tests/test_shop.gd`.
2. **NPC cost enforcement.** NPCs have NO cost_provider — infinite monster stamina is fine
   (form kits are authored around it), but a HUMAN NPC with a gun would have infinite rounds.
   The seam exists (`CombatExecutor.cost_provider`, asked last so refusals burn nothing);
   `weapon_for_ability` is already agent-generic. Design question: do NPCs carry literal items
   (visible in world, lootable from downed bodies — strong RPG/hidden-monster potential: count the
   butcher's cleavers) or get an abstract provider? RECOMMENDATION: literal items + a
   generic AgentCostProvider; loot tables on downed (never-deleted) bodies.
3. **More weapons/tools as content**: police truncheon (constable_brom), boat hook (dockhand),
   the occult tools already in OccultToolManager should migrate INTO items.json weapons/tools
   with grants — one schema for everything the hands hold. paper_charm is a candidate
   "tool with charges" (charm papers as consumable ammo_item) — would exercise a second
   granting weapon and the multi-weapon determinism path.
4. **Kit ↔ carried-weapon interaction.** Today the kit (combat_forms.json) says what arts a
   form KNOWS; items say what the hands HOLD; revolver_shot needs both (kit lists it + weapon
   grants it, else no_weapon). Extension: derive part of the kit FROM carried weapons
   (kit = form base + Σ carried grants). That makes disarming/looting meaningful and is the
   natural end-state of the user's directive — but it changes tactical band derivation inputs
   (bands_for reads kit defs), so re-run the vector dump if you do it. Design first; it touches
   COMBAT_SPEC §1.2/§2.
5. **Drop/throw/give**: inventory verbs exist for ritual materials; weapons should ride the
   same verbs (a fleeing cultist dropping the grimoire already works — a dropped revolver
   should too). Mostly data + pickup wiring once (1) exists.
