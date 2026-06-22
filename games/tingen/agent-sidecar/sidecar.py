#!/usr/bin/env python3
"""
Tingen Agent Sidecar (scaffold)
===============================
The external LLM brain for the Tingen agent-sim. Godot (the deterministic substrate)
POSTs perception snapshots; this service returns ONE validated action per snapshot,
chosen from the constrained verb schema shared with the engine
(tingen/data/action_schema.json). All LLM nondeterminism is quarantined here.

With ANTHROPIC_API_KEY present it asks Claude for each agent's next action, constrained to
the shared verb schema; with no key (or on any network/parse failure) it returns a safe
`idle` and the engine's ambient brain fills in movement. Every action is validated against
the schema before it leaves this service.

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
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Shared schema: one source of truth with the engine.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tingen" / "data" / "action_schema.json"

# Anthropic Messages API (called via stdlib urllib — no third-party deps). A per-beat NPC
# decision is small and frequent, so the default is a fast model; override with TINGEN_SIDECAR_MODEL.
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = os.environ.get("TINGEN_SIDECAR_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = 256
HTTP_TIMEOUT = 18  # seconds; under the Godot client's ~20s budget before it ambient-falls-back


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


def idle_action(snapshot: dict) -> dict:
    return {"actor": snapshot.get("agent_id", ""), "verb": "idle", "args": {}}


def verb_menu(verbs: dict) -> str:
    """One line per verb with its required args, so the model only ever emits legal actions."""
    lines = []
    for verb in sorted(verbs):
        req = verbs[verb]
        lines.append(f"- {verb}: requires {req}" if req else f"- {verb}: no args")
    return "\n".join(lines)


def build_prompt(snapshot: dict, verbs: dict) -> str:
    persona = {
        "id": snapshot.get("agent_id", ""),
        "name": snapshot.get("display_name", ""),
        "faction": snapshot.get("faction", ""),
        "role": snapshot.get("role", ""),
        "intent": snapshot.get("intent", ""),
        "position": snapshot.get("position", []),
    }
    world = {
        "phase": snapshot.get("phase", ""),
        "stage": snapshot.get("stage", ""),
        "pressures": snapshot.get("pressures", {}),
    }
    return (
        "You are one inhabitant of Tingen, a fog-choked Victorian city where a cult races to "
        "summon a descending god. Choose THIS character's single next action for the current "
        "beat, in character, using the allowed verbs only.\n\n"
        f"Character: {json.dumps(persona, ensure_ascii=False)}\n"
        f"World: {json.dumps(world, ensure_ascii=False)}\n"
        f"Nearby: {json.dumps(snapshot.get('nearby', []), ensure_ascii=False)}\n\n"
        f"Allowed verbs (use these names EXACTLY and include every required arg):\n"
        f"{verb_menu(verbs)}\n\n"
        "A move target may be another agent's id, the site name 'iron_cross_warehouse', or an "
        "'x,y' coordinate string.\n"
        'Respond with ONLY a JSON object like {"verb": "move_to", "args": {"target": "..."}}. '
        "No prose, no markdown fence."
    )


def extract_action(text: str) -> dict:
    """Pull the first JSON object out of the model's reply (tolerates stray prose or fences)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def call_claude(snapshot: dict, verbs: dict, key: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": build_prompt(snapshot, verbs)}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    req.add_header("x-api-key", key)  # used only to authenticate; never logged or returned to Godot
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return extract_action(text)


def decide(snapshot: dict, verbs: dict, key: str = "") -> dict:
    """One action for one agent. With a key, ask Claude; without (or on any failure), idle."""
    if not key:
        return idle_action(snapshot)
    try:
        action = call_claude(snapshot, verbs, key)
    except Exception:
        return idle_action(snapshot)  # any network/parse failure -> safe idle (engine ambient-fills)
    if not isinstance(action, dict) or "verb" not in action:
        return idle_action(snapshot)
    action["actor"] = snapshot.get("agent_id", "")  # the engine binds the action to this agent
    action.setdefault("args", {})
    ok, _reason = validate_action(action, verbs)
    return action if ok else idle_action(snapshot)


class Handler(BaseHTTPRequestHandler):
    verbs: dict = {}
    has_key: bool = False
    key: str = ""   # used in-process for the Anthropic call; never printed or sent to the engine

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
            action = decide(snap, self.verbs, self.key)
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
    Handler.has_key = bool(key)  # presence flag for /health; NEVER the value
    Handler.key = key            # used in-process for the Anthropic call; never printed

    # Key presence only — never echo the token.
    print(f"[sidecar] schema verbs: {sorted(Handler.verbs)}")
    print(f"[sidecar] model: {MODEL}")
    print(f"[sidecar] ANTHROPIC_API_KEY {'present (LLM mode)' if key else 'MISSING (idle-only mode)'}")
    print(f"[sidecar] listening on http://127.0.0.1:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
