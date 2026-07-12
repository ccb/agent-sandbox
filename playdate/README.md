# Playdate port -- M1 (mini-engine)

Layout:
- `Source/engine/core.lua` -- the playdate-free mini-engine (pure Lua 5.4:
  no playdate APIs, no `+=`): things/characters/locations with properties,
  aliases and ordered contents; the verb registry (look/examine/search/
  take/drop/inventory + travel); scope -> suggestions (the composer lanes);
  journal + (seed, journal) restore.
- `Source/content/slice.lua` -- the vertical slice (Wreck, Wagon's Hold,
  Tomb Exterior) ported from the Python tomb with the terse-text pass.
- `Source/main.lua` -- the device layer: transcript, the Composer
  (crank lane + per-pool recency recall), datastore autosave every turn,
  system menu (new game, free input via playdate.keyboard).
- `tests/engine_test.lua` -- the parity harness: `lua playdate/tests/engine_test.lua`
  (22 assertions: movement/aliases/blocks, hidden-until-search honesty,
  awards idempotence, take/drop/containers, replay-rebuilds-state).

Build:  `pdc -sdkpath ~/Developer/PlaydateSDK Source TombOfNassakAnRah.pdx`
Run:    open the .pdx with the Playdate Simulator, or sideload.

Controls: crank = word lane; left/right = EXITS/VERBS/NOUNS; A speaks
(an exit alone just goes); B unsays; up/down pages the transcript.
