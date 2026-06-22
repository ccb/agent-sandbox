# Tingen Agent Sidecar

External LLM brain for the Tingen agent-sim. The Godot substrate POSTs perception
snapshots; the sidecar returns one schema-validated action per agent. All LLM
nondeterminism lives here — the engine stays deterministic and runs on an in-engine
`MockSidecar` for normal play and CI.

## Run

```bash
python3 agent-sidecar/sidecar.py --port 8777
curl -s localhost:8777/health
curl -s -X POST localhost:8777/propose -d '{"snapshots":[{"agent_id":"voss"}]}'
```

## Key handling

Reads `ANTHROPIC_API_KEY` from the environment, else from `--env-file <path>`. The token
value is **never printed or logged**. API keys live here, never in the Godot engine
(same rule as `asset-gen/`). With no key the sidecar runs in idle-only mode.

## Schema parity

Verbs and required args come from `tingen/data/action_schema.json` — the same file the
engine validates against. Change verbs in one place.

## Status

Scaffold: returns `idle` by default and validates every action. Real Claude calls + the
Godot-side `HttpSidecar` client are a later task; this stands up the stable contract.
