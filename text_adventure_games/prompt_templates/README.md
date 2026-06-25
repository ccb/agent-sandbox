# Prompt templates

The engine's LLM prompts live here as [Prompty](https://prompty.ai) files
(`.prompty`): YAML frontmatter (name, description, documented inputs, a sample)
followed by a [Jinja2](https://jinja.palletsprojects.com/) template body. Keeping
prompts here — in the codebase, under version control — means a prompt is one
reviewable artifact you can diff in a pull request, not an f-string scattered
across a function. There is deliberately **no external prompt database or hosted
service**: changing a prompt is a normal code change. (Introduced in
[#145](https://github.com/ccb/agent-sandbox/issues/145).)

## How prompts are rendered

`__init__.py` exposes one function:

```python
from text_adventure_games import prompt_templates

text = prompt_templates.render("narrate_fail")
text = prompt_templates.render("match_item", hint="it glows")
```

`render(name, **variables)` loads `<name>.prompty`, renders its Jinja2 body with
`variables`, and returns the resulting string. It uses Prompty's *render* step
only — not `prompty.prepare`/`execute` — because the engine builds its own chat
messages and owns its LLM client (see `llm_client.py`). A variable the template
doesn't reference is ignored; one left unset renders as empty.

## Where each template is used

Each prompt is rendered from exactly one place in the code. **Keep this table in
sync when you add, rename, remove, or re-wire a template.**

| Template | Rendered by | Used for |
| --- | --- | --- |
| `npc_decision.prompty` | `npc.py` — `LLMAgent._render_system()` (via `_system_message()` and `_structured_system_message()`) | The NPC's ReAct decision system message: persona + goals, plus the labeled `Reasoning:`/`Action:`/`Duration:` instruction on the free-text path (omitted on the structured tool-calling path). |
| `npc_dialogue.prompty` | `npc.py` — `LLMAgent._dialogue_system_message()` | The NPC's conversation system message (issue #86): the same persona + goals block as `npc_decision`, plus the one-line dialogue instruction (say the next line in character; bow out with a brief goodbye). |
| `reflect_system.prompty` | `reflection.py` — `LLMReflector._call()` (both reflection steps) | System message for periodic reflection (issue #84): synthesize higher-level insights grounded only in the memories given. The per-call user message (numbered memory window + step instruction) is assembled in code. |
| `narrate_ok.prompty` | `llm_parser.py` — `LlmParser._ok_system_instructions()` (used by `ok()`) | Narrator instructions for a command that succeeded. |
| `narrate_fail.prompty` | `llm_parser.py` — `LlmParser._fail_system_instructions()` (used by `fail()`) | Narrator instructions for a command that failed. |
| `narrate_npc.prompty` | `llm_parser.py` — `LlmParser._npc_system_instructions()` (used by `npc_ok()`) | Narrator instructions for describing an NPC's action. |
| `match_intent.prompty` | `llm_parser.py` — `LlmParser.determine_intent()` (LLM fallback) | Match the player's input to the closest known action. |
| `match_character.prompty` | `llm_parser.py` — `LlmParser._llm_get_character()` | Match a character named in a command. |
| `match_item.prompty` | `llm_parser.py` — `LlmParser._llm_match_item()` | Match an item named in a command. |
| `match_direction.prompty` | `llm_parser.py` — `LlmParser._llm_get_direction()` | Match a movement direction named in a command. |

> Note: this folder is **not** the same as `text_adventure_games/prompts.py`,
> which is the in-game `Prompt` choice mechanism (#110).

## Adding a new prompt

1. Create `your_prompt.prompty` here. Give it frontmatter (`name`,
   `description`, documented `inputs`, a `sample`) and a Jinja2 body. Use
   `{%- ... -%}` whitespace trimming so optional sections don't leave blank
   lines.
2. Render it with `prompt_templates.render("your_prompt", ...)` from the code
   that needs it.
3. **Add a row to the table above** pointing at that call site.
4. Pin its exact output with a test in `tests/test_prompt_templates.py`.
