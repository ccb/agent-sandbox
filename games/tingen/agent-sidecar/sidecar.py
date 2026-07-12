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
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make the cognition package importable, then load the stateful brain (cognition/SPEC.md §6).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cognition.brain import BrainSession

# Shared schema: one source of truth with the engine.
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "tingen" / "data" / "action_schema.json"

# Anthropic Messages API (called via stdlib urllib — no third-party deps). A per-beat NPC
# decision is small and frequent, so the default is a fast model; override with TINGEN_SIDECAR_MODEL.
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = os.environ.get("TINGEN_SIDECAR_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = 256
# Dialogue needs more room than a bare action JSON (a spoken line + an optional action + a few reply
# chips). Player-initiated, so it can afford the larger budget — the autonomous beat stays at MAX_TOKENS.
CONVERSE_MAX_TOKENS = 600
# GM digest narration (/narrate): 2-4 sentences of prose, so it needs a little more than an action
# JSON but far less than a dialogue turn.
NARRATE_MAX_TOKENS = 300
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
        "role": snapshot.get("role", ""),
        "intent": snapshot.get("intent", ""),
        "position": snapshot.get("position", []),
    }
    # Objective roster only — who is present (id + role). Per-agent flags the engine carries on each
    # nearby entry (conceals_identity, distance) stay OUT of the prompt; no faction label either.
    roster = ", ".join(
        (f"{n.get('id')} ({n.get('role')})" if isinstance(n, dict) and n.get("role")
         else str(n.get("id") if isinstance(n, dict) else n))
        for n in (snapshot.get("nearby", []) or []))
    world = {
        "phase": snapshot.get("phase", ""),
        "stage": snapshot.get("stage", ""),
        "pressures": snapshot.get("pressures", {}),
    }
    return (
        "You are a character in a simulated world. Choose THIS character's single next action for "
        "the current beat, in character, using the allowed verbs only.\n\n"
        f"Character: {json.dumps(persona, ensure_ascii=False)}\n"
        f"World: {json.dumps(world, ensure_ascii=False)}\n"
        f"Nearby: {roster}\n\n"
        f"Allowed verbs (use these names EXACTLY and include every required arg):\n"
        f"{verb_menu(verbs)}\n\n"
        "A move target may be another agent's id, a known site name, or an 'x,y' coordinate string. "
        "A character whose goal names a site should move_to that site, then act on it once standing "
        "there.\n"
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


def _coerce_converse(obj) -> dict:
    """Coerce a (possibly messy) reply object into {say, action, replies} with safe defaults."""
    if not isinstance(obj, dict):
        return {"say": "", "action": None, "replies": []}
    action = obj.get("action") if isinstance(obj.get("action"), dict) else None
    replies = obj.get("replies") if isinstance(obj.get("replies"), list) else []
    return {"say": str(obj.get("say", "")).strip(), "action": action, "replies": replies}


def parse_converse_reply(text: str) -> dict:
    """Turn a TEXT /converse reply into {say, action, replies}. Reuses extract_action's tolerant
    first-{...}-to-last-} slice; coerces to safe defaults — never raises. This is the FALLBACK path:
    the live route forces structured tool use (call_claude_tool) so the model can't hand us invalid
    JSON (a `say` full of quotes/dashes), which a hand-built JSON string routinely breaks on."""
    return _coerce_converse(extract_action(text))


# Forced-tool schema for /converse: the API guarantees the model fills these as VALID JSON (escaping
# quotes etc.), so an expressive spoken line never corrupts the structure the way free-text JSON does.
CONVERSE_TOOL = {
    "name": "reply",
    "description": "Reply to the player, in character.",
    "input_schema": {
        "type": "object",
        "properties": {
            "say": {"type": "string", "description": "What you say aloud, in character (plain prose)."},
            "action": {
                "type": ["object", "null"],
                "description": "ONE optional mechanical action you take as you speak, or null.",
                "properties": {"verb": {"type": "string"}, "args": {"type": "object"}},
            },
            "replies": {
                "type": "array",
                "description": "Up to 4 short lines the player could say back.",
                "items": {"type": "object",
                          "properties": {"id": {"type": "string"}, "text": {"type": "string"}}},
            },
        },
        "required": ["say"],
    },
}


def call_claude_tool(prompt: str, key: str, tool: dict, max_tokens: int = MAX_TOKENS, model: str = "") -> dict:
    """Force a STRUCTURED reply via tool use. tool_choice pins the model to `tool`, so the response
    carries a tool_use block whose `input` is schema-valid JSON. Returns {input, tokens_in/out, cost};
    `input` is {} if (unexpectedly) no tool_use block came back. `model` is the per-request override
    (the engine's per-agent selection); empty → the process default MODEL."""
    use_model = model or MODEL
    payload = json.dumps({
        "model": use_model,
        "max_tokens": max_tokens,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    req.add_header("x-api-key", key)  # used only to authenticate; never logged or returned to Godot
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    inp: dict = {}
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
            inp = block["input"]
            break
    usage = data.get("usage", {})
    tin = int(usage.get("input_tokens", 0))
    tout = int(usage.get("output_tokens", 0))
    return {"input": inp, "tokens_in": tin, "tokens_out": tout, "cost": _cost_usd(use_model, tin, tout),
            "model": use_model}


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


# USD per 1,000,000 tokens (input, output), keyed by model-id prefix. From the claude-api reference.
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-fable-5": (10.00, 50.00),
}


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Dollar cost of one call. Matches the model id by prefix; unknown models cost 0 (flagged as such)."""
    for prefix, (pin, pout) in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            return tokens_in / 1_000_000.0 * pin + tokens_out / 1_000_000.0 * pout
    return 0.0


def call_claude_full(prompt: str, key: str, max_tokens: int = MAX_TOKENS, model: str = "") -> dict:
    """POST the brain-built prompt to Claude; return the raw reply text + token usage + cost. `model` is
    the per-request override (the engine's per-agent selection); empty → the process default MODEL."""
    use_model = model or MODEL
    payload = json.dumps({
        "model": use_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(ANTHROPIC_URL, data=payload, method="POST")
    req.add_header("content-type", "application/json")
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    req.add_header("x-api-key", key)  # used only to authenticate; never logged or returned to Godot
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage", {})
    tin = int(usage.get("input_tokens", 0))
    tout = int(usage.get("output_tokens", 0))
    return {"text": text, "tokens_in": tin, "tokens_out": tout, "cost": _cost_usd(use_model, tin, tout),
            "model": use_model}


def call_claude_text(prompt: str, key: str) -> str:
    return call_claude_full(prompt, key)["text"]


# --- /narrate: GM digest narration (the GM panel's hybrid LLM paragraph) --------------------------
NARRATE_PERSONA = (
    "You are the game master's narrator for a simulated Victorian city. In 2-4 sentences, "
    "present tense, summarize what just happened for the player-facing log. No speculation, "
    "no meta-commentary."
)


def build_narrate_prompt(events: list, world: dict) -> str:
    """Compact GM prompt: persona + the deterministic digest lines + the world state."""
    lines = "\n".join(f"- {e}" for e in events)
    return (
        f"{NARRATE_PERSONA}\n\n"
        f"World state: {json.dumps(world, ensure_ascii=False)}\n"
        f"Events since the last digest:\n{lines}"
    )


def narrate_reply(req: dict, key: str) -> dict:
    """The /narrate route's whole reply, as a plain function so it is testable without a socket
    (test_narrate_route.py monkeypatches call_claude_full). Empty events (or no key) short-circuit
    to an empty summary WITHOUT calling the LLM — the engine's deterministic digest already rendered,
    so an absent narration is a normal outcome, not an error."""
    events = [str(e) for e in (req.get("events") or []) if str(e).strip()]
    if not events or not key:
        return {"ok": True, "summary": "", "model": ""}
    world = req.get("world") if isinstance(req.get("world"), dict) else {}
    model = str(req.get("model", ""))  # per-request model (empty → the process default MODEL)
    try:
        full = call_claude_full(build_narrate_prompt(events, world), key,
                                max_tokens=NARRATE_MAX_TOKENS, model=model)
    except Exception as e:
        return {"ok": False, "error": str(e), "summary": "", "model": ""}
    return {"ok": True, "summary": str(full.get("text", "")).strip(),
            "model": str(full.get("model", "")), "cost": float(full.get("cost", 0.0))}


def call_claude_prompt(prompt: str, key: str) -> dict:
    """Like call_claude, but the BRAIN already built the prompt (SPEC §6); returns an action dict."""
    return extract_action(call_claude_text(prompt, key))


# Process-wide stateful cognition brain (SPEC §6). One memory stream per (session, agent). The brain
# is internally thread-safe (per-agent locks, released around the LLM call), so a batch of agents is
# decided CONCURRENTLY rather than serializing behind one global lock.
_BRAIN = BrainSession()


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
        if self.path not in ("/propose", "/decide", "/converse", "/narrate"):
            self._send(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        if self.path == "/decide":
            self._handle_decide(req)
            return
        if self.path == "/converse":
            self._handle_converse(req)
            return
        if self.path == "/narrate":
            # GM digest narration: stateless, single call; the whole reply is built by narrate_reply.
            self._send(200, narrate_reply(req, self.key))
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

    def _handle_decide(self, req: dict) -> None:
        """Stateful cognition decide (SPEC §6). Accepts EITHER a single request, or a batch
        {"requests": [...]} so the Godot client makes one POST per beat (like /propose) and gets back
        an `actions` array shaped identically. The brain ingests events, retrieves memories, builds the
        prompt, Claude proposes, the hard veto governs."""
        if isinstance(req.get("requests"), list):
            reqs = req["requests"]
            # The brain is thread-safe and the LLM call dominates latency, so decide agents
            # CONCURRENTLY — batch wall-time is ~one Claude call, not N of them serialized.
            if len(reqs) <= 1:
                results = [self._decide_one(r) for r in reqs]
            else:
                with ThreadPoolExecutor(max_workers=min(8, len(reqs))) as ex:
                    results = list(ex.map(self._decide_one, reqs))
            self._send(200, {"ok": all(r.get("verdict") != "error" for r in results),
                             "actions": [r["action"] for r in results],  # mirrors /propose
                             "results": results})
            return
        self._send(200, {"ok": True, **self._decide_one(req)})

    def _handle_converse(self, req: dict) -> None:
        """One player↔NPC conversation turn (design §2). The brain hears the player's utterance, the LLM
        replies in character, and the spoken line is returned verbatim (NEVER governed); only the
        OPTIONAL mechanical action is schema-validated + hard-veto governed. Single request, not a batch."""
        agent_id = str(req.get("agent_id", ""))
        model = str(req.get("model", ""))  # per-agent model selection (empty → the process default MODEL)

        def llm(prompt: str) -> dict:
            if not self.key:
                # No key (offline) → a neutral in-character beat, no action.
                return {"say": "…", "action": None, "replies": []}
            try:
                full = call_claude_tool(prompt, self.key, CONVERSE_TOOL, max_tokens=CONVERSE_MAX_TOKENS, model=model)
                return _coerce_converse(full["input"])
            except Exception as e:
                print("[converse] LLM error for %s: %r" % (agent_id, e), file=sys.stderr, flush=True)
                return {"say": "", "action": None, "replies": [], "_error": str(e)}

        try:
            out = _BRAIN.converse(req, llm, verbs=self.verbs)
        except Exception as e:
            self._send(200, {"ok": False, "error": str(e),
                             "say": "", "action": None, "replies": []})
            return
        # The say is free; the optional action must still be schema-valid (governance already ran in the
        # brain). Drop an invalid action but keep the spoken line.
        action = out.get("action")
        if action and str(action.get("verb", "")):
            ok, reason = validate_action(action, self.verbs)
            if not ok:
                action = None
        self._send(200, {"ok": True, "say": out.get("say", ""), "action": action,
                         "replies": out.get("replies", []), "verdict": out.get("verdict", "approve")})

    def _decide_one(self, req: dict) -> dict:
        agent_id = str(req.get("agent_id", ""))
        model = str(req.get("model", ""))  # per-agent model selection (empty → the process default MODEL)
        captured = {"prompt": "", "raw": "", "in": 0, "out": 0, "cost": 0.0, "model": model or MODEL}  # play-log

        def llm(prompt: str) -> dict:
            captured["prompt"] = prompt
            if not self.key:
                return {"verb": "idle", "args": {}}
            try:
                full = call_claude_full(prompt, self.key, model=model)
                captured["raw"] = full["text"]
                captured["in"] = full["tokens_in"]
                captured["out"] = full["tokens_out"]
                captured["cost"] = full["cost"]
                captured["model"] = full.get("model", model or MODEL)
                return extract_action(full["text"])
            except Exception as e:
                captured["raw"] = "(LLM error: %s)" % e
                return {"verb": "idle", "args": {}}

        try:
            out = _BRAIN.decide(req, llm, verbs=self.verbs)  # full {verb: [args]} schema
        except Exception as e:
            # Surface the per-agent failure ON the action (_error) so the Godot client logs a
            # sidecar_error and ambient-fills, rather than silently caching an idle as a success.
            return {"action": {"actor": agent_id, "verb": "idle", "args": {}, "_error": str(e)},
                    "verdict": "error", "invariant": None, "reflected": False, "stream_size": 0,
                    "error": str(e)}
        ok, reason = validate_action(out["action"], self.verbs)
        if not ok:
            out["action"] = {"actor": agent_id, "verb": "idle", "args": {}, "_invalid": reason}
        # Memory text never leaves the process by default (SPEC's "memory stays server-side"): the
        # retrieved snippets are returned only when explicitly tracing.
        if not os.environ.get("TINGEN_DECIDE_LOG"):
            out.pop("retrieved", None)
        # Decision trace (verb/verdict only — never memory text or the key): lets a headless game run
        # prove the brain path is live. Off unless TINGEN_DECIDE_LOG is set.
        if os.environ.get("TINGEN_DECIDE_LOG"):
            a = out["action"]
            at_rite = bool(req.get("world_state", {}).get("actor_at_rite_site"))
            room = req.get("perception", {}).get("room", "")
            print(f"[decide] {agent_id:>18} room={room:<16} -> {a.get('verb',''):<18}"
                  f" verdict={out.get('verdict','')} at_rite={at_rite} mem={out.get('stream_size')}",
                  file=sys.stderr, flush=True)
            # Attach the exact prompt + raw LLM reply so the Godot play-log can record them at the
            # bottom of the transcript. Only under verbose logging — never in production.
            out["action"]["_prompt"] = captured["prompt"]
            out["action"]["_llm_response"] = captured["raw"]
            out["action"]["_tokens_in"] = captured["in"]
            out["action"]["_tokens_out"] = captured["out"]
            out["action"]["_cost"] = captured["cost"]
            out["action"]["_model"] = captured["model"]
        return out


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
