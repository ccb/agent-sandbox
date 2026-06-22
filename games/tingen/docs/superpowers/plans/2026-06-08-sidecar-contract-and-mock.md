# LLM Sidecar Contract + Mock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the single typed boundary between the deterministic Godot substrate and the (eventual) LLM brain — a constrained action schema, a swappable `SidecarClient` interface with a deterministic in-engine `MockSidecar`, the `SidecarBridge` seam the agent runtime calls, and a runnable Python sidecar scaffold (key-safe, schema-parity) — so CI never needs a live API.

**Architecture:** All nondeterminism is quarantined behind one interface. `ActionSchema` (shared `data/action_schema.json`) defines the typed verb set and validates any proposed action. `SidecarClient` (abstract RefCounted) declares `propose(snapshots) -> [action]`; `MockSidecar` returns scripted/idle actions deterministically for tests; a later `HttpSidecar` will talk to the Python service. `SidecarBridge` (autoload) holds the active client (a `MockSidecar` by default) and is the only thing the agent runtime touches. The Python `agent-sidecar/` scaffold mirrors `asset-gen/`'s key handling (reads `ANTHROPIC_API_KEY` from env/`.env`, never prints it) and shares the same schema JSON.

**Tech Stack:** Godot 4.6, GDScript, autoloads + `class_name` scripts, shared JSON schema, Python 3 stdlib `http.server` (no extra deps). Headless `SceneTree` test runner (`tingen/tests/run_tests.gd`).

**Source spec:** `docs/superpowers/specs/2026-06-08-tingen-agent-sim-vertical-slice-design.md` §B, §D, §7.

---

## Conventions

- **Godot project root:** `Tingen-Game/tingen/`. Run commands from `Tingen-Game/`.
- **Run the suite:** `godot --headless --path tingen -s tests/run_tests.gd`. Success tail: `=== N passed, 0 failed ===`, exit 0.
- **Test pattern:** one `SceneTree` script; each feature gets `func _test_xxx()` using `_ok(cond, label)`, called in `_init()` above the final `print(...)`.

## File Structure

- **Create** `tingen/data/action_schema.json` — the one source of truth for valid verbs + required args (loaded by both GDScript and Python).
- **Create** `tingen/src/ActionSchema.gd` — `class_name ActionSchema`. One job: validate a proposed action dict against the schema.
- **Create** `tingen/src/SidecarClient.gd` — `class_name SidecarClient` (RefCounted). One job: the abstract `propose(snapshots) -> [action]` interface.
- **Create** `tingen/src/MockSidecar.gd` — `class_name MockSidecar extends SidecarClient`. One job: deterministic scripted/idle proposals for tests.
- **Create** `tingen/src/SidecarBridge.gd` — autoload `SidecarBridge`. One job: own the active client + route `propose`.
- **Create** `agent-sidecar/sidecar.py` — runnable Python scaffold (health + propose), key-safe, schema-parity. Not CI-gated.
- **Create** `agent-sidecar/README.md` — how to run it; the key rule.
- **Modify** `tingen/project.godot` — register `SidecarBridge`.
- **Modify** `tingen/tests/run_tests.gd` — add tests.

---

## Task 1: ActionSchema (typed verb validation)

**Files:**
- Create: `tingen/data/action_schema.json`
- Create: `tingen/src/ActionSchema.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_action_schema() -> void:
	print("[action schema]")
	var ok := ActionSchema.validate({"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	_ok(ok["ok"] == true, "valid move_to accepted")
	var no_verb := ActionSchema.validate({"actor": "voss", "verb": "teleport", "args": {}})
	_ok(no_verb["ok"] == false, "unknown verb rejected")
	var missing := ActionSchema.validate({"actor": "voss", "verb": "talk_to", "args": {"agent": "orin"}})
	_ok(missing["ok"] == false, "talk_to missing 'topic' rejected")
	var idle := ActionSchema.validate({"actor": "voss", "verb": "idle", "args": {}})
	_ok(idle["ok"] == true, "idle needs no args")
	var no_actor := ActionSchema.validate({"verb": "idle", "args": {}})
	_ok(no_actor["ok"] == false, "missing actor rejected")
	_ok(ActionSchema.is_verb("attack"), "attack is a known verb")
	_ok(not ActionSchema.is_verb("nope"), "nope is not a known verb")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_action_schema()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `ActionSchema` not defined.

- [ ] **Step 3: Create the schema JSON + ActionSchema.gd**

Create `tingen/data/action_schema.json`:

```json
{
	"verbs": {
		"move_to": ["target"],
		"talk_to": ["agent", "topic"],
		"gather_item": ["item_id"],
		"perform_ritual_step": ["step"],
		"hide": [],
		"flee": ["from"],
		"attack": ["target"],
		"recruit": ["agent"],
		"report": ["to", "info"],
		"idle": []
	}
}
```

Create `tingen/src/ActionSchema.gd`:

```gdscript
class_name ActionSchema
extends RefCounted
## The one source of truth for the constrained agent action vocabulary. Loads
## data/action_schema.json (shared verbatim with the Python sidecar) and validates that
## a proposed action is (1) well-formed and (2) uses a known verb with its required args.
## This is the "legality: valid schema" half of the critic's legality axis (the
## "possible in current world state" half is checked at commit time, later).
##
## Action shape: { "actor": "<agent_id>", "verb": "<verb>", "args": { ... } }

const SCHEMA_PATH: String = "res://data/action_schema.json"

static var _verbs: Dictionary = {}   # verb -> Array[String] required arg names
static var _loaded: bool = false

static func _ensure_loaded() -> void:
	if _loaded:
		return
	_loaded = true
	if not FileAccess.file_exists(SCHEMA_PATH):
		push_error("ActionSchema: missing %s" % SCHEMA_PATH)
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(SCHEMA_PATH))
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("ActionSchema: %s is not a JSON object" % SCHEMA_PATH)
		return
	var verbs: Variant = parsed.get("verbs", {})
	if typeof(verbs) == TYPE_DICTIONARY:
		for v in verbs.keys():
			_verbs[String(v)] = (verbs[v] as Array).duplicate()

static func verbs() -> Array:
	_ensure_loaded()
	return _verbs.keys()

static func is_verb(verb: String) -> bool:
	_ensure_loaded()
	return _verbs.has(verb)

## Returns { "ok": bool, "reason": String }. `reason` is "" when ok.
static func validate(action: Dictionary) -> Dictionary:
	_ensure_loaded()
	if String(action.get("actor", "")) == "":
		return {"ok": false, "reason": "missing actor"}
	var verb := String(action.get("verb", ""))
	if not _verbs.has(verb):
		return {"ok": false, "reason": "unknown verb '%s'" % verb}
	var args: Variant = action.get("args", {})
	if typeof(args) != TYPE_DICTIONARY:
		return {"ok": false, "reason": "args must be an object"}
	for required in _verbs[verb]:
		if not (args as Dictionary).has(required):
			return {"ok": false, "reason": "verb '%s' missing arg '%s'" % [verb, required]}
	return {"ok": true, "reason": ""}
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[action schema]` shows seven PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/data/action_schema.json tingen/src/ActionSchema.gd tingen/tests/run_tests.gd
git commit -m "feat(sidecar): ActionSchema — constrained verb validation"
```

---

## Task 2: SidecarClient interface + MockSidecar

**Files:**
- Create: `tingen/src/SidecarClient.gd`
- Create: `tingen/src/MockSidecar.gd`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_mock_sidecar() -> void:
	print("[mock sidecar]")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "move_to", "args": {"target": "iron_cross_warehouse"}})
	var snaps := [{"agent_id": "voss"}, {"agent_id": "orin"}]
	var out: Array = mock.propose(snaps)
	_ok(out.size() == 2, "one proposal per snapshot")
	_ok(out[0]["verb"] == "move_to", "scripted action returned for voss")
	_ok(out[1]["verb"] == "idle", "unscripted agent defaults to idle")
	_ok(out[1]["actor"] == "orin", "idle proposal is attributed to the right actor")
	# Queue support: pop one action per beat.
	mock.set_action("orin", [{"actor": "orin", "verb": "hide", "args": {}}])
	var out2: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out2[0]["verb"] == "hide", "queued action consumed")
	var out3: Array = mock.propose([{"agent_id": "orin"}])
	_ok(out3[0]["verb"] == "idle", "empty queue falls back to idle")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_mock_sidecar()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: parse/identifier error — `MockSidecar` not defined.

- [ ] **Step 3: Create SidecarClient.gd and MockSidecar.gd**

Create `tingen/src/SidecarClient.gd`:

```gdscript
class_name SidecarClient
extends RefCounted
## Abstract boundary to the LLM brain. The substrate hands the client a batch of
## perception snapshots and receives one proposed action per snapshot. All
## nondeterminism (LLM calls, batching, caching) lives behind this interface in concrete
## subclasses; the substrate stays deterministic. Subclasses: MockSidecar (tests/offline),
## and later HttpSidecar (talks to the Python service).

## True when the client can serve proposals (a network client may be still connecting).
func is_ready() -> bool:
	return true

## snapshots: Array of perception dicts (each must carry an "agent_id"). Returns an
## Array of action dicts aligned 1:1 with `snapshots`. Base returns idle for each.
func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		out.append({"actor": String((s as Dictionary).get("agent_id", "")), "verb": "idle", "args": {}})
	return out
```

Create `tingen/src/MockSidecar.gd`:

```gdscript
class_name MockSidecar
extends SidecarClient
## Deterministic test/offline sidecar. Returns a scripted action per actor; agents with
## no script idle. A scripted value may be a single action dict (returned every beat) or
## an Array used as a queue (one popped per beat, idle when empty). Lets headless tests
## drive exact agent behavior with no LLM.

var scripted: Dictionary = {}   # actor_id -> action dict OR Array[action dict]

func set_action(actor_id: String, action: Variant) -> void:
	scripted[actor_id] = action

func clear() -> void:
	scripted.clear()

func propose(snapshots: Array) -> Array:
	var out: Array = []
	for s in snapshots:
		var actor := String((s as Dictionary).get("agent_id", ""))
		out.append(_next_for(actor))
	return out

func _next_for(actor: String) -> Dictionary:
	if not scripted.has(actor):
		return _idle(actor)
	var v: Variant = scripted[actor]
	if typeof(v) == TYPE_ARRAY:
		var q: Array = v
		if q.is_empty():
			return _idle(actor)
		return (q.pop_front() as Dictionary).duplicate(true)
	return (v as Dictionary).duplicate(true)

func _idle(actor: String) -> Dictionary:
	return {"actor": actor, "verb": "idle", "args": {}}
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[mock sidecar]` shows six PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SidecarClient.gd tingen/src/MockSidecar.gd tingen/tests/run_tests.gd
git commit -m "feat(sidecar): SidecarClient interface + deterministic MockSidecar"
```

---

## Task 3: SidecarBridge autoload (the single seam)

**Files:**
- Create: `tingen/src/SidecarBridge.gd`
- Modify: `tingen/project.godot`
- Test: `tingen/tests/run_tests.gd`

- [ ] **Step 1: Write the failing test**

In `tingen/tests/run_tests.gd`, add:

```gdscript
func _test_sidecar_bridge() -> void:
	print("[sidecar bridge]")
	var SB: Object = root.get_node("/root/SidecarBridge")
	_ok(SB.client != null, "bridge has a default client")
	var mock := MockSidecar.new()
	mock.set_action("voss", {"actor": "voss", "verb": "attack", "args": {"target": "pell"}})
	SB.set_client(mock)
	var out: Array = SB.propose([{"agent_id": "voss"}])
	_ok(out.size() == 1, "bridge routes one proposal")
	_ok(out[0]["verb"] == "attack", "bridge returns the active client's proposal")
	# Every proposal the bridge returns must be schema-valid for the mock to be useful.
	_ok(ActionSchema.validate(out[0])["ok"], "bridged proposal is schema-valid")
```

Register in `_init()` above the final `print(...)`:

```gdscript
	_test_sidecar_bridge()

	print("\n=== %d passed, %d failed ===" % [_passed, _failed])
```

- [ ] **Step 2: Run the suite to verify it fails**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: failure resolving `/root/SidecarBridge` (autoload missing).

- [ ] **Step 3: Create SidecarBridge.gd + register autoload**

Create `tingen/src/SidecarBridge.gd`:

```gdscript
extends Node
## The single seam between the substrate and the LLM brain (autoload `SidecarBridge`).
## Holds one active SidecarClient — a MockSidecar by default so the game and CI run with
## zero network/API. The agent runtime (a later plan) calls `propose(snapshots)` here and
## nowhere else; swapping in the real HttpSidecar is a one-line `set_client` change.

var client: SidecarClient = null

func _ready() -> void:
	if client == null:
		client = MockSidecar.new()

func set_client(c: SidecarClient) -> void:
	client = c

func is_ready() -> bool:
	return client != null and client.is_ready()

func propose(snapshots: Array) -> Array:
	if client == null:
		return []
	return client.propose(snapshots)
```

Register the autoload in `tingen/project.godot` — add the `SidecarBridge` line in the `[autoload]` block. Place it after `Agents` (from the substrate plan) if present, otherwise after `WorldManager`:

```
Agents="*res://src/AgentRegistry.gd"
SidecarBridge="*res://src/SidecarBridge.gd"
EventManager="*res://src/EventManager.gd"
```

- [ ] **Step 4: Run the suite to verify it passes**

Run: `godot --headless --path tingen -s tests/run_tests.gd`
Expected: `[sidecar bridge]` shows four PASS lines; suite exits 0.

- [ ] **Step 5: Commit**

```bash
git add tingen/src/SidecarBridge.gd tingen/project.godot tingen/tests/run_tests.gd
git commit -m "feat(sidecar): SidecarBridge autoload seam (mock client by default)"
```

---

## Task 4: Python sidecar scaffold (runnable, key-safe, schema-parity)

This task adds NO Godot tests (the engine runs on `MockSidecar`); it stands up the real
service skeleton the slice will later point `HttpSidecar` at. Verification is manual.

**Files:**
- Create: `agent-sidecar/sidecar.py`
- Create: `agent-sidecar/README.md`

- [ ] **Step 1: Create the sidecar server**

Create `agent-sidecar/sidecar.py`:

```python
#!/usr/bin/env python3
"""
Tingen Agent Sidecar (scaffold)
===============================
The external LLM brain for the Tingen agent-sim. Godot (the deterministic substrate)
POSTs perception snapshots; this service returns ONE validated action per snapshot,
chosen from the constrained verb schema shared with the engine
(tingen/data/action_schema.json). All LLM nondeterminism is quarantined here.

This scaffold returns safe `idle` actions by default and validates every action against
the shared schema. Wiring real Claude calls is a later task — the contract is what
matters now, so the engine can talk to a stable boundary.

Key handling (mirrors asset-gen/generate_tingen_assets.py):
  Reads ANTHROPIC_API_KEY from the environment, else from --env-file. The token value is
  NEVER printed or logged. API keys live here, never in the Godot engine.

Run:
  python3 agent-sidecar/sidecar.py --port 8777
  curl -s localhost:8777/health
  curl -s -X POST localhost:8777/propose -d '{"snapshots":[{"agent_id":"voss"}]}'

Requires: Python 3.8+ standard library only (no pip installs).
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Shared schema: one source of truth with the engine.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tingen" / "data" / "action_schema.json"


def load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("verbs", {})


def validate_action(action: dict, verbs: dict) -> tuple[bool, str]:
    if not action.get("actor"):
        return False, "missing actor"
    verb = action.get("verb", "")
    if verb not in verbs:
        return False, f"unknown verb '{verb}'"
    args = action.get("args", {})
    if not isinstance(args, dict):
        return False, "args must be an object"
    for req in verbs[verb]:
        if req not in args:
            return False, f"verb '{verb}' missing arg '{req}'"
    return True, ""


def decide(snapshot: dict, verbs: dict) -> dict:
    """Pick one action for one agent. Scaffold default: idle. (LLM call goes here later.)"""
    return {"actor": snapshot.get("agent_id", ""), "verb": "idle", "args": {}}


class Handler(BaseHTTPRequestHandler):
    verbs: dict = {}
    has_key: bool = False

    def log_message(self, *_args) -> None:  # keep logs quiet + key-safe
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "have_key": self.has_key, "verbs": list(self.verbs)})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/propose":
            self._send(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        snapshots = req.get("snapshots", [])
        actions = []
        for snap in snapshots:
            action = decide(snap, self.verbs)
            ok, reason = validate_action(action, self.verbs)
            if not ok:
                action = {"actor": snap.get("agent_id", ""), "verb": "idle", "args": {}, "_invalid": reason}
            actions.append(action)
        self._send(200, {"ok": True, "actions": actions})


def read_key(env_file: str | None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key and env_file and Path(env_file).exists():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    return key


def main() -> None:
    ap = argparse.ArgumentParser(description="Tingen agent sidecar (scaffold)")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--env-file", default=None, help="path to a .env with ANTHROPIC_API_KEY")
    args = ap.parse_args()

    key = read_key(args.env_file)
    Handler.verbs = load_schema()
    Handler.has_key = bool(key)  # store presence only; NEVER the value

    # Key presence only — never echo the token.
    print(f"[sidecar] schema verbs: {sorted(Handler.verbs)}")
    print(f"[sidecar] ANTHROPIC_API_KEY {'present' if key else 'MISSING (idle-only mode)'}")
    print(f"[sidecar] listening on http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create the README**

Create `agent-sidecar/README.md`:

```markdown
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
```

- [ ] **Step 3: Verify it runs (manual)**

Run:
```bash
python3 agent-sidecar/sidecar.py --port 8777 &
sleep 1
curl -s localhost:8777/health
curl -s -X POST localhost:8777/propose -d '{"snapshots":[{"agent_id":"voss"},{"agent_id":"orin"}]}'
kill %1
```
Expected: health returns `{"ok": true, "have_key": ..., "verbs": [...]}`; propose returns `{"ok": true, "actions": [{"actor":"voss","verb":"idle",...}, {"actor":"orin","verb":"idle",...}]}`. Confirm the startup logs print key **presence** only, never a token value.

- [ ] **Step 4: Commit**

```bash
git add agent-sidecar/sidecar.py agent-sidecar/README.md
git commit -m "feat(sidecar): runnable Python scaffold (key-safe, schema-parity)"
```

---

## Done criteria for this plan

- Full headless suite passes and includes: action schema, mock sidecar, sidecar bridge.
- `ActionSchema` validates the constrained verb set from `data/action_schema.json`.
- `SidecarBridge` is a registered autoload defaulting to `MockSidecar`; tests can swap the client and drive exact agent behavior.
- The Python sidecar runs from stdlib, validates against the shared schema, and never prints the API key.

## What this plan deliberately does NOT do (later plans)

- No `HttpSidecar` Godot client and no live Claude calls — the engine runs on `MockSidecar`; wiring the real service is deferred (Plan 4 builds perception/commit on the bridge; live LLM is post-slice).
- No perception-snapshot builder or commit logic — Plan 4 builds snapshots and consumes proposals.
- No overseer/critic verdicts — Plan 5 inserts review between propose and commit.
