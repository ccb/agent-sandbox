"""In-repo prompt management for the Smallville port (issue #145).

The generative-agents port drives every persona with a deterministic mock
(``smallville_agents.SmallvilleMockClient``), so there is no live model prompt to
manage here. What there *is* -- and what this package centralizes -- is the
agent's generated **memory and belief text**: the day's plan, the first-person
record of each action it takes, and the places it knows up front. Those strings
used to be inline f-strings in ``smallville_agents.py`` and ``seed.py``; they now
live as ``.prompty`` files next to this module: YAML frontmatter (name,
description, documented inputs, a sample) followed by a Jinja2 template body.

Keeping them *here* -- in the codebase, under version control -- means each one is
a single reviewable artifact you can diff in a pull request, not a string spread
across a function. There is deliberately no external prompt database or hosted
service: changing one is a normal code change. This mirrors the engine's own
``text_adventure_games/prompt_templates/`` package (the other half of #145).

We use the `prompty <https://prompty.ai>`_ library to load the files and the
Jinja2 templating it ships with to render them. We only need the *render* step
(template + inputs -> text). We deliberately do **not** use
``prompty.prepare``/``execute``: those additionally parse the rendered text into
chat messages and call a model, but nothing here calls a model -- the rendered
string is stored straight into the agent's memory/knowledge.

Usage::

    from gen_agents.prompt_templates import render

    plan = render("plan_memory", destination="Hobbs Cafe", activity="tending the cafe counter")
    text = render("reflection", verb="travel", location="Hobbs Cafe")
    belief = render("spatial_knowledge", place="Johnson Park", areas="")
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import prompty
from prompty.invoker import InvokerFactory

# The .prompty files live alongside this module and are read straight from the
# source tree at runtime (gen_agents/ is run as `python -m gen_agents.run_simulation`
# from generative-agents/, not installed as a wheel), so no package-data is
# needed -- unlike the engine package, which ships its templates in a wheel.
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
    resulting string.

    Variables the template does not reference are ignored; template variables
    left unset render as empty (Jinja's default). The optional sections rely on
    that: an empty ``areas`` simply drops the "-- its ..." clause rather than
    printing a blank one (the templates use ``{%- ... -%}`` whitespace trimming
    to keep the output free of stray blank lines and trailing newlines).
    """
    prompt = _load(name)
    return InvokerFactory.run_renderer(prompt, variables, prompt.content)
