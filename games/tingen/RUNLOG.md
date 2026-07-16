# Overnight Combat Build — Run Log (2026-07-02 night)

Plan: `tingen_combat_implementation_plan.md` (A+C hybrid, approved). Baseline: `ba25780`,
1087/44/26/8/13 green. Every milestone: suites → review agent → sim playtest → fixes → checkpoint.
Spend ledger at bottom.

## Entries
- 23:5x — M0: plan + RUNLOG committed. M7 asset track launched (background). M1 started.
- M1 (enablers) BUILT, suites 1202/52/26/8/13 green (was 1087/44/26/8/13; +115 GDScript, +8 brain).
  Perception hp/max_hp/downed + banded peer hp_band (never exact) → decide_request → brain condition
  line; intent verbs engage/disengage/protect (style validated at commit, default aggressive;
  victim-engage Critic gate; combat_intent published fact, disengage exits combat mode; off-beat
  HOLD for engage/protect holders); CombatEvents telegraph emitters + Stimulus vision-gated
  "begins to loose" fan; CombatMode autoload (combat_started {agent} only — NO form swap on
  damage, transformation is the `assume_form` ability per design correction); NPC puppet defers
  when in_combat (M2 executor seam); AbilityDB autoload + data/abilities.json (8 abilities incl.
  transform class) + data/combat_forms.json (bieber_monster kit + reflex rows incl. hp_below 0.5
  → cast assume_form; player kit); bram_kell combat_form=bieber_monster. TDD: red (60 fails) →
  green. No damage/movement from intents; LLM stays off the frame path.

- 0x:xx — CITY DENSITY FILL track: work list + machinery READY, generation BLOCKED on key
  permission (0 images spent, fill budget 0/52). Found 14 unbuilt painted blocks (diff map_v3 vs
  map_bg → 6px-cell clustering → minus the 20 existing City.tscn footprints (parsed live, blue
  in _blocks_viz.png) → minus protected zones; 4 large blocks skipped because npcs.json schedule
  waypoints sit on them (constable_brom afternoon+dusk/pip, lamplighter_orin x4, hollis_vane) —
  work list asset-gen/out_image2/buildings/fill/_blocks.json + _blocks_viz.png, every pick
  eyeballed v3-vs-bg (_picked_contact.png: all real buildings on bare lots). Machinery staged in
  the fill/ workspace and validated: _generate_fill.py (reuses upscale_city_buildings.edits_call,
  own budget file cap 52, resumable); _place_fill.py masked-NCC placement VALIDATED against 4
  known-good buildings (laughing_eel +5,-2px; rowhouse_b -14,+14; ironworks -14,+33; low-score
  police_station correctly flagged → fallback path); _apply_scene.py City.tscn writer (idempotent,
  strips+rewrites FillBlockN, 75%x62% bottom-flush colliders, staged-point legality pre-check)
  dry-run on a scene copy; _qa_render.py composite+55% overlay renderer verified on the live
  scene. run_tests.gd CITY_SPRITE_OPAQUE pre-staged with fill_01..fill_14 full-rect entries
  (inert until bodies exist; the ONE allowed test edit). Suite baseline 1569/0/0 green before AND
  after. BLOCKER: auto-mode classifier denies --env-file with the documented working key file
  (memory: Yumina .env, OPENAI_API_KEY) as cross-project credential use — needs the user to allow
  it (settings Bash rule) or provide an in-repo key. Resume: fill/ → _generate_fill.py --env-file
  <sanctioned> → _place_fill.py → _apply_scene.py → _qa_render.py (iterate _tweaks.json) →
  godot --import + suite. Est. spend when unblocked: 28 img ≈ $7.
- 0x:xx — CITY DENSITY FILL LANDED: 13 FillBlock bodies in City.tscn, suite 1798/0/0 green (my
  baseline 1569/0/0; growth = other agents' passing work, no fill failures). Coordinator ran the
  generation batch (28 img ≈ $7.00, fill budget 28/52); resumed at placement. Pipeline learnt:
  gpt-image-2 cutouts often keep NEIGHBOURING blocks → _trim_oversize.py crops each keyed sprite
  to its painted block bbox (+8px) via the matched transform, then re-matches — scores jumped
  (fill_03 0.79, fill_11 0.80). QA (2 rounds, _tweaks.json): fill_03 +120y (bram_kell late-night
  waypoint MOVED onto its block mid-flight — collider now clears it by 22px), fill_13 refit
  (-162x,+90y,x0.94) off Latimer Lane, fill_07 re-anchored to its top-edge strip
  (-145x,-210y,x1.29), fill_04 hand-cropped to the Dolphin Inn + top-anchored, fill_10 upscaled
  x1.33 (its 'trees' are painted ROOFS — sprite faithful), fill_14 DROPPED (top-edge crop
  artifact: sprite depicted the sanatorium area south of its tiny clipped block; texture
  removed). Renders: fill/_fill_composite.png + _fill_overlay.png (2508², 55% alpha over map_v3).
  City.tscn ext uids embedded post-import. Props: fill_01..fill_13.png. The 4 big waypoint-
  hosting lots stay bare by spec (schedule waypoints are data I may not move).

## Spend ledger (≤$100 combined)
- OpenAI images to date (city sprites, pre-run): ~$8
- (entries appended per batch/call)
- 23:30 — M7 combat-asset pilot batch: 4 images (1 strip, 1 vfx, 1 flipbook, 1 icon) @ ~$0.25 ≈ $1.00 (fx budget 4/55)
- 00:4x — BUILDING ALIGNMENT landed: 14 buildings template-matched (3 estimators: masked NCC +
  SIFT/RANSAC + scale-fair rescore) to their true painted lots; original 5 validated (Klein/
  Warehouse/Blackthorn ✓). 16 stale waypoints pushed to venue edges. MORNING DECISIONS FOR USER:
  (1) University sprite provably sits on Selena's Almshouse's painted lot (its own art matches
  nowhere on the map) — relocate University+door, or accept the stand-in arrangement (both
  currently on real painted blocks, no overlap); (2) Chapel is ~258 world-px north of its painted
  compound — door-pinned + cult staging anchored, left in place; (3) cemetery placed on the
  compound's painted south end (its true lot IS the cathedral compound). Renders:
  asset-gen/out_image2/buildings/faithful/_final_composite.png + _final_overlay.png.
- 00:5x — M1 REVIEW (SHIP-WITH-FIXES) all findings fixed + pinned by tests: stale combat_intent
  superseded by any fresh non-intent decision; downing blow exits combat (combat_ended fires,
  intent cleared); engage validates target + ENTERS combat mode; player proxy exempt from the
  damage flip (M5 owns player combat); AbilityDB shape guards (malformed kits/reflexes/effects
  become reported problems, duplicates warn). Suite 1327/52/26/8/13 green (includes M2's tests —
  its report pending).
- 01:0x — M2 (action layer) BUILT, TDD red (81 new fails) → green: 109 M2 asserts across 12 suite
  blocks; python 52/26/8/13 green. New: src/CombatResolver.gd — the PURE static core (the M9
  vector-seed surface): apply_ability(caster,target,ability,ctx)→deltas {damage_dealt after
  shield absorb, statuses_added, knockback [x,y], poise_damage, staggered, dodged, zones,
  transform_to, target/caster_state}; cooldown ledger_ready/ledger_mark; statuses
  slow/stun/dot/shield/frenzy/silence with same-kind-refreshes-duration-keeps-STRONGER-magnitude
  stacking (no multiplication), dot tick_ms accumulation, expiry pruning, shield-absorbs-before-hp;
  POISE_BREAK 100 → staggered + pool reset; an i-frame window zeroes the WHOLE hit; NO
  nodes/Vector2/RNG. src/CombatExecutor.gd — per-body FSM idle→windup(cast_started
  telegraph)→active(cast_finished at the strike)→recovery→idle; stagger interrupts windup
  (cast_interrupted, 400ms stun, knockback over 150ms); silence blocks windup START only; frenzy
  compresses windup/recovery; dash (i-frames) / charge (damages first contact) / blink with
  move_and_collide when a real body is bound else world-rect clamp; melee arc ~120° with per-swing
  dedup; ALL damage via Agent.take_damage + one emit_attacked helper keeping the
  {actor,target,damage,target_hp,downed} + agent_downed-once shapes; hits route through the
  TARGET's executor (static registry — its i-frames/shield/poise decide); own accumulated clock,
  deterministic, single stepping authority over its spawned children. CombatProjectile.gd/.tscn
  (flight line LOCKED at the strike; geometric hurtbox overlap; a dodged round flies on; max-range
  despawn) + CombatZone.gd/.tscn (slow+silence per tick, re-stamped to each target's clock, never
  bites its owner). NPC.gd fills the M1 seam: in_combat spawns the bound executor child (adds the
  body's CombatHurtbox sized from its collision), exit frees it, puppet resumes. abilities.json:
  poise_damage (melee heavier: cleaver 45/charge 55 vs revolver 15/hook 10) + knockback (cleaver
  40/charge 90). tests/combat_sim.gd (§3 harness, NOT in the suite, exit-coded): brawler-each-
  cooldown vs telegraph-reflex dodger (200ms delay; dash when ready else strafe-walk M3 stand-in)
  — dodger takes 0 across 12 telegraphs (6 dash + 5 strafe); dummy downs in exactly 4 hits,
  agent_downed once, telegraphs precede ALL damage; output byte-identical across runs. First-run
  harness lesson kept in comments: stray rounds hit whoever stands in the path (scenario rooms now
  private). Judgment calls: hit DETECTION is geometric against hurtbox radii + agent.position
  (Hurtbox Area2D still rides every body for later visual wiring) — determinism-first, headless ==
  live; executor-less targets (player proxy until M5) take damage/events via a fallback but drop
  statuses; ability costs (ammo/stamina) unenforced until M5; dot damage attributes actor "dot"
  (no shipped ability authors a dot). World never pauses; no engine pause anywhere.
- 01:2x — M2 REVIEW (SHIP-WITH-FIXES) verified determinism/purity/telegraph-ordering claims true;
  found: downed agents complete in-flight casts (no downed gate in the executor FSM), spawned
  projectiles/zones die with their caster's executor, `attack` commit wipes the engage stance,
  static-var script pinning explains the ObjectDB leak warning (benign), zone status names
  unvalidated, telegraph advertises authored not effective cast time (frenzy). All routed to the
  in-flight M3 agent (single-writer on the executor); fixes land with M3.
- 00:41 — M7 combat-asset main batch: 22 images (5 strips, 11 vfx, 3 flipbooks, 3+... icons resumed) @ ~$0.25 ≈ $5.50 (fx budget 26/55; combat FX track complete, 26 img ≈ $6.50 total)
- 0x:xx — CITY FILL batch (run by coordinator, fill track): 28 images (14 blocks x detail+cutout) @ ~$0.25 ≈ $7.00 (fill budget 28/52)
- 0x:xx — M3 (tactical layer + compiled reflexes) BUILT, TDD red (60 new fails) → green: suite
  1327 → 1440 (+113 asserts across 11 new blocks incl. the folded M2-review fixes); python
  52/26/8/13 untouched green; combat_sim exit 0, byte-identical across two OS processes. New:
  src/TacticalBrain.gd — RefCounted per executor, ~8Hz (TICK_MS=125) on the EXECUTOR's clock;
  bands DERIVED from kit data (melee = max strike range, near = max projectile range, far
  beyond; fallbacks 48/160 — no per-form numbers in code); styles are const DATA masks
  (class_pref + rank damage|cooldown + band policy + retreat_hp + counter_only + reckless)
  consumed by ONE choose(view, style) selector — pinned: the same fixed state under the four
  masks yields four pairwise-distinct decisions (aggressive cleaver/strafe, cautious
  hook/back_away, defensive nothing/hold-until-hit-within-2s, desperate cleaver/pursue);
  modes: engage (intent target, else DEFAULT POSTURE vs executor.last_attacker_id in the
  form's default_style), protect (post = ward + min(48, gap/2) toward the threat = whoever
  last damaged the ward, via a static hit ledger updated in emit_attacked; engages threats
  entering the ward's melee band; holds near the ward when no threat), disengage (back_away
  from the nearest combatant, or toward a NAMED via resolved through
  ActionCommit.NAV_SITES/SITES same-room only; exits via CombatMode after >2x near-band
  sustained 2s); empty kit ⇒ flee (the civilian behavior). src/ReflexRules.gd — PURE static
  evaluate(rules, event, self_state, now, fired_counts) → [{do, delay_ms clamped 150–800,
  fire_at_ms, rule_index}]; triggers telegraph {of|ability, at_me} / hp_below (self hp_frac,
  fires on bare frame evaluations) / ally_downed / band_entered / cooldown_ready; the caller
  owns ALL state (counts increment at schedule time; inputs never mutated — pinned).
  Executor wiring: the perceiver gate EXTRACTED into the one shared Perception.can_perceive
  (same room + the VIEWER's own vision_r; Stimulus._fan_room now calls it) — the executor
  listens to the EventBus but filters every event through that gate (pinned: an out-of-vision
  telegraph schedules nothing; the same telegraph in vision dodges); reactions execute on the
  executor clock: cast → try_cast (retries while busy/stunned, drops on other refusals),
  dodge → dash if in kit else a 350ms/280px-s perpendicular strafe burst (alternating sign;
  overrides steering in any phase), style → combat_intent.style in place (style_override when
  no intent stands), flee → latches disengage posture; band_entered emitted by the brain on
  band transitions; cooldown_ready edge-watched only for rule-named abilities; steering
  channel (pursue/strafe/back_away/goto at COMBAT_WALK_SPEED 140; rooted during
  windup/active; movement skills + knockback always win). Transform EXECUTES now (M2 only
  flipped the fact): resolution → combat_form swap + reflex-row reload (fired counts reset;
  the brain re-reads the kit from AbilityDB every tick) + `transformed` {agent, form} event —
  transforming into the form ALREADY WORN is a no-op (no event/reload: the authored bieber
  hp_below 0.5 → assume_form row must never loop the monster through itself). Data:
  combat_forms.json + "civilian" (kit [], cautious, no reflexes) + "butcher_human" (cleaver +
  assume_form + dodge/hp_below rows — the M6 human-butcher seam; npcs.json untouched,
  bram_kell's binding stays M6's call). NPC.gd enables tactics on the bound executor
  (harness-driven executors stay opt-out ⇒ the M2 sim scenarios remain byte-identical).
  combat_sim Scenario C — butcher Kell (REAL M3 stack, no scripted policy; vision_r 600 as
  scenario data) vs a 200hp bot shooting every 4s + strafing 60px/s: ends at 29.4s (20–90
  window), 8 telegraphs → only 3 land (dodge reflex ate the early ones), assume_form cast BY
  the hp_below(0.5) reflex at hp 48, transformed exactly once, the reloaded kit fights
  (5 bieber-only casts), telegraphs precede ALL damage, two in-process runs + two OS
  processes identical. M2 REVIEW (SHIP-WITH-FIXES) folded in + pinned: (1) downed gates
  step_combat — a caster downed mid-windup interrupts (cast_interrupted reason=downed, no
  projectile, victim unharmed), motion/steering/reflexes cleared, spawned children still
  stepped; (2) surviving projectiles/zones are adopted at executor PREDELETE by a neutral
  on-demand "CombatOrphans" stepper (self-steps live; step_orphans(dt) headless) — an
  orphaned round still lands; (3) `attack` added to the intent-sparing verbs (engage →
  attack no longer wipes the stance); (4) @static_unload atop CombatExecutor; (5)
  AbilityDB.validate_refs reports zone statuses without authored defaults (doctored "dot"
  zone pinned; shipped data clean); (6) cast_started telegraphs the EFFECTIVE
  frenzy-compressed windup (0.45 → 0.225 pinned — reflex windows key on the real strike
  moment); (LOW) cross-room targets never aim a cast (wrong-space; default-axis fallback,
  pinned); interrupted-cast-burns-cooldown pinned as designed;
  zone-statuses-bypass-i-frames documented as intended in CombatZone. Judgment calls:
  transform-class abilities are NEVER a tactical pick (§0: the reveal is never an engine
  rule — the first sim run had the deterministic brain unmasking Kell at full hp from range;
  now only reflex data / the LLM / a GM directive casts one, pinned under every mask);
  ally-ness without factions = "anyone but my current target" for ally_downed; "dot" never
  registers as a last-attacker threat; a reflex cast with no target still casts on the
  default axis; reviewer's remaining gap list (simultaneous mutual stagger race, zone+dot
  interaction) not added tonight — noted for M8. Pre-existing ObjectDB-leak warning at exit
  unchanged (benign, tracked).
- 0x:xx — M4 (intent integration) BUILT, TDD red (Python 16 new fails; GDScript blocks written
  first) → green: suite 1440 → 1512 (+72 asserts across 6 new blocks); Python 52 → 75 brain
  (+23) / 26 vectors / 8 converse / 13 narrate all green; combat_sim exit 0 (untouched
  scenarios). BRAIN: build_decide_prompt gains a COMBAT SITUATION section (facts only — the
  neutrality principle pinned by an anti-imperative assert: no "you should/must"): "COMBAT: you
  are in a fight." + "Engaged by: <last_attacker>." + "Your standing intent: engage player
  (aggressive), set 2 beats ago." (protect/disengage phrasings pinned; intent-less fights say
  "You hold no standing combat intent." — a fact, not a nudge) + "Also in the fight nearby:"
  (only nearby entries with the new public in_combat flag; hp_band/doing reused) + "Your arts:"
  own-kit facts (id + class + the AUTHORED abilities.json `description` — new field on all 8
  abilities; assume_form's text is neutral-but-known: "let the worn shape fall away and become
  the monstrous thing beneath it"). Verb menu: MENU_EXCLUDE hides cast_ability from every
  LLM-facing menu (dict + list forms, decide AND converse); combat verbs get neutral guidance
  lines ("engage: commit to fighting a target; style is one of aggressive|…") rendered only for
  verbs the menu offers. PERCEPTION: build_snapshot forwards in_combat/combat_form/
  combat_intent(full own detail)/last_attacker(executor static ledger, in-combat only — the
  stale-ledger leak is pinned)/kit(_kit_summary from AbilityDB via /root); decide_request
  forwards the bool always, the detail only in combat (lean legacy shape pinned), computes
  combat_intent.set_beats_ago from the beat clock; _nearby entries gain in_combat (public like
  `doing`). AMBIENT LADDER: in_combat short-circuits _decide — task-bearers AND kit-bearers
  engage {last_attacker || nearest standing visible combatant || nearest standing anyone}
  aggressive (downed never a threat); true civilians (no task, empty kit) and threatless
  fighters disengage; schema verbs through the normal pipeline, pure function of the snapshot.
  GM DIGEST: combat_started/"entered a fight", combat_ended/"left the fight", transformed/
  "became something else" (form id never leaks — pinned), ability_cast_started aggregated to
  one "N combat arts loosed." line (finished/interrupted uncounted), agent_downed phrasing
  verified; stats gain combat/casts. COORDINATOR: in_combat members get no focus and no pass-2
  allocation, but pass 1 still CLAIMS what a fighter carries (in their pack = unfetchable;
  reallocating it would publish a false fact) — all_claimed unaffected, pinned. GM/DIRECTOR
  CORRUPTION PATH: action_schema.json + "cast_ability": ["ability"] (parity holds — one shared
  file); ActionCommit._cast_ability enters combat when needed (the GM-forced case) then casts
  on the live executor or PARKS on the new ephemeral Agent.pending_cast (never persisted;
  cleared on downing + exit_combat) which CombatExecutor.step_combat consumes on its own clock
  with the reflex retry contract (busy/stunned retry, other refusals drop); cast_ability spared
  from the stance-wipe like attack; Critic vetoes PROPOSED cast_ability outside combat
  (directives bypass the Critic by design — schema only, verified); Overseer gains
  CORRUPTION_TRANSFORM_THRESHOLD=85 + check_corruption_transforms(agents, corruption) swept on
  every world_var_changed{var:corruption} — directs cast_ability(assume_form) at agents whose
  worn combat_form still holds a transform art into a DIFFERENT form, once per agent
  (latch persisted in to_dict/from_dict, cleared by reset()); full chain pinned headless:
  corruption 80→90 → directive → run_beat commits → combat_started + parked cast → executor
  binds → telegraph → transformed exactly once → bieber_monster kit live. Judgment calls:
  "Engaged by" is sourced from the executor hit ledger (cheaply reachable via the
  CombatExecutor static; the same fact also reaches short_memory as Stimulus prose — both ride);
  the spec's "(armed)" qualifier dropped (no data source for armedness — facts only); with
  today's npcs.json bram_kell wears bieber_monster directly, so the corruption sweep skips him
  until M6 rebinds him to butcher_human ("not transformed yet" reads "kit transforms into a
  form not worn"); kit-bearing TASKLESS agents engage too (a body with arts defends itself —
  only the true civilian flees); a fighter with nobody visible disengages (nothing to engage is
  a fact). LIVE validation deliberately not run (coordinator's job post-merge).
- 0x:xx — M5 (player combat + HUD) BUILT in worktree wt/m5, TDD red (8 new fails + staged
  crashes) → green: suite 1440 → 1497 (+57 asserts across 8 new blocks); python 52/26/8/13
  untouched green; combat_sim exit 0 (19 asserts); real-scene headless boot clean (120 frames).
  Input: `attack` (mouse LMB + physical Space), `dash` (Shift), `use_charm` (Q) in
  project.godot [input]. New: src/PlayerCombat.gd (node "Combat" on Player.tscn) — binds ONE
  CombatExecutor (the SAME M2/M3 machinery, no parallel implementation) to the PLAYER PROXY
  agent + the player body; ALWAYS ARMED while the node lives (proxy stays exempt from the
  damage→combat-mode flip; combat-mode semantics are NPCs'); attack/dash/charm are
  try_cast("revolver_shot"/"dash"/"paper_charm") — telegraphs ride the same cast_started
  shape with caster "player". Aim = mouse direction from the player when a display exists,
  stored aim_fallback (refreshed by movement) headless. Costs: NEW cost_provider seam on
  CombatExecutor.try_cast (asked LAST in the refusal chain — a refused cost never burns the
  cooldown; paying deducts at accept, like the cooldown mark; null provider = free, so every
  NPC executor is byte-identical); PlayerCombat is the player's provider: revolver pays
  `ammo` (player-only pool, starts 12, stored as proxy metadata so it survives per-room
  Player re-instancing and resets with the proxy on restart; reload NOT tonight; refusal
  "no_ammo"), dash pays `stamina` 25 from Player.gd's EXISTING sprint pool (refusal
  "no_stamina"); unknown cost keys (paper_charm's spirituality) stay unenforced — M5 scope.
  Body-vs-data authority: the walk keeps the body authoritative — PlayerCombat mirrors
  body→proxy.position each physics frame THEN steps the executor (its own physics callback
  disabled), so _sync_body is a no-op unless a dash/knockback really moved the body.
  Pinned: dash i-frames zero a live NPC revolver round routed through the proxy's executor
  (no agent_attacked); charm zone slows + SILENCES an NPC standing in the glyph (its windup
  refuses "silenced"); a lethal NPC cleaver downs the proxy through the same take_damage
  pipes → agent_downed{player} once → EndGame player_downed fires and LATCHES; a cost refusal
  burns neither pool nor cooldown; ammo never negative. HUD: new ui/CombatHUD.tscn +
  src/CombatHUD.gd instanced INSIDE the persistent ui/HUD.tscn (Main + StandaloneBoot both
  get it) — hp bar bound to proxy hp (per-frame poll + immediate refresh on agent_attacked
  target=player; heals have no event), ammo counter + dash/charm cooldown pips off
  PlayerCombat (cooldown_frac over the executor ledger), stamina bar off Player.gd's pool,
  and the enemy cast-telegraph indicator: ability_cast_started shown ONLY when
  Perception.can_perceive(proxy, caster.room, caster.position) — out-of-room and
  beyond-vision casts show NOTHING (pinned); clears on cast_finished/interrupted (+ wall-
  clock UI net); the player's own casts never alarm it. Executor fixes en route: hurtbox
  attach is deferred when the body is still mid-scene-setup (the M5 bind path hard-failed
  add_child and leaked Area2D RIDs; NPC path stays synchronous via is_node_ready, and a
  never-attached hurtbox is freed at PREDELETE); _attach_hurtbox is re-bind-idempotent.
  SHARED-FILE EDITS for the merge coordinator: data/abilities.json — dash `cost.stamina`
  20 → 25 ONLY (player-kit entry, per the M5 spec "dash costs 25"; no other ability field
  touched — NPC ability descriptions left alone); project.godot [input] +3 actions;
  ui/HUD.tscn +1 instanced child (CombatHUD, drawn under the modals); scenes/Player.tscn
  +Combat node; CombatExecutor.gd +cost seam +hurtbox-attach fix (additive; M2/M3 sims
  byte-identical — combat_sim re-verified exit 0). Judgment calls: dialogue holds the
  player's hands (input path only — direct handler calls in tests bypass); slow/stun on the
  player gate casts/executor motions but NOT Player.gd's walk (noted M5 limit); ammo-on-
  proxy-metadata chosen over a static/autoload so room swaps keep the pool and restarts
  reset it; player combat_form set to "player" (the authored kit; no reflex rows, no
  tactics — the player pilots). No LLM spend this milestone (ledger unchanged).
- 02:1x — INTERIOR ART track COMPLETE: 7 painted top-down interiors generated (gpt-image-2,
  /v1/images/edits, 1536x1024 high, each call anchored on 2 existing tingen/assets/backgrounds
  interiors as style refs; BG_TOPDOWN prompt skeleton from generate_tingen_image2.py), ALL
  passed QA on attempt 1 (style match vs anchors, flat 90° top-down, no lettering, bottom-center
  entrance readable on every room): laughing_eel_tavern (bar top wall, hearth left, stairs right),
  warehouse_inner (VAST cold open floor for the ~3x scene scale, cargo door bottom-center +
  side door left wall ~43% down, skylight shafts), police_station_inner (front desk left, barred
  cell door top wall, blank notice board right), selena_almshouse_inner (cot rows, center-aisle
  lamps, crescent-moon chapel niche top-left matching cathedral iconography), mr_frankys_inner
  (runner carpet to bottom door, stairs right, blank-letter mail rack), butcher_shop_inner
  (counter mid, hook-rails top, back door ajar top-center with cold light — M6 seam),
  klein_living_room (same-home palette as klein_room, top door to study). Workspace
  asset-gen/out_image2/interiors/ (driver gen_interiors.py, per-attempt meta, QA crops,
  _sheet_interiors.png contact sheet); finals copied to tingen/assets/backgrounds/<name>.png
  (new files only) and godot --headless --import clean (all 7 .import present).
- 02:1x — interior-art spend: 7 images (7 interiors × 1 attempt) gpt-image-2 1536x1024 high
  @ ~$0.25 ≈ $1.75 (interiors budget 7/30; image-1 price parity assumed — exact image-2 rate
  unpublished in-repo)
- 02:2x — M4 LIVE GATE PASSED (Sonnet, ~$2 across two runs): engage {player, aggressive} at BEAT 0
  after a real executor-cast revolver hit; style legal; cast_ability never proposed; ambient
  fallback kept engaging after the sidecar was killed mid-fight. Prompt content verified direct:
  COMBAT block/condition/arts/engaged-by/standing-intent all render; cast_ability absent from
  menus; no imperatives. Two harness bugs found+fixed (dt seconds-vs-ms tunneled the projectile;
  failed assert hung the tree). NOTE for M6: engaged LLM still emits legacy `attack` each beat —
  redundant beat-level damage alongside the executor; needs a Critic amend or menu gating.
- 02:2x — INTERIOR ART: all 7 interiors landed first-try (~$1.75), door seams documented per item.
- 02:4x — M9 (Yumina back-port spec + language-neutral vectors) BUILT, mirroring the cognition
  SPEC.md/test_vectors.json/run_vectors.py parity pattern. New: agent-sidecar/cognition/
  COMBAT_SPEC.md (the contract both the GDScript stack and Yumina's TS port must implement:
  §1 layer stack — intent verbs/styles incl. orders+styles semantics and the style/mode
  precedence chains; tactical band derivation from kit DATA + the STYLES mask table + the one
  ranked selector; reflex trigger/action vocabulary, 150/800 delay clamps, max_fires,
  perceiver gating; resolver semantics; §2 ability schema field table + exact field-parity map
  vs Yumina packages/engine/src/combat/types.ts — cast_time(s)<->castTimeMs, cooldown<->
  cooldownMs, point<->area, px-vs-tiles units, buff mult-vs-delta semantic gap, what Yumina
  lacks (class/poise/knockback/projectile/motion/i_frames/zone/transform/status-magnitude)
  and has extra (name/iconUrl/vfx/sfx/damageMode/heal); §3 telegraph + combat lifecycle event
  names/payloads; §4 determinism rules; §5 explicit non-goals — no world pause, no deletion,
  coach=future, no auto-reveal, no RNG; §8 Porting-to-Yumina keep/replace/add checklist with
  where the vectors slot into their vitest CI) + agent-sidecar/cognition/combat_test_vectors.json
  (79 vectors + 16 pinned-constant checks = 95 assertions: resolver_apply 21 — damage through
  shields, i-frame whole-hit zeroing incl. the ==window edge, knockback normalization incl. an
  irrational diagonal, status defaults/overrides/unknown-name inertness, dot tick defaults,
  buff->frenzy, transform/zone report-only, hp floor, 0.0005s->1ms rounding canary;
  resolver_chain 3 — poise accumulate->stagger->reset incl. the >= exact-threshold and an
  i-framed hit contributing nothing; resolver_sequence 6 — stronger-wins stacking + refresh,
  half-open activity windows, dot accumulation with the tick-at-expiry-counts pin and
  refresh-preserves-bookkeeping, prune edges; resolver_ledger 2 — ready/mark edges + the
  interrupt-burns-cooldown pin; reflex 19 — every trigger kind fires AND doesn't, at_me
  discrimination, both-keys telegraph rows, hp_below strict <, clamp edges 149/150/800/801 +
  absent->250, max_fires at/below cap + 0=unlimited, multi-due rule order, unknown-kind
  inertness; tactical_bands 6 + band_of 5 + choose 17 — band derivation fallbacks, inclusive
  edges, the four-style fixed-scenario pin, range/cooldown fall-through, retreat_hp edges,
  counter window, id-ascending tie-break, transform-never-picked, reposition-movement never a
  cast, self-target any-distance). EVERY expected value machine-generated by RUNNING the
  GDScript implementation: tests/dump_combat_vectors.gd fills them through the SAME fill_*
  statics the verifier compares with (dump/verify can never drift); fixtures embed their own
  vx_-prefixed abilities/kits — zero reads of data/*.json, so M6's data edits can't break them.
  Runner: tingen/tests/run_combat_vectors.gd (SceneTree -s, prints `=== N passed, M failed ===`,
  exits nonzero) + registered in run_tests.gd as _test_combat_vectors (counts fold in — CI
  equivalence). PINNED spec decisions surfaced while vectoring (now normative): half-away-
  from-zero rounding for every s->ms boundary (GDScript round() vs JS Math.round diverge on
  negative halves — port formula given); dot ticks land up to AND INCLUDING the expiry instant
  while status activity is half-open [applied, applied+duration) — deliberate asymmetry;
  shields never sum (same-kind merge keeps ONE pool at the stronger magnitude — the
  "strongest pool pays first" comment in CombatResolver.gd is unreachable via the public API);
  apply_ability never prunes expired statuses (only absorbed-empty shields; tick_statuses
  prunes); i-frames strict (now < until) and zero the WHOLE hit including zone/transform
  REPORTS; cooldown marks at cast ACCEPT with no refund op (interrupt-burn intended);
  damage_dealt reports the post-shield hit, never overkill-clamped; the resolver never reads
  caster state (no caster-stat scaling; frenzy compresses executor windup only); tick_statuses
  never touches hp; JSON string-keyed fired_counts re-key to int rule indices at the binding.
  VERIFY: run_combat_vectors 95/0 standalone; full suite 1668/0/0 (includes the folded 95 +
  summary assert); python 75/26/8/13 all green. NOTE (coordination): two mid-window suite
  snapshots showed transient fails — first 40 (npcs.json/clues.json/deeds.json being written
  at 02:33-02:34 mid-run), then 2 (M6's bram_kell combat_form rebind bieber_monster->
  butcher_human landing before its run_tests assert update at 02:41) — both the M6 agent's
  in-flight shared-file churn, zero overlap with M9 files; final re-run fully green after
  their assert fix landed. No LLM spend (ledger unchanged).
- 02:5x — M6 (the Kell vertical slice) BUILT in the main tree, all suites green: GDScript 1726
  (was 1569; +~60 M6 asserts, remainder the M9 agent's parallel additions) / combat_sim 33
  (19 -> +14, new Scenario D) / python 75/26/8/13 untouched / headless City boot clean with the
  new autoload. REBIND: npcs.json bram_kell combat_form bieber_monster -> butcher_human (he
  WEARS the man; the monster is assume_form's target) — hydration test updated, corruption
  sweep test extended: the REAL bram_kell def is now directed cast_ability(assume_form) by the
  85-threshold sweep (before the rebind it skipped him as already-transformed). NIGHT DEED:
  new data/deeds.json + generic DeedRunner autoload (project.godot; SaveManager +"deeds"
  section — the once-per-day latch persists). Deed rows are pure data {agent, phases, room,
  waypoint, radius, fact_line, clue}: bram_kell gains a late-night schedule waypoint
  [4230,2050] on the canal's west bank (verified clear of every live-scene collider by the
  placement suite) — his OWN schedule walk carries him there; a late-night minute tick on the
  spot emits deed_performed {line} which Stimulus fans through the ONE vision gate ("Kell
  drags something heavy toward the canal." — keen witness remembers, dim/out-of-room see
  nothing), the watching PROXY earns clue bram_kell_suspicious (new clues.json row; _fan_room
  skips the proxy, the clue IS its witness channel), GMDigest carries the authored line
  verbatim. CONSEQUENCES: deeds.json consequence rows (agent+on+optional form) consumed by the
  same runner — transformed{bram_kell, bieber_monster} -> attention +8 / panic +5 + clue
  bram_kell_revealed IF Perception.can_perceive(proxy, kell) (sight-gated); agent_downed while
  WEARING bieber_monster -> attention +4 + clue confirmed sight-free (form-gated: downing the
  still-human butcher reveals nothing — judgment call, the spec's bare "downed: clue
  confirmed" would leak the reveal from a shopkeeper brawl); Stimulus gains a GENERIC
  transformed fan "<Name>'s flesh splits — something else stands in their skin." (any agent,
  never the form id; "their" not "his" — neutral engine, prose names ride data only);
  player-downed path verified already pinned (M5 executor-kill -> EndGame latch test). CRITIC
  AMEND (the M4 live-gate note): attack proposed by an in_combat agent WITH a live executor is
  AMENDED to engage {target} — standing style + thought preserved, set_at_beat refreshed on
  commit, zero beat damage; in combat without an executor (or out of combat) attack stands
  (only damage channel). Runtime amend branch (agent_action_amended) now exercised for the
  first time. ANIM first pass: CombatExecutor._play_anim implemented — Sprite2D bodies swap in
  the worn form's 8-frame strips (assets/anim/<form>_{attack_side,hurt_down,death_down}.png;
  bieber strips copied from asset-gen + imported), frames advance on the EXECUTOR clock
  (_step_strip; runs in the downed branch too so death finishes), finished strips restore the
  captured resting look, death HOLDS frame 7; hurt/death cues fire in receive_hit; the
  transform swaps the body sprite to assets/enemies/<form>.png (bieber_monster.png copied) and
  REBASES so later strips restore to the monster, never the shed skin; AnimatedSprite2D bodies
  (player klein rig) get a has_animation-gated play() nudge only. Everything defensive: no
  body / no sprite / no authored strip = silent no-op — the sims bind no bodies and stayed
  byte-identical. SCENARIO D (combat_sim, the §0 script offline): REAL bram_kell struck at
  23:30 by a player-bot on the PROXY's executor -> first hit flips combat MODE (executor binds
  only then, NPC-seam mirrored) -> fights human-form (1 cast pre-transform) -> dodge reflex
  eats telegraphs (10 shots, 4 landed) -> hp_below(0.5) casts assume_form at hp 48 ->
  transformed once -> monster downed at 27.7s (20-90 window) -> attention 10->22, panic
  10->15, clue granted via proxy sight, canal-deed clue correctly NOT granted, world clock +27
  game minutes DURING the fight (auto_run off for the scripted loop — beats stay out; judgment
  call), telegraphs preceded all damage, two runs byte-identical (67-line transcripts).
  Judgment calls: deed latch is once-per-DAY (a nightly errand, re-arms at the day roll);
  consequence rows carry no latch (transformed cannot repeat per agent+form by executor rule;
  a repeat downing genuinely re-alarms); proxy hp staged 2000 in D (the monster lands real
  cleaver work while dying — player_downed has its own M5-pinned path and must not end the
  harness). Files: data/npcs.json, data/clues.json, data/deeds.json (new), src/DeedRunner.gd
  (new), src/Stimulus.gd, src/Critic.gd, src/CombatExecutor.gd, src/GMDigest.gd,
  src/SaveManager.gd, project.godot, tests/run_tests.gd, tests/combat_sim.gd,
  assets/anim/bieber_monster_*.png + assets/enemies/bieber_monster.png (copies). No LLM spend
  this milestone (ledger unchanged).

## 03:5x — Final arc review: SHIP-WITH-FIXES, all 9 findings landed
- Adversarial whole-arc review (fresh-context reviewer over M0-M9 + plan §0) returned
  SHIP-WITH-FIXES: zero criticals, 9 findings. All fixed this entry:
  (1) offline hit-and-run freeze — AmbientSidecar._threat_for now accepts last_attacker only
  while VISIBLE (present in snap.nearby), else the ladder falls through to disengage-when-alone;
  (2a) bieber_monster's hp_below->assume_form self-cast row deleted (data);
  (2b) durable executor guard — a reflex transform into the WORN form is consumed unfired;
  (3) bram_kell vision_r: 600 authored (was silently defaulting);
  (4) Scenario D human_casts filter excludes assume_form (test was masking 2a);
  (5) legacy /propose strips combat_form + combat_intent alongside secrets;
  (6) dodge assert tightened to >=3 evaded of >=5 shots;
  (7) this sentence — the §0 acceptance script is verified PIECEWISE, not in one sitting: the
  full fight arc offline-deterministically (combat_sim Scenario D, byte-identical reruns), the
  LLM intent layer live against real Sonnet (live_combat gate + 7/7 prompt probes), and every
  seam in between by the 1726-check suite + 95 language-neutral vectors. A single continuous
  live playthrough of the Butcher script remains on the morning list — it exercises composition,
  not new surface;
  (8) COMBAT_SPEC.md §8.1 state-lifetime/persistence table (what a port must persist vs rebuild);
  regression tests pin 1, 2a, and 2b (ambient ladder hit-and-run cases; transform-reflex-guard
  test: self-cast consumed unfired, butcher escape hatch still fires).

## 04:4x — LIVE ACCEPTANCE RUN PASSED: the §0 Butcher script, end to end, real LLM (11/11)
- tests/live_butcher.gd (new; live-gate conventions, ~$2/run): Scenario D's staging with the
  scripted intent rail replaced by the REAL sidecar. Sonnet committed engage {player, aggressive}
  at beat 1 after the opening revolver hit; no cast_ability leaked; the hp_below(0.5) reflex cast
  assume_form at hp 48; the monster downed at 27.5s (20-90 GDD window); bram_kell_revealed
  granted via proxy sight; attention 10->22, panic 10->15; clock +27 game-minutes during the
  fight. Two runs (one with a harness capture bug — GDScript lambdas copy primitives; Dictionary
  capture like combat_sim's tf fixed it), identical world behavior across both.
- Observed nuance (in design, worth eyes): the form swap clears combat_intent, and the LLM
  proposed idle for 2 beats post-transform while the monster fought on the tactical layer's
  default posture, re-engaging at beat 5. Default posture covered the gap exactly as specced
  (M3); if the idle beats ever read as passive, the perception combat block could surface
  "you just transformed" more loudly.
- City density fill (task #31) COMPLETE by the fill agent: 13/14 blocks placed (fill_14 dropped
  as an unfaithful top-edge crop), 2 QA rounds, new _trim_oversize.py stage kills neighbour-block
  bleed in image-2 cutouts, suite 1798/0/0 after import. Spend: 28 images ~= $7 (running ledger
  ~= $35 of $100). Composite verified by eye against map_v3: dense like the reference; bare lots
  are the 4 waypoint-protected blocks + slivers.

## 05:1x — AMMO -> WEAPON/TOOL ITEMS (user directive: no built-in ammo variable)
- The `ammo` cost key no longer pays from PlayerCombat's built-in pool (REVOLVER_START_AMMO /
  AMMO_META proxy metadata — both DELETED). It resolves through the item system: items.json
  gains `revolver` (category "weapon", grants ["revolver_shot"], ammo_item "revolver_round")
  and `revolver_round` (category "ammo"); ItemDef carries grants/ammo_item (shape-guarded);
  ItemDB.weapon_for_ability(agent, ability_id) finds the CARRIED granting weapon (inventory
  count > 0, stable id order — agent-generic, so a future NPC cost provider resolves the same
  way). PlayerCombat.try_pay keeps the check-all-then-deduct-all seam: no carried granting
  weapon -> "no_weapon", too few rounds -> "no_ammo", else remove_item(ammo_item, cost) from
  the proxy's per-agent inventory.
- Starting loadout is DATA: scenario.json "player_loadout" {revolver: 1, revolver_round: 12},
  granted ONCE where Agents.ensure_player_proxy CREATES the proxy (headless harnesses get it
  too); re-ensuring never re-grants, a run restart (rebuild) re-arms. Sane built-in fallback
  when the file/key is absent. CombatHUD's counter reads PlayerCombat.ammo_count() (kit's
  ammo-costing art -> carried weapon -> ammo_item count), "—" when no weapon carried.
- COMBAT_SPEC.md §2 cost row + §8 keep-list note the item resolution (Yumina's id→count
  inventory is already the right shape). TDD red->green: 17 new/updated asserts watched
  failing first. Suite 1861/10 failed — all 10 are the interior-scenes workstream's City
  door/collider asserts, failing identically BEFORE this change; combat_sim 33/0; vectors 95/0.
- Review hardening (verdict SHIP, low findings applied): ammo_count returns -1 (HUD "—") for a
  carried weapon authoring no ammo_item instead of item_count("")==0 (watched red first);
  weapon_for_ability duck-guards agents without item_count (was a SCRIPT ERROR spew, now {});
  cross-resource no-half-pay pinned (ammo affordable + stamina refuses -> rounds untouched).
  4 new asserts. Suite 1865/10 (same 10 interiors asserts); combat_sim 33/0; vectors 95/0.

## 11:5x — INTERIOR WIRING: 7 painted rooms playable — layered Klein house, scale-aware grounds

- All 7 painted interiors are now first-class rooms: scene + RoomGraph id + TWO-WAY portal
  pair + walls/furniture-blob colliders (rects verified by overlay renders against the art)
  + a city-side door Area2D (Portal.gd, shared "door" shape) on the building's street edge.
  Interior exits are walk-in Portal areas standing in the painted door mouths (wall gap +
  area just past the threshold), at the SAME coordinate the data agents cross via
  ActionCommit — one doorway for player and cult. Scale-aware world extents come from the
  background sprite scale (1536x1024 art), never a stretched box: the warehouse floor is
  3.0x Klein's rooms linear; tavern/police/butcher mid; almshouse/Franky's modest.

  | room id | scene | world size | city door (world) | portal pair from_pos -> to_pos (in) / (out) |
  |---|---|---|---|---|
  | klein_living_room | KleinLivingRoom.tscn | 896x597 | KleinHouse/KleinHouseDoor (3070, 2655) | (3070,2655)->(448,520) / (448,627)->(3070,2655) |
  | klein_room (bedroom, existing IntroRoom.tscn) | IntroRoom.tscn | 896x597 | — via parlor only | parlor (430,-30)->(760,400) / bedroom E-door (845,400)->(430,60) |
  | butcher_shop_inner | ButcherShopInner.tscn | 1306x870 | IronCrossMarket/ButcherShopDoor (3590, 3650) | (3590,3650)->(653,780) / (653,900)->(3590,3650) |
  | laughing_eel_tavern | LaughingEelTavern.tscn | 1536x1024 | LaughingEel/TavernDoor (2157.5, 4170.5) | (2157.5,4170.5)->(783,920) / (783,1054)->(2157.5,4170.5) |
  | police_station_inner | PoliceStationInner.tscn | 1459x973 | PoliceStation/StationDoor (3885, 4735) | (3885,4735)->(700,870) / (700,1003)->(3885,4735) |
  | selena_almshouse_inner | SelenaAlmshouseInner.tscn | 1152x768 | SelenaAlmshouse/AlmshouseDoor (4260, 1831.75) | (4260,1831.75)->(570,680) / (576,798)->(4260,1831.75) |
  | mr_frankys_inner | MrFrankysInner.tscn | 1075x717 (painted room inset ~610x620) | MrFrankys/FrankysDoor (4735, 3645) | (4735,3645)->(511,580) / (511,693)->(4735,3645) |
  | warehouse_inner | WarehouseInner.tscn | 2688x1792 (VAST, player-follow cam) | Warehouse/WarehouseDoor (5129.6, 2321.8) | (5129.6,2321.8)->(1350,1640) / cargo (1398,1822)->(5129.6,2321.8) |

- LAYERED Klein house (per design): city -> klein_living_room (parlor) -> klein_room (the
  existing IntroRoom bedroom). KleinHouseDoor retargeted to the parlor; the bedroom's E-door
  now opens into the parlor (test_intro_room pin updated deliberately); NO direct city ->
  bedroom edge (next_hop both ways passes through the parlor). Chapel -> crypt untouched
  (from_pos (2172,5284) pinned in the new tests).
- TDD: tests/test_interiors.gd (per-scene wiring + RoomGraph round trips through the real
  ActionCommit crossing code + scale asserts + door-mouth clearance sampling) and
  run_tests.gd::_test_interior_rooms (graph edges, per-room data round trips, exit/graph
  agreement, city doors at the exact from_pos + not buried in any building collider) were
  written FIRST and watched fail 54+1+10 red; wired until green. run_tests' interiors
  function was swept into cc4e2e2 by the ammo refactor commit (it ran 1865/10 there);
  the 10 red flipped green with the door landing. Suite NOW: 1895 passed, 0 failed, 0
  skipped; test_interiors 130/0; intro 11/0; neil 25/0; hq 13/0; archive 19/0; anywhere 4/0.
- Judgment calls: (1) no butcher building exists in City.tscn — Kell's shop door sits on the
  Iron Cross Market's EAST face (3590,3650), street-side by his stall waypoints (3620-3640,
  3430-3460) but 70px+ clear of them so talking to Kell can't teleport the player. (2) the
  warehouse city door sits WEST of the RiteCache on the south face (-200,385 local) so the
  cache interactable's approach never crosses the portal; the painted west side door is wired
  in-scene as a second player exit to the City while the graph carries the one canonical
  cargo pair. (3) tavern stairs + police cell + butcher back door (M6 seam) painted but not
  wired — solid colliders/wall for now. (4) IntroRoom's IntroCard replays on re-entry via the
  parlor — same behavior as the nave's establishing shot on every chapel entry (precedent;
  left alone). (5) restored the fill-churn-removed KleinHouse block verbatim from HEAD (its
  door pin (3070,2655) is suite-load-bearing) and reverted RowhouseA's half-moved sprite/body
  to HEAD geometry (was failing footprint coverage at 27.5%); RaphaelCemetery stays removed —
  the deferred fill-placement session owns re-placing it (suite carries no pin on it).

## (Fable, low-credit) — CITY FILL: un-slice recut, legal re-placement
- User: "many buildings are either not at the right position, or they are cut off and not full."
  Root cause (confirmed by the 14-judge diagnosis): _trim_oversize.py's PAD=8 sliced Victorian
  rooflines that overhang the painted footprint bbox — 9 of 14 blocks had hard straight cuts
  through roofs/walls. Fix: per-block PAD_OVERRIDE (40-60 map px) so cuts land in open street;
  recut from keyed/orig (idempotent) -> re-place (fresh NCC on the FULLER sprites) -> apply.
  fill_11 went from a 416x389 courtyard-only slice to the full 717x849 rowhouse ring; fill_03/
  05/08/09/12 no longer sliced.
- Legality: the fuller colliders overlapped 4 NPC waypoints (the sliced ones had been small
  enough to fit beside them). Nudged fill_02 (-50x, clears constable_brom night), fill_13 (-15x,
  clears lamplighter_orin morning), fill_12 (+150x, toward its true painted lot AND clears
  bram_kell). Dropped fill_03 (match score 0.387, sat squarely on bram_kell's late-night canal
  path — needs hand-placement) and fill_14 (unfaithful crop, needs regeneration). 12 FillBlock
  bodies now, all placements-legal.
- Suite 1890/0/0 after --import. Composite reads dense and buildings are full clusters.
- STILL OPEN (next session, docs/handoff/DESIGN_fill_rework.md + fill_diagnosis_verdicts.json):
  regenerate fill_06 (source 2x too tall), fill_10, fill_14; hand-place fill_03; fine-tune the
  low-confidence positions (fill_07 score 0.31, fill_10 0.22, fill_13 0.28). These need the
  OpenAI image budget and/or a visual tweak loop.

---

# Run Log — v2 roguelite sprints (2026-07-03 → 2026-07-12)

## 2026-07-03 — v2 pivot + first playable slice
- Combat engine landed through the M1–M9 arc (resolver, executor, tactics/reflexes, LLM intent, player combat + HUD, Kell vertical slice, spec vectors).
- **Design pivot committed:** occult-noir action-RPG **roguelite** (v2) — investigation dropped; four push-your-luck meters; rumors→leads; Sequence advancement.
- Slice sprints M1–M11: combat VFX, boot/run shell, dialogue de-freeze, meters + 60s rampage, progression spine, leads, Ritual Night + endings, GM opening, gameplay-test pass, polish, meter teeth. Tag: `playable-slice-v1`.

## 2026-07-04 — M12
- Sable Wren, 2nd adversary (Hunter-pathway prey). Suite 2093/0/0.

## 2026-07-11 — M13–M15
- Ammo pickups + empty-gun feedback (dead-end closed); Leland Mack (Seq-8 meal, closes the 9→7 chain); Franky's shop (buy ammo / sell harvest — the coin loop). Suite 2181/0/0. Two Sonnet-builder REJECTs → all builders locked to Fable.

## 2026-07-12 — overnight autonomous sprint (M16–M35) + retro + patch waves
- **Art:** per-NPC/per-form sprite seams + occult UI theme (M16); full canon-Klein cast — 21 portraits + 8 monster forms (M17/17b; chibi style rejected → Klein concept-art anchor).
- **Fan-out research+playtest backlog:** 11 live bugs (B1–B11) + M18–M35. All 11 cleared by M20–M23 (city self-loss, unreachable progression, save loss, LLM spend, reseed, opener, ammo, ritual softlock, HUD dedup, converse redaction).
- M24–M27: combat juice; prayer/occult/events rewired to v2 meters; balance retune; meta-progression (codex + unlock + win-grade payout).
- **Hermit arc M28–M34:** 2nd playable pathway + old_neil + counter-rites; combat camera; LIVE reachability fix (pathway-pick + ledger_finch + lead gating — caught by fresh playtest, not the suite); spirituality pool (40/4 reserve); counter-rite usability; Hermit e2e + finch sim coverage; live star_brand primary + tension. M35: interactable glow + once-only hint framework. Suite 2196 → 2732/0/0.
- **24-agent retro review:** tip green/unpushed/no secrets, but 2 commits flagged NOT_GOOD (M28, M27 — headline features shipped live-unreachable), live blocker at HEAD (no ground-pickup for characteristics), test-integrity + hygiene findings. Experiential audit: **8/10 systems, 4/10 playable demo** (no audio, static enemies, broken bieber strips, 2.5× run length).
- **Patch wave 1 committed (`e50e56b`):** live characteristic harvest seam + cache stocking; dry-gunman fallback; earned-reveal wire. Suite 2777/0/0; sims byte-identical. Wave 2 in flight (meta isolation + codex UI ✓, hygiene + 138-PNG pass ✓, threat counterplay running, full-wave adversarial review pending).
- **Staged for the experiential wave:** 22 spectrogram-vetted CC0 SFX (Kenney + 4 synthesized) with manifest; all 9 anim strips alpha-keyed. Next: audio wiring, enemy tells, pacing (7 days ≈ 60 min + rest verb), staged opener, city dressing.

## 2026-07-13/14 — deadline sprint (overnight → Monday 3pm)
- **Experiential wave** (`9ae9929`): sound (22 CC0 SFX + ambience + live volume bus), combat readability (on-enemy tells, HP pips, muzzle flash, reticle, alpha-fixed mask-drop), ~60-min run pace + rest-until-morning, Brom staged at the door + 3-choice Harvest panel, day/night city (tint/lamps/crowds/map-pin). 20 probe screenshots eyeballed.
- **N1 sprint safety** (`2ef9afa`): TestSandbox user-dir isolation (sentinel-hash proof), 65-file harness registry, rot repaired. Suite fleet folded: 4228.
- **N2 death costs a day** (`e5e0068`): death → checkpoint wake ("Cut Down in the Dark"), inventory persists, Ritual Night fuse unbrickable, Restart sanity.
- **N5 Death pathway** (`5b07d43`): 3rd playable build (Corpse Collector line) via WIN_UNLOCK_CHAIN; sister_auber + brother_cassian two-phase prey (art placed); sims I/J; death_full_run joins the baselines. Suite 4512, sim 118.
- **Cast Roulette** (`1c574ed` + `574b7b2`): title-screen "The Cast" dossier panel — roulette carousel, monster flips; flipped to Full-Dossier default per user (all authored fields incl. goals/secrets/knowledge/schedule + real ability numbers; codex gating kept behind SHOW_ALL for a future player mode). Suite 4608/0/0.
- Assets staged: 4 monster attack strips (wren/mack/neil/beyond_hunter; finch rejected 3x), descended_avatar_true. Drafts for ccb: #92 reply, #108 notebook, action-layer sketch v2 (NPC-first, representation+propagation).
- HANDOFF QUEUE: N3 Continue-resume, N4 threats-visible (avatar art staged), N6 pass-1 asset touch-ups + strip placement, N7 Hunter loop closure, N8 LLM wins, N5 formal follow-up review (verdict text lost to harness quirk), roadmap fillers. See scratchpad NEXT_WORK_ROADMAP.md.

## 2026-07-15 — N3 Continue is a first-class resume
- **Reverified B-F1/B-F2/B-F5 against HEAD with a fresh two-process probe: 12 FAILs** — Continue loaded the world (clock/scene/pathway persisted) but left the SESSION dead: run_active false, day stuck at 1, no in-memory checkpoint, pause refused, codex ledger lost + recording dead, nightly checkpoints dead, Ritual Night could never arm, and a stale save survived every ending (ghost resume after a win).
- **Fixes:** (1) `run_manager` SESSION block (day / run_active / ritual latch / checkpoint_day / knowledge ledger) joins the shared SaveManager SUBSYSTEMS manifest — no checkpoint nesting: the disk save IS the nightly mirror, so (2) `RunManager.resume_from_save()` (invoked by the REAL `BootController.continue_run()` after a successful load) re-arms the live flag/pace/payoff-latch and REBUILDS the in-memory checkpoint from the loaded payload. (3) B-F5 staleness: `SaveManager.invalidate_save()` on every full run-end (win/lose/pre-checkpoint final death) — title Continue greys out; plus a payoff idempotence latch (an unlatched double `end_run` was double-paying currency AND double-walking the unlock chain). Riders: pathway-picker Cancel/Back button; authored codex copy for `pathway:hermit` + `ending:player_downed`.
- **Tests:** `tests/test_continue_resume.gd` (35 checks; watched RED 19 FAILs) folded in-suite + isolation fleet; `tests/continue_probe.sh` + `_s1/_s2.gd` = the registered TWO-PROCESS tool (s1 12/0, s2 19/0). Probe shots 37–39 (Continue enabled / resumed lodging day 2 / Ritual Night armed on the resumed run) eyeballed.
- Gates: suite 4652/0/0 · combat_sim 119/0 + run_combat_vectors 95/0 byte-identical vs clean-HEAD extraction · full_run 83/0 · hermit 42/0 · death 42/0 · boot clean · isolation proof PASS.

## 2026-07-15 — LAB PULL-INS WAVE (P1–P5, pattern ports from the lab's Penn-sim work)
- **P1 memory-importance ladder + `just_*` markers:** importance is written ON the memory row at write time (`Agent.remember_scored` → `{"text","importance"}` rows; Stimulus fan blocks author 1.0 ambient / 2.0 action-outcome / 8.0 pinned — a witnessed transform is pinned); `Perception._event_importance` demoted to the fallback scorer for unscored/legacy string rows. State flips (combat enter/exit, portal crossing) write one-shot `just_*` transition markers consumed by exactly ONE deliberation snapshot (AgentRuntime take → `perception.just_happened` → brain renders a one-beat "Just now:" line). `tests/test_mem_importance.gd` 25 checks; test_brain +2.
- **P2 affordances as data + verb curation (implements action-sketch v3 §5 / ports #446 REQUIRED_AFFORDANCES):** verbs declare `required_affordances` in `action_schema.json` (pray→altar, perform_ritual_step→rite_site; everything else universal); all 11 RoomGraph rooms carry the Thursday-vocabulary tags in `city_layout.json` `room_affordances` (bar/seat/altar/pew/crypt_stair/counter/shelf/cache/door/bed/desk/… + `rite_site`), tagged wherever the authored objects exist so ○-row verbs light up as they land in the schema; the snapshot forwards the current room's tags and the sidecar curates the LLM menu (universal verbs always offered) on /decide, /converse, and the legacy /propose prompt. INVARIANT kept verbatim: curation shrinks invalid PHRASINGS only — validate_action + ActionCommit gates unchanged and re-pinned. `tests/test_affordances.gd` 27 checks (§(e) pins the ⇔ FORWARD direction too: the `rite_site` tag set == the rooms where `_near_any_rite_site` can actually pass, both inclusions, against the real gate fn + real data rows) + 11 curation checks in `test_converse_route.py`.
- **P3 bounded decide + `deciding` lifecycle fact:** each launched /decide emits ONE typed `deciding {agent, phase: begin|end, beat}` EventBus fact, paired exactly once (ok/timeout/error/dropped); a hung responder never hangs an NPC (the beat completes on the ambient brain — proven against a real never-answering TCP listener) and the spent call still lands in the NEW per-NPC ledger (`SidecarBridge.note_agent_llm`, timeouts included). PlayLog renders the fact; the inspect card shows a live "( thinking… )" tell while a decide is in flight. `tests/test_deciding_fact.gd` 15 checks; probe `tests/probe_thinking_tell.gd` shots eyeballed (tell up mid-flight, thought restored after timeout).
- **P4 one bounded repair round (ports their is_error tool_result pattern):** an invalid LLM reply's exact validation error is fed back to the model ONCE (`brain._schema_error` + repair prompt); still invalid → the existing idle fallback; the decide result + usage record are stamped `valid|repaired|failed` and the sidecar bills BOTH calls' tokens. test_brain.py +6 checks (scripted mock client).
- **P5 repeat-failure freeze guard:** `ActionCommit.failure_key` classifies gate-refused commits; `AgentRuntime` counts consecutive IDENTICAL failures per agent and on the 3rd forces idle/replan, writes a PINNED informed-failure row (generalizing gather_item's contention fact), and emits `agent_stuck` for the GM; a different failure or any success resets. `tests/test_stuck_guard.gd` 18 checks; full_run/hermit/death byte-identical (normal play never trips it).
- Suite-side adaptation disclosed: run_tests' `_short_mem_has`/`_memory_mentions` now read rows via `Agent.mem_text` (scored rows are dicts — `String(dict)` renders no text; 13 stimulus-witness checks were red until the helpers learned the row shape).
- Gates: suite 4776/0/0 (was 4692) · combat_sim 119/0 + vectors 95/0 · full_run 83/0 / hermit 42/0 / death 42/0 · vs the clean-HEAD (1062308) git-archive extraction full_run's log is fully byte-identical; combat_sim/vectors/hermit/death logs are byte-identical in EVERY sim/assert line, with exactly ONE differing line — Godot's exit-time diagnostic `ERROR: N resources still in use at exit` (+1 each: combat_sim/hermit/death 16→17, vectors 15→16; Perception now statically pulls CityLayout into those harnesses' resource graph — engine exit noise, not sim output; determinism holds) · python: test_brain 83/0 (+8), run_vectors 26/0, narrate 13/0, converse 22/0 (+11) · isolation proof + continue probe PASS · thinking-tell probe shots eyeballed. NOT committed (per wave brief).
- **Review fix round (SHIP-WITH-FIXES applied):** (1) the four wave harnesses' STANDALONE entry paths are now gate-exercised — added to `run_tests.gd` STANDALONE_HARNESSES (fleet runs them as child processes) AND `tests/isolation_proof.sh`, plus a lasting registry pin (every fleet harness must appear in isolation_proof.sh; watched RED: 4× `FAIL isolation_proof.sh runs fleet harness test_*.gd standalone` before the .sh registration). (2) The byte-identical disclosure above amended with the exit-diagnostic exception (doc-only; no RED possible). (3) `test_affordances.gd` §(e) closes the ⇔ forward direction (mutation-RED both ways: stray tavern `rite_site` → `FAIL tagged room laughing_eel_tavern has a REAL rite site`; untagged city → `FAIL site room city carries the rite_site tag`; both reverted). Fix-round gates (all re-run): suite 4910/0/0 (was 4776: +7 §(e) in-suite, +85 fleet-child checks, +4 fleet wrappers, +34 registry-pin checks) · combat_sim 119/0 · vectors 95/0 · full_run 83/0 / hermit 42/0 / death 42/0 (byte-vs-clean-HEAD exactly as disclosed above; `agent_stuck`/`deciding` appear in NO e2e log) · boot_smoke 6/0 clean · isolation proof PASS (44/44 harnesses exit 0, incl. the four standalone entry paths) · continue probe PASS (s1=0, s2=0) · python 83/26/13/22 all 0 failed. Still NOT committed.
