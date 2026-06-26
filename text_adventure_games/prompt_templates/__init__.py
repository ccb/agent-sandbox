"""In-repo prompt management for the engine's LLM calls (issue #145).

Each prompt lives as a ``.prompty`` file next to this module: YAML frontmatter
(name, description, documented inputs, and a sample) followed by a Jinja2
template body. Keeping prompts *here* -- in the codebase, under version
control -- means a prompt is one reviewable artifact you can diff in a pull
request, not an f-string scattered across a function. There is deliberately no
external prompt database or hosted service: a prompt change is a normal code
change.

We use the `prompty <https://prompty.ai>`_ library to load the files and the
Jinja2 templating it ships with to render them. We only need the *render* step
(template + inputs -> text). We deliberately do **not** use
``prompty.prepare``/``execute``: those additionally parse the rendered text into
chat messages and call a model, but the engine already builds its own messages
and owns its LLM client (see ``llm_client.py``). So this module renders a prompt
to a plain string and hands it back to the caller unchanged.

Usage::

    from text_adventure_games import prompt_templates

    system = prompt_templates.render(
        "npc_decision",
        persona="I am the troll. I guard the drawbridge.",
        goals_block="",
        include_instruction=True,
        reasoning_label="Reasoning:",
        action_label="Action:",
        duration_label="Duration:",
    )
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import prompty
from prompty.invoker import InvokerFactory

# Prompts live alongside this module, so `pip install` / `uv sync` ship them
# with the package (see [tool.setuptools.package-data] in pyproject.toml).
_PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _load(name: str) -> prompty.core.Prompty:
    """Load and cache the parsed ``<name>.prompty`` file.

    Raises ``FileNotFoundError`` with the list of available templates when the
    name is unknown -- a typo'd prompt name fails loudly at the call site
    instead of silently rendering nothing.
    """
    path = _PROMPTS_DIR / f"{name}.prompty"
    if not path.is_file():
        available = sorted(p.stem for p in _PROMPTS_DIR.glob("*.prompty"))
        raise FileNotFoundError(
            f"No prompt template named {name!r} in {_PROMPTS_DIR}. "
            f"Available: {', '.join(available) or '(none)'}."
        )
    return prompty.load(str(path))


def render(name: str, /, **variables) -> str:
    """Render the ``<name>.prompty`` template with *variables* and return the
    resulting prompt string.

    Variables the template does not reference are ignored; template variables
    left unset render as empty (Jinja's default). The engine's optional prompt
    sections rely on that: an absent persona or an empty goal list simply drops
    its line rather than printing a blank one (the templates use ``{%- ... -%}``
    whitespace trimming to keep the output free of stray blank lines).
    """
    prompt = _load(name)
    return InvokerFactory.run_renderer(prompt, variables, prompt.content)
