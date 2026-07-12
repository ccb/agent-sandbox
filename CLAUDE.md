# CLAUDE.md — Tingen (read me first)

Occult-noir action-RPG roguelite (v2 pivot — north star: `tingen_game_direction_v2.md`):
Godot 4.6/GDScript game (`tingen/`) + Python LLM sidecar (`agent-sidecar/`). 21 LLM-driven
NPCs on schedules, four push-your-luck meters (Doom/Madness/Notice/Heat), rumors→leads→hunt
Beyonders→harvest Characteristic→acting deed→advance the Sequence (9→8→7), a nightly-checkpoint
~7-day/~60-min run, and deterministic two-layer combat under LLM intent. Two playable pathways
so far: Hunter (revolver/ammo) and Hermit (star/ritual, spirituality-gated), each with its own
adversaries; the canon "Tingen Six" pathways are the roadmap. Part of the Purm 2026 internship;
sibling project Yumina (TS) at `/Users/markma/Desktop/Yumina Master/yumina`.

**Start here**: `docs/handoff/HANDOFF.md` (state + protocols) → `RUNLOG.md` (journal) →
`docs/handoff/TODO_NEXT_AGENTS.md` (work queue).

## Commands

```
GODOT=/Applications/Godot.app/Contents/MacOS/Godot
$GODOT --headless --path tingen --import                          # after asset changes
$GODOT --headless --path tingen -s tests/run_tests.gd             # suite (baseline 2529/0/0 as of M30)
$GODOT --headless --path tingen -s tests/combat_sim.gd            # 71/0 deterministic fights
$GODOT --headless --path tingen -s tests/run_combat_vectors.gd    # 95/0 spec vectors
python3 agent-sidecar/cognition/test_brain.py                     # 75/0 (run as scripts, not pytest)
python3 agent-sidecar/cognition/run_vectors.py                    # 26/0
python3 agent-sidecar/test_narrate_route.py                       # 13/0
python3 agent-sidecar/test_converse_route.py                      # 8/0
# sidecar: cd agent-sidecar && python3 sidecar.py --env-file .env --port 8777
# play live: TINGEN_SIDECAR_URL=http://127.0.0.1:8777 $GODOT --path tingen
```

## Hard rules

- **Never push without explicit user approval.** ⚠️ The remote
  `github.com/MaEnqiMark/Tingen-Game` is **PUBLIC** and has **no LICENSE**; local `main` is 44+
  commits ahead of `origin/main`. Pushing publishes tonight's work to a public repo — get a
  clear yes first. Also subtree-synced into ccb/agent-sandbox `game/tingen`. Confirm before
  creating GitHub issues/PRs.
- **Never print API key values** (presence/length only). Keys: `agent-sidecar/.env`
  (ANTHROPIC_API_KEY), Yumina's `.env` (OPENAI_API_KEY, for image gen — main loop only,
  subagent permissions deny it). Pass via `--env-file`.
- **TDD, strictly**: failing assert watched red BEFORE implementation; milestone changes get a
  fresh-context adversarial review + fix round (docs/handoff/TESTING_WORKFLOW.md §5).
- **Engine neutrality**: facts not commands; no NPC-identity branches in engine code (content
  lives in `data/*.json`); secrets/combat_form/combat_intent never reach LLM /decide payloads;
  peer hp banded; transformation only via `assume_form` (NPC layers or GM directive); no
  locational damage; no RNG in combat; world never pauses; downed bodies never deleted.
- Spec/vector governance: change algorithm → regenerate fixtures via
  `tests/dump_combat_vectors.gd` (never hand-edit expecteds) → both runners green.
- `tests/run_tests.gd` is shared ground: Edit-tool string edits only, register new tests in the
  call list. `.tscn` files: one writer at a time.

## Gotchas that cost hours

- `step_combat(dt)` takes SECONDS (1.0/60.0). ms tunnels projectiles.
- GDScript lambdas capture primitives BY VALUE — use a Dictionary to mutate from a closure.
- `String.hash()` is djb2 (33≡1 mod 2^n) — md5 for mod-K partitioning.
- class_name scripts under the `-s` harness: autoloads via `/root` lookup (`_al` pattern);
  `@static_unload` when statics pin scripts.
- Restart the sidecar after editing brain.py (old code stays in memory).
- Harness asserts must `quit(1)` — a bare failed assert hangs the tree forever.
- gpt-image-2 rejects `input_fidelity`/`background=transparent` (image-1 params); cutouts keep
  neighbour content — trim + rematch (`asset-gen/out_image2/buildings/fill/_trim_oversize.py`).
