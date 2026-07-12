"""Unit tests for the sidecar's /narrate route (GM digest narration).

    python3 test_narrate_route.py

Follows test_converse_route.py's pattern: pure-function checks with call_claude_full
monkeypatched, so no network and no key are ever needed.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sidecar  # noqa: E402

_passed = 0
_failed = 0


def check(cond: bool, label: str) -> None:
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def main() -> int:
    calls: list = []

    def fake_call_claude_full(prompt: str, key: str, max_tokens: int = 0, model: str = "") -> dict:
        calls.append({"prompt": prompt, "key": key, "max_tokens": max_tokens, "model": model})
        return {"text": "  The crypt stirs as Dalia descends.  ", "tokens_in": 10,
                "tokens_out": 20, "cost": 0.0, "model": model or "default-model"}

    real = sidecar.call_claude_full
    sidecar.call_claude_full = fake_call_claude_full
    try:
        # A normal digest: the LLM is called, the prompt carries the event lines + world state,
        # and the model from the request is passed through.
        events = ['Dalia moved from the city to the cathedral crypt.',
                  'Voss: "The hour is close."']
        r = sidecar.narrate_reply(
            {"events": events, "world": {"beat": 42, "phase": "night", "pressures": {"panic": 10}},
             "model": "claude-sonnet-4-6"}, "k")
        check(r["ok"] is True, "narrate replies ok")
        check(r["summary"] == "The crypt stirs as Dalia descends.", "summary is the trimmed LLM text")
        check(r["model"] == "claude-sonnet-4-6", "reply reports the model used")
        check(len(calls) == 1, "exactly one LLM call for a non-empty digest")
        check(calls[0]["model"] == "claude-sonnet-4-6", "request model reaches call_claude_full")
        prompt = calls[0]["prompt"]
        check(all(e in prompt for e in events), "prompt contains every event line")
        check('"beat": 42' in prompt and '"phase": "night"' in prompt,
              "prompt contains the world state")
        check("game master" in prompt and "2-4 sentences" in prompt,
              "prompt carries the GM narrator persona")

        # Empty events -> {"summary": ""} WITHOUT calling the LLM.
        calls.clear()
        r2 = sidecar.narrate_reply({"events": [], "world": {}, "model": ""}, "k")
        check(r2["ok"] is True and r2["summary"] == "", "empty events short-circuit to empty summary")
        check(len(calls) == 0, "empty events never call the LLM")

        # Whitespace-only lines count as empty too.
        r3 = sidecar.narrate_reply({"events": ["   ", ""]}, "k")
        check(r3["summary"] == "" and len(calls) == 0, "whitespace-only events also short-circuit")

        # No key (offline sidecar) -> empty summary, no call; the panel keeps its digest.
        r4 = sidecar.narrate_reply({"events": ["something happened"]}, "")
        check(r4["ok"] is True and r4["summary"] == "" and len(calls) == 0,
              "missing key degrades to empty summary without an LLM call")

        # An LLM failure degrades to ok:false + empty summary — never raises.
        def boom(prompt: str, key: str, max_tokens: int = 0, model: str = "") -> dict:
            raise RuntimeError("api down")

        sidecar.call_claude_full = boom
        r5 = sidecar.narrate_reply({"events": ["something happened"]}, "k")
        check(r5["ok"] is False and r5["summary"] == "", "LLM failure degrades to empty summary")
    finally:
        sidecar.call_claude_full = real

    print(f"\n=== {_passed} passed, {_failed} failed ===")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
