"""Predict, offline, whether Anthropic prompt caching (#367) will actually fire.

Prompt caching only kicks in when the *stable prefix* of a request — the part
marked ``cache_control: {"type": "ephemeral"}`` — is at least the model's
minimum cacheable length. Below that floor the marker is silently ignored: no
error, ``cache_creation_input_tokens`` stays 0, and every call pays full price.
For an agent, that stable prefix is the system message (persona + rules) plus
the tool schema; the per-turn observation renders *after* it and never caches.

This script renders each persona's cacheable prefix from the world YAML,
estimates its token count, and prints a go/no-go table against the model's
floor — so you can tell before spending a cent whether caching will do anything
on this cast. It's the offline half of the caching check; the live half is
watching the ``cache_creation``/``cache_read`` columns in ``serve_penn``'s
request monitor and ``GET /usage`` during a ``--brain llm`` run.

``--live`` closes the loop: it makes two real calls through the production
``AnthropicClient`` path (the one #367 wired ``cache_control`` into) on a prefix
padded past the floor, and asserts call 1 *writes* the cache and call 2 *reads*
it — proving the wiring fires end-to-end, independent of how terse the real
cast happens to be.

Usage (from the repo root)::

    # Fast, offline, no key — ~4-chars/token heuristic:
    uv run python godot-generative-agents/backend/penn/cache_prefix_check.py

    # Exact counts via the free token-counting endpoint (needs ANTHROPIC_API_KEY):
    uv run python godot-generative-agents/backend/penn/cache_prefix_check.py --accurate

    # Prove the caching wiring fires (2 real Haiku calls, ~1-2 cents, needs a key):
    uv run python .../cache_prefix_check.py --live

    # Point at a different world file:
    uv run python .../cache_prefix_check.py --world path/to/world.yaml
"""

from __future__ import annotations

import argparse
import json
import os

from text_adventure_games.npc import LLMAgent, build_choose_action_tool

from backend.build_world import load_world_yaml

# The world file serve_penn.py loads by default.
_DEFAULT_WORLD = os.path.join(os.path.dirname(__file__), "world_data_upenn.yaml")

# The minimum cacheable prefix, in tokens, per model family (from Anthropic's
# prompt-caching docs). A prefix shorter than this silently won't cache. We
# match on a substring of the model id and fall back to the most common (and
# most conservative) 4096 floor for anything unrecognized.
_MODEL_MIN_TOKENS = {
    "haiku-4-5": 4096,
    "opus-4": 4096,
    "sonnet-5": 2048,
    "sonnet-4-6": 2048,
    "fable-5": 2048,
    "sonnet-4-5": 1024,
}
_DEFAULT_MIN_TOKENS = 4096

# A representative command set for the tool enum. The tool schema is a small,
# roughly fixed slice of the prefix (a few hundred chars), so the exact verb
# list barely moves the total — the persona/rules text dominates.
_SAMPLE_VERBS = [
    "travel",
    "perform",
    "go",
    "get",
    "drop",
    "look",
    "examine",
    "give",
    "open",
    "close",
    "read",
    "eat",
    "drink",
    "sit",
    "wait",
    "talk to",
]


def min_tokens_for(model: str) -> int:
    """The cacheable-prefix floor for *model* (substring match, else default)."""
    for needle, floor in _MODEL_MIN_TOKENS.items():
        if needle in model:
            return floor
    return _DEFAULT_MIN_TOKENS


def cacheable_prefix(persona: str) -> tuple[str, dict]:
    """The two pieces that carry the cache_control marker: the system message
    (persona + rules) and the choose_action tool schema. The per-turn
    observation is deliberately excluded — it renders after the prefix and is
    never cached."""
    # llm_client is unused by the system-message renderer, so a placeholder is
    # fine — we only want the rendered text, not a live decision.
    agent = LLMAgent(lambda _prompt: None, persona=persona)
    return agent._structured_system_message(), build_choose_action_tool(_SAMPLE_VERBS)


def estimate_tokens(system: str, tool: dict) -> int:
    """Offline ~4-chars-per-token estimate of the cacheable prefix size."""
    return (len(system) + len(json.dumps(tool))) // 4


def count_tokens(client, model: str, system: str, tool: dict) -> int:
    """Exact prefix size via the (free) token-counting endpoint. Counts tools +
    system together — the order the API renders and caches them — plus a
    one-token placeholder user turn the endpoint requires."""
    resp = client.messages.count_tokens(
        model=model,
        system=system,
        tools=[
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
        ],
        messages=[{"role": "user", "content": "x"}],
    )
    return resp.input_tokens


# A fixed, byte-identical filler sentence. --live repeats it to pad the stable
# system prefix past the model floor; because it never varies, the cached prefix
# stays byte-identical across the two calls (a single changed byte would
# invalidate the cache and mask a real write→read).
_FILLER_UNIT = (
    "\n(cache-prefix-check filler: this stable sentence pads the system prefix "
    "past the model's minimum cacheable length so prompt caching engages.)"
)


def _padded_system(system: str, target_tokens: int) -> str:
    """Append :data:`_FILLER_UNIT` until *system* clears *target_tokens* (by the
    ~4-chars/token heuristic). Returns *system* unchanged if it's already big
    enough."""
    needed_chars = target_tokens * 4
    if len(system) >= needed_chars:
        return system
    reps = (needed_chars - len(system)) // len(_FILLER_UNIT) + 1
    return system + _FILLER_UNIT * reps


def verify_live(model: str, floor: int, persona: str) -> int:
    """Two real ``call_tools`` calls through the production ``AnthropicClient``
    path, on a prefix padded past *floor*, asserting call 1 writes the cache and
    call 2 reads it. Returns 0 on PASS, 1 on FAIL. Costs ~2 cheap calls."""
    from text_adventure_games.llm_client import AnthropicClient, LlmConfig

    system, tool = cacheable_prefix(persona)
    # Pad the stable system prefix comfortably past the floor so caching engages
    # regardless of how terse the real cast is. This verifies the *wiring*; the
    # offline table (without --live) is what reports the real cast's prefix size.
    system = _padded_system(system, floor + 512)
    print(
        f"model: {model}   floor: {floor} tokens   "
        f"padded prefix: ~{estimate_tokens(system, tool)} tokens (est.)\n"
    )

    client = AnthropicClient(LlmConfig(provider="anthropic", model=model))
    usages = []
    for i in (1, 2):
        before = len(client.ledger.records)
        # System prefix + tool are byte-identical across both calls; only the
        # user turn (after the cache breakpoint) varies, which never caches.
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Reply with one short word. (probe {i})"},
        ]
        client.call_tools(messages, [tool], tool_choice="auto", max_tokens=16)
        if len(client.ledger.records) == before:
            print(
                f"  call {i}: FAILED — no response recorded. Check "
                "ANTHROPIC_API_KEY, the model id, and network."
            )
            return 1
        u = client.ledger.records[-1].usage
        usages.append(u)
        print(
            f"  call {i}: input={u.input_tokens:<6} "
            f"cache_write={u.cache_creation_input_tokens:<7} "
            f"cache_read={u.cache_read_input_tokens:<7}"
        )

    wrote = usages[0].cache_creation_input_tokens > 0
    read = usages[1].cache_read_input_tokens > 0
    print()
    if wrote and read:
        print("PASS: call 1 wrote the cache, call 2 read it — #367 wiring fires.")
        return 0
    print(
        "FAIL: expected call 1 cache_write>0 and call 2 cache_read>0. All zeros "
        "means the prefix didn't clear the floor (the estimate can lag the exact "
        "count — raise the pad target) or caching isn't taking effect."
    )
    return 1


def _require_anthropic(flag: str):
    """Import the anthropic SDK and confirm a key is set, or print why *flag*
    can't run and return None."""
    try:
        import anthropic
    except ImportError:
        print(f"{flag} needs the anthropic package (uv sync --extra llm).")
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"{flag} needs ANTHROPIC_API_KEY (put it in the repo-root .env).")
        return None
    return anthropic


def _load_env() -> None:
    """Fold the repo-root ``.env`` into ``os.environ`` before the key checks,
    like every other backend CLI (see ``.env.example`` / ``backend/env.py``).
    Best-effort: the offline table must still run if ``backend`` isn't importable
    or there's no ``.env``. An already-exported key always wins."""
    import sys

    gga = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if gga not in sys.path:
        sys.path.insert(0, gga)
    try:
        from backend.env import load_dotenv

        load_dotenv()
    except Exception:
        pass


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--world",
        default=_DEFAULT_WORLD,
        help="path to the world YAML (default: world_data_upenn.yaml)",
    )
    parser.add_argument(
        "--accurate",
        action="store_true",
        help="use the token-counting endpoint instead of the "
        "char heuristic (needs ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="make 2 real calls through AnthropicClient on a padded-above-floor "
        "prefix and assert cache write→read (needs ANTHROPIC_API_KEY; ~2 cheap "
        "calls). Proves the #367 wiring fires; skips the offline table.",
    )
    args = parser.parse_args()

    data = load_world_yaml(args.world)
    personas = [p for p in (data.get("personas") or []) if p and p.get("persona")]
    if not personas:
        print(
            f"No active personas in {args.world} (empty cast: list, or persona "
            "files missing their persona: field?)."
        )
        return 1

    model = str((data.get("llm") or {}).get("model", "claude-haiku-4-5"))
    floor = min_tokens_for(model)

    if args.live:
        if _require_anthropic("--live") is None:
            return 1
        return verify_live(model, floor, personas[0]["persona"])

    client = None
    if args.accurate:
        anthropic = _require_anthropic("--accurate (token counting is free)")
        if anthropic is None:
            return 1
        client = anthropic.Anthropic()

    mode = "exact (count_tokens)" if client else "~4 chars/token estimate"
    print(f"model: {model}   cacheable-prefix floor: {floor} tokens   [{mode}]\n")
    header = f"{'persona':<22}{'prefix tokens':>15}   caches?"
    print(header)
    print("-" * len(header))

    any_caches = False
    for p in personas:
        system, tool = cacheable_prefix(p["persona"])
        tokens = (
            count_tokens(client, model, system, tool)
            if client
            else estimate_tokens(system, tool)
        )
        caches = tokens >= floor
        any_caches = any_caches or caches
        verdict = "YES" if caches else "no (silent no-op)"
        print(f"{p['name']:<22}{tokens:>15}   {verdict}")

    print()
    if any_caches:
        print(
            "At least one persona clears the floor — expect nonzero "
            "cache_creation/cache_read on a live --brain llm run."
        )
    else:
        print(
            f"Every prefix is below {floor} tokens, so cache_control is a "
            "silent no-op: caching is wired in but dormant. To make it fire, "
            "grow the stable prefix (richer personas, or a shared world/rules "
            "preamble in the system block) past the floor. Run --live to confirm "
            "the wiring fires once a prefix does clear the floor."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
