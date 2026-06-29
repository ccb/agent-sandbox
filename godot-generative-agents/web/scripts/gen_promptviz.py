"""Precompute the prompt-chain visualizer's data as static JSON for the web app.

`promptviz` (text_adventure_games/promptviz) is normally a small Flask app that
builds a chain's DAG + per-node prompts *offline* (no LLM call). The Godot web
companion is a static site, so rather than run Flask we dump the same JSON here
and the React "Prompt chains" view renders it. This mirrors app.py's /chains,
/graph.json and /prompt responses; the optional run-overlay (the only piece that
needs a recorded run) is dropped.

It also dumps a flat prompts.json catalog of every .prompty template (both
template packages) for the "Prompts" reader view — name, description, declared
inputs, rendered example, and raw source.

Re-run via `pnpm gen:promptviz` whenever a chain spec or its .prompty templates
change. The per-chain files, a chains.json index, and prompts.json all land in
public/promptviz/.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    """Walk up to the agent-sandbox checkout (holds both engine + backend pkgs)."""
    for p in (start, *start.parents):
        if (p / "pyproject.toml").exists() and (p / "text_adventure_games").is_dir():
            return p
    raise RuntimeError("could not locate the repo root from %s" % start)


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
# Put the repo root on the path so `backend.prompt_templates` (used by the
# smallville chain) imports even when this script is run by file path.
sys.path.insert(0, str(REPO_ROOT))

from text_adventure_games.promptviz.app import _graph_elements  # noqa: E402
from text_adventure_games.promptviz.spec import ChainSpec, load_spec  # noqa: E402
from text_adventure_games.promptviz.templates import node_prompt  # noqa: E402

# Chain specs to dump. action_castle ships inside promptviz; smallville lives
# with the generative-agents backend.
SPECS = [
    REPO_ROOT / "text_adventure_games" / "promptviz" / "chains" / "action_castle.yaml",
    REPO_ROOT / "backend" / "promptviz_chains" / "smallville.yaml",
]
# Template packages to catalog for the Prompts reader. Each exposes render() and
# holds its .prompty files alongside its __init__.
PACKAGES = [
    "text_adventure_games.prompt_templates",
    "backend.prompt_templates",
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
        "elements": _graph_elements(spec, None),
        "prompts": {n.id: _prompt_detail(spec, n) for n in spec.nodes},
    }


def _catalog_entry(template: str, pkg_name: str) -> dict:
    """One row of the flat prompt catalog: frontmatter + rendered + source."""
    detail = node_prompt(template, None, pkg_name)
    fm = detail.get("frontmatter") or {}
    return {
        "template": template,
        "package": pkg_name,
        "name": fm.get("name") or template,
        "description": " ".join((fm.get("description") or "").split()),
        "inputs": fm.get("inputs") or {},
        "rendered": detail.get("rendered"),
        "raw_source": detail.get("raw_source"),
        "error": detail.get("error"),
    }


def dump_catalog() -> list:
    """Every .prompty template across PACKAGES, rendered with its own sample."""
    entries = []
    for pkg_name in PACKAGES:
        pkg_file = importlib.import_module(pkg_name).__file__
        assert pkg_file is not None, f"{pkg_name} has no __file__"
        for prompty_file in sorted(Path(pkg_file).parent.glob("*.prompty")):
            entries.append(_catalog_entry(prompty_file.stem, pkg_name))
    return entries


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

    catalog = dump_catalog()
    (OUT_DIR / "prompts.json").write_text(
        json.dumps({"prompts": catalog}, indent=2) + "\n"
    )
    print(f"==> catalog: {len(catalog)} prompt templates -> prompts.json")


if __name__ == "__main__":
    main()
