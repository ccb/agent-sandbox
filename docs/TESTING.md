# Testing the agent layer

The agent layer (LLM client, `LlmParser`, ReAct NPCs) normally talks to OpenAI or Anthropic. For **offline, deterministic tests** use **`MockLlmClient`** from `text_adventure_games.llm_client`. It implements the same `LlmClient` protocol as the real adapters: no API key, no network, no SDK.

## Quick start

```python
from text_adventure_games.llm_client import MockLlmClient

mock = MockLlmClient(["go north"])
assert mock.chat([{"role": "user", "content": "what do you do?"}]) == "go north"
```

Run the reference suites:

```bash
uv run pytest tests/test_agent_layer.py -v      # unit patterns: parser + NPC behaviors
uv run pytest tests/test_react_live_game.py -v  # ReAct NPCs vs the real Action Castle game
```

The first file shows end-to-end patterns for the parser and NPC behaviors; the
second runs the full Observe → Decide → Act → Reflect loop against the live game.

## Response modes

### Scripted queue (FIFO)

Pass a list of strings (or `None`). Each `chat()` call consumes the next entry; when the list is empty, `chat()` returns `default`.

```python
client = MockLlmClient(["one", "two"], default="DONE")
client.chat([])  # -> "one"
client.chat([])  # -> "two"
client.chat([])  # -> "DONE"
```

Use this for ReAct NPCs that issue one command per turn, or retries across multiple `chat()` calls:

```python
from text_adventure_games.npc import make_react_behavior

troll.set_behavior(make_react_behavior(MockLlmClient(["go south", "go north"])))
```

### Callable responder

Pass a function `(messages, max_tokens, temperature) -> str | None` when the reply should depend on the prompt (for example, picking a numbered option from the system message):

```python
def pick_first(messages, max_tokens, temperature):
    return "0"

client = MockLlmClient(pick_first)
```

`tests/test_agent_layer.py` includes `pick_option_containing(keyword)`, which scans numbered lines in the system message and returns the matching index—the same shape of answer `LlmParser` expects when it asks the model to “return just the number.”

### The mock ReAct brain (`MockReActClient`)

For driving the **whole game** rather than a single test, `MockReActClient` (registered as provider `"mock"`) is a callable-responder client with Action Castle rules built in: it reads the agent's system message (persona + goals) and observation, and picks an in-character command — escalating from the NPC's own action history, standing down when the player leaves, and demonstrating the Reflect step by first issuing an `attack` that fails `check_preconditions()`. It replies in the same labeled two-line format a real model is instructed to use (`Reasoning: ...` / `Action: ...`), so the ReAct loop traces every decision with explicit `[reasoning]`/`[action]` labels (via `parser.npc_log`, which stays out of `command_history`). Because it is a real registered provider, `LLM_PROVIDER=mock` exercises the live terminal game and webapp at no cost:

```bash
LLM_PROVIDER=mock uv run python -m notebooks.hw1_llm.play           # pure ReAct NPCs
LLM_PROVIDER=mock uv run python -m text_adventure_games.webapp.app  # hybrid NPCs + LLM parser
```

It inherits `calls` recording from `MockLlmClient`, so tests can assert on the exact prompts the agents sent (see `tests/test_react_live_game.py`).

## Simulating failures

Return **`None`** from `chat()` (via `default=None`, a queued `None`, or the callable) to mimic an API error. Parser and NPC code should fall back gracefully (for example, narration keeps the original text, hybrid behaviors run scripted logic).

```python
MockLlmClient(default=None)
```

## Asserting on prompts

Every `chat()` call is appended to **`client.calls`**, each entry a dict with `messages`, `max_tokens`, and `temperature`. Use this to verify the LLM was (or was not) invoked:

```python
mock = MockLlmClient(default="SHOULD NOT BE CALLED")
game.set_parser(WebLlmParser(game, mock))
game.parser.determine_intent("go north")  # keyword path
assert mock.calls == []
```

## Where to plug it in

| Component | Typical wiring |
|-----------|----------------|
| **Parser** | `WebLlmParser(game, mock)` — keyword matches skip the LLM; ambiguous commands call `mock.chat()`. |
| **ReAct NPC** | `make_react_behavior(mock)` — mock returns a game command string each turn. |
| **Hybrid NPC** | `make_hybrid_behavior(mock, scripted_fn)` — tries ReAct first; if `mock` returns `None`, runs `scripted_fn`. |

Production code uses `create_llm_client(LlmConfig(...))` instead; tests swap in `MockLlmClient` at the same injection points.

## Further reading

- Implementation and docstring examples: `text_adventure_games/llm_client.py` (`MockLlmClient`)
- Full worked tests: `tests/test_agent_layer.py`
