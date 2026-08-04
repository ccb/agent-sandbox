"""Precompute the prompt-chain visualizer's data as static JSON for the web app.

The Godot web companion is static, so this script turns the Penn cognition
chain and its prompt templates into JSON during development. The React figure
then renders the same data without a Python server or an LLM call.

Re-run via `pnpm gen:promptviz` whenever a chain spec or its .prompty templates
change. The per-chain files and a chains.json index land in public/promptviz/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up to the repository root (which holds engine and backend packages)."""
    for p in (start, *start.parents):
        if (p / "pyproject.toml").exists() and (p / "text_adventure_games").is_dir():
            return p
    raise RuntimeError("could not locate the repo root from %s" % start)


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
# Put the repo root on the path so `backend.prompt_templates` (used by the
# cognition chain) imports even when this script is run by file path.
sys.path.insert(0, str(REPO_ROOT))

from text_adventure_games.promptviz.graph import graph_elements  # noqa: E402
from text_adventure_games.promptviz.spec import ChainSpec, load_spec  # noqa: E402
from text_adventure_games.promptviz.templates import node_prompt  # noqa: E402

# Chain specs to dump. Only the Penn sim's own cognition chain ships on the site
# -- promptviz also carries an action_castle chain, but that describes the
# text-adventure demo, not this simulation. Run the Flask app against it directly
# if you want to see it.
SPECS = [
    REPO_ROOT
    / "godot-generative-agents"
    / "backend"
    / "promptviz_chains"
    / "cognition.yaml",
]
OUT_DIR = Path(__file__).resolve().parents[1] / "public" / "promptviz"


def _prompt_detail(spec: ChainSpec, node) -> dict:
    """Reproduce app.py's /prompt handler for one node (sans run overlay)."""
    detail = {
        "id": node.id,
        "label": node.label,
        "kind": node.kind,
        "template": node.template,
        "description": " ".join((node.description or "").split()),
    }
    if node.template:
        detail.update(
            node_prompt(node.template, node.example_vars, spec.templates_for(node))
        )
    elif node.kind in ("start", "gate"):
        detail["note"] = "Control point -- no prompt (no LLM call here)."
    else:
        detail["note"] = (
            "No prompt template wired yet for this call site "
            "(e.g. a mock brain that ignores prompts)."
        )
    return detail


def dump_chain(spec_path: Path) -> dict:
    spec = load_spec(spec_path)
    return {
        "chain": spec.name,
        "label": spec.name.replace("_", " ").title(),
        "description": " ".join((spec.description or "").split()),
        "elements": graph_elements(spec),
        "prompts": {n.id: _prompt_detail(spec, n) for n in spec.nodes},
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for spec_path in SPECS:
        chain = dump_chain(spec_path)
        (OUT_DIR / f"{chain['chain']}.json").write_text(
            json.dumps(chain, indent=2) + "\n"
        )
        index.append(
            {
                "id": chain["chain"],
                "label": chain["label"],
                "description": chain["description"],
            }
        )
        n, e = len(chain["elements"]["nodes"]), len(chain["elements"]["edges"])
        print(f"==> {chain['chain']}: {n} nodes, {e} edges")
    (OUT_DIR / "chains.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"==> wrote {len(index)} chain(s) + chains.json to {OUT_DIR}")


if __name__ == "__main__":
    main()
