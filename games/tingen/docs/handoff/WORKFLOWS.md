# WORKFLOWS — reusable multi-agent orchestration patterns (tuned for Opus 4.8)

These are the orchestration shapes that actually worked this project, written as copy-paste
templates for the Claude-Code `Workflow` tool. Model notes: with Opus 4.8, omit per-agent
`model` (inherit the session model); keep `effort: 'high'` ONLY on adversarial-review and
synthesis stages; builders/judges run fine at default effort. Token budgets: a 3-stage
build/review/fix ≈ 250k tokens; a 14-judge visual fan-out ≈ 200k.

## Hard-won Workflow-tool gotchas (read before writing a script)

1. `args` passed to the tool did NOT reach one of our scripts (`args.blocks` undefined) —
   **hardcode config as consts at the top of the script**; it's also more reproducible.
2. Leftover/dead code in the script body throws at RUN time (`X is not defined`) — the script is
   executed top-to-bottom; delete scaffolding before launching.
3. `Date.now()` / `Math.random()` / argless `new Date()` THROW inside scripts (resume safety).
   Stamp timestamps after the workflow returns.
4. Every run persists its script to a file (path in the tool result). Iterate by EDITING that
   file + relaunching with `{scriptPath}`; add `resumeFromRunId` to reuse completed agents'
   cached results (same prompt+opts = cache hit — edit only what must change).
5. `parallel()` resolves failed/skipped agents to `null` — always `.filter(Boolean)`.
6. Agents that must read images: give EXACT absolute paths and read-order; put the judgment
   criteria and the output schema in the prompt (the `schema` opt forces validated JSON out).
7. Subagent permission walls: anything touching the OTHER repo's `.env`
   (`/Users/markma/Desktop/Yumina Master/yumina/.env`) gets DENIED for subagents — run
   image-generation / key-bearing commands from the main loop; fan out everything around them.
8. Two agents editing ONE file: allowed only with Edit-tool string edits in disjoint regions
   (run_tests.gd survived this twice); never let a subagent rewrite a shared file wholesale.
   Scene files (.tscn) get ONE writer at a time — coordinate with SendMessage holds/go-signals.

## 1. Review-re-edit milestone loop (the project's backbone)

Shape: sequential `phase('Build') → phase('Review') → phase('Fix')`, one agent each.
The full worked example (prompts included) is the `ammo-to-weapon-items` script — persisted at
the path in RUNLOG's 05:1x entry's workflow metadata; the essential skeleton:

```js
export const meta = { name: 'milestone-x', description: '...', phases: [
  { title: 'Build' }, { title: 'Review' }, { title: 'Fix' }] }
const BRIEF = `PROJECT/CURRENT STATE/TARGET DESIGN/TDD IS MANDATORY (strict red-green, watch
the red run)/VERIFY (exact commands + baselines)/CONSTRAINTS (files other workstreams own,
never commit, never print keys)`   // <- the quality lives HERE; be exhaustive
phase('Build')
const build = await agent(BRIEF + 'You are the BUILDER... report red-run evidence + suite lines',
  { label: 'build', effort: 'high' })
phase('Review')
const review = await agent(`Fresh-context ADVERSARIAL REVIEWER... brief: ${BRIEF} ...their
report: ${build} ... review the ACTUAL git diff, run the suites YOURSELF, hunt list: <the five
ways this specific change classically fails>. Verdict SHIP/SHIP-WITH-FIXES/REJECT + numbered
findings (severity, file:line, concrete fix)`, { label: 'review', effort: 'high' })
phase('Fix')
const fix = await agent(`FIXER... apply every major/critical + regression assert each...
${review}`, { label: 'fix' })
return { build, review, fix }
```

Rules that made it work: the reviewer gets the BRIEF **and** the builder's report but forms its
own view from the diff; the hunt list is change-specific (half-pay, re-grant, determinism, spec
drift, test theater — for the ammo change); the fixer may reject findings but must say why.
Main loop commits AFTER the workflow, scoped to the workstream's files.

## 2. Visual QA judge fan-out (any "does it look right" problem)

Used for the city-fill diagnosis (14 blocks). Generalizes to any set of visual units
(sprites, panels, rooms): build side-by-side evidence panels FIRST (reference left, actual
right, zoom + coordinate key in the title bar), then one judge per unit + one whole-picture
critic, all `schema`-forced:

```js
const VERDICT = { type: 'object', required: ['unit','verdict','severity','recommended_fix', ...],
  properties: { offset_map_px: {...}, cut_edges: {...}, confidence: {...}, notes: {...} } }
phase('Diagnose')
const verdicts = await parallel(UNITS.map(u => () => agent(
  `Visual QA judge for ${u}. Read IN ORDER: <panel path> (primary evidence; title bar gives
   zoom+origin), <reference>, <actual asset>, <pre-processing original>, <metadata json>.
   Judge: position / completeness / content. Estimate corrections in <declared unit system>.
   Be strict — the user already rejected this once. But honest ok verdicts are valid.`,
  { label: `judge:${u}`, schema: VERDICT })))
phase('Cross-check')
const critic = await agent(`Whole-picture critic: look ONLY for what per-unit judges can't see:
  missing units, overlaps, duplicates, edge artifacts...`, { schema: CRITIC_SCHEMA })
```

Then the MAIN LOOP applies fixes (single writer), re-renders, and re-runs the fan-out as a
verify round (fresh judges, same schema) until all severities ≤1. Never let judges write.

## 3. Evidence-cited audit fan-out (the production-gap audit)

One auditor per subsystem, schema-forced findings with a REQUIRED `evidence` field
("file:line citations or command output — no evidence = no finding"), explicit taxonomy
(BLOCKER / DESIGN GAP / LOOPHOLE / working-well), then a synthesis editor (effort high) that
dedups by root cause, keeps citations, keeps auditor disagreements visible, and emits the final
markdown report. The full script is persisted as `production-gap-audit-*` (see the tool-result
paths in this session's RUNLOG-adjacent notes); its briefs encode per-subsystem hunt lists —
reuse those briefs, they're the value.

## 4. Asset-generation pipelines (image-2)

Not a Workflow-tool job (key access, long-running) — run as staged Python in the main loop with
nohup + a log file, and a Monitor/wakeup armed on completion. Pattern staged in
`asset-gen/out_image2/buildings/fill/_*.py`: find-work → generate (resumable, budget-capped,
white-bg + key) → match/place → trim → apply (idempotent scene writer) → render → visual QA
loop. gpt-image-2 facts: `/v1/images/edits`; REJECTS `input_fidelity` and
`background=transparent` (image-1-only params — gate them); white-bg cutout via
`key_building.py --white 222 --erode 2`; "more detailed, true to the provided image" is the
faithful-upscale prompt that works; cutouts often keep NEIGHBOUR content — always trim+rematch.

## 5. Coordination primitives that mattered

- **Hold / go-signal** via SendMessage when two workstreams share a file (City.tscn tonight):
  tell the holder exactly what is frozen, what to reorder, and that YOU will send the go.
- **Idle agents**: asset agents that "wait for a batch" stall forever — resume them with
  active-polling instructions or take the wait into the main loop with a scheduled wakeup.
- **A workflow output file under /private/tmp is EPHEMERAL** — copy anything that matters
  (audit reports, verdicts) into the repo before ending the session.
- **Checkpoint commits** after every green milestone; scope commits to workstream files even
  when the tree holds other agents' work (`git add <explicit list>`).
