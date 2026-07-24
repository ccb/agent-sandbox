# Live-LLM run batch 1 — UPenn campus, 2026-07-24

The first batch of **real-model** runs on the Penn campus, logged against
[issue #760](https://github.com/ccb/agent-sandbox/issues/760) (the live-LLM run log).
Five runs, `claude-haiku-4-5`, seed 42, **$3.10 total**. Seven issues came out of it.

> **The run directories are not inside this folder.** `RunStore` resolves a run as
> `root / run_id` (`backend/run_store.py:121,223,309,357`) — a flat layout. Nesting
> them here would break `export_replay`, `--re-run`, `GET /runs/{id}/replay` and the
> believability audit. This folder is the index; the runs sit beside it in `runs/`.

## The runs

| | run id | cast | steps | convos | verbs | calls | cost | believability |
|---|---|---|---|---|---|---|---|---|
| **R1** baseline | `run-20260724-193817-d528ec` | diego, tanaka, sofia | 1200 ✅ | 3 | 6 | 172 | $0.3465 | 8.40 |
| **R2** warm/cold | `run-20260724-194343-78858a` | nina, jamal, grace, aiden, chris | 977 ⛔ cap | 10 | 5 | 499 | $1.0035 | 9.54 |
| **R3** adversarial | `run-20260724-195642-584ead` | omar, bethany, tessa, ellis, ravi, hannah, tanaka | 862 ⛔ cap | 9 | 4 | 506 | $1.0106 | 8.90 |
| **R4** from zero | `run-20260724-201036-e8c405` | wesley, dana, leon, casey, marcus | 1200 ✅ | 4 | **11** | 331 | $0.6192 | 9.36 |
| **R5** knobs A/B | `run-20260724-202121-e51349` | diego, tanaka, sofia + `--plan llm --cognition-tools --react` | 1200 ✅ | **0** | 4 | 65 | $0.1224 | 8.60 |

All five: `--scenario penn --steps 1200 --tick-seconds 0.05 --seed 42 --max-cost 1.00`,
cast applied through `POST /config` while paused at tick 0. R2 and R3 tripped the
$1.00 ceiling before the day ended — both the socially dense casts.

Write-ups, one comment per run plus a cross-run summary:

- [R1 — baseline](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5073734240)
- [R2 — warm vs cold](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5073813544)
- [R3 — adversarial edges](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5073966902)
- [R4 — from zero](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5074036062)
- [R5 — knobs A/B](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5074062138)
- [**Batch summary + cross-run comparison**](https://github.com/ccb/agent-sandbox/issues/760#issuecomment-5074099291)

## Issues that came out of this batch

| issue | what | evidenced by |
|---|---|---|
| [#776](https://github.com/ccb/agent-sandbox/issues/776) | `backend.env.load_dotenv()` looks one directory too shallow since #399 — `--brain llm` cannot find a repo-root `.env` | blocked R1 from starting at all |
| [#777](https://github.com/ccb/agent-sandbox/issues/777) | Reflection treats *future* schedule stops as completed past events | R1 — Sofia "remembered" dinner at 08:27 |
| [#778](https://github.com/ccb/agent-sandbox/issues/778) | Co-located pair locks into a groundhog-day loop; `talk_to` starves `perform`, schedule never advances, 63% of budget burned | R2 — aiden/chris, corroborated by R3's ravi/hannah |
| [**#779**](https://github.com/ccb/agent-sandbox/issues/779) | **Persona relationships never reach agent memory** — seeded `rivals` behave as allies, `closeness` has no effect. The priority. | R3 primarily; zero relationship memories in all five |
| [#780](https://github.com/ccb/agent-sandbox/issues/780) | Agents invent world geography in dialogue and then claim to have visited it | R4 — casey/dana and a boathouse that doesn't exist |
| [#781](https://github.com/ccb/agent-sandbox/issues/781) | `believability --no-llm` ranks the loop run highest (9.54) and the healthiest lowest (8.40) — rewards memory volume, not progress | the believability column above |
| [#782](https://github.com/ccb/agent-sandbox/issues/782) | `--plan llm` spend charged to no run (`runs.cost` under-reports 29%), plus an orphan run dir per configured run | R5; the orphans listed below |

## Reading these runs

From the repo root:

```bash
R=godot-generative-agents/runs
ID=run-20260724-193817-d528ec

# what agents were actually doing (the useful distribution — events.jsonl is sparse)
jq -r 'to_entries[] | "\(.key)\t\(.value.act)"' $R/$ID/frames.jsonl | sort | uniq -c | sort -rn

# action tally
uv run python godot-generative-agents/tools/most_common_actions.py $R/$ID/events.jsonl

# conversations — NOTE the chat blob grows one line per step and is repainted across
# the playback window, so collapse states where one transcript prefixes the next
# (this redundancy is also why frames.jsonl is ~40 MB of this folder's neighbours)
jq -r 'to_entries[] | select(.value.chat) | .value.chat | map(.[0]+": "+.[1]) | join("\n") + "\n---"' \
  $R/$ID/frames.jsonl | uniq

# memories, cost
sqlite3 -header $R/sim.db "select agent,kind,created_turn,text from memories where run_id='$ID';"
sqlite3 -header $R/sim.db "select id,status,model,cost,steps from runs order by created desc;"

# scored audit (but read #781 before trusting it to compare runs)
uv run python -m backend.eval.believability $R/$ID --no-llm
```

Per-call token counts, `by_tool` and `by_role` are **not** in these artifacts — they
live only in the in-process ledger and were captured from `GET /usage` before each
shutdown. Those figures are in the issue write-ups.

## Caveats

- **Not reproducible.** `--re-run` on R1 diverges at frame 0, and that is expected:
  byte-identity only holds for runs recorded under *sequential* decide
  (`serve_penn.py:2074-2079`), and `--decide-workers auto` gives a paid brain one
  worker per persona. R5 refuses outright — `--re-run` doesn't support model-authored
  days. **Pass `--decide-workers 0` for any future run intended to be citable.**
- **Five orphan directories** sit alongside these, kept deliberately as #782 evidence
  and so `sim.db` stays consistent with the disk. Each is a `status='reset'`, 0-step,
  $0 run opened at boot and abandoned when `POST /config` rebuilt the world:
  `run-20260724-193816-b8e1bb`, `run-20260724-194341-cbc3b1`,
  `run-20260724-195640-a17eca`, `run-20260724-201036-aa41d4`,
  `run-20260724-202101-4400fc`.
- R5's `runs.cost` reads $0.0863 against a true $0.1224 — that gap *is* #782.
- Cost per run ran ~3.5× the estimate in `docs/design/agent-llm-interface.md:112-129`,
  which omits the `score` role (#583). Budget accordingly.
