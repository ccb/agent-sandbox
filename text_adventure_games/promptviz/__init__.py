"""Prompt-chain visualizer.

A small, offline web app that draws the DAG of LLM call sites an agent run flows
through, reading the prompts straight from the ``.prompty`` templates -- no model
call required. Each game/app contributes a *chain spec* (see ``chains/*.yaml``);
the same engine renders any of them.

Run it::

    python -m text_adventure_games.promptviz.app            # ships the Action Castle chain
    python -m text_adventure_games.promptviz.app --help      # options (--spec, --runlog, --port)

Public API:

* :func:`~text_adventure_games.promptviz.spec.load_spec` / :class:`ChainSpec`
* :func:`~text_adventure_games.promptviz.templates.node_prompt`
* :func:`~text_adventure_games.promptviz.overlay.load_runlog` / :func:`map_to_chain`
* :func:`~text_adventure_games.promptviz.app.create_app`
"""

from .overlay import Overlay, load_runlog, map_to_chain
from .spec import ChainSpec, Edge, Node, load_spec
from .templates import node_prompt

__all__ = [
    "ChainSpec",
    "Edge",
    "Node",
    "Overlay",
    "load_spec",
    "load_runlog",
    "map_to_chain",
    "node_prompt",
]
