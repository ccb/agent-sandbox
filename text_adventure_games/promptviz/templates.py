"""Read a chain node's prompt template -- offline, never calling a model.

For one node this returns the template's frontmatter (name, description,
declared inputs), the raw ``.prompty`` body, and a rendered example. The example
is produced by the templates package's own ``render()``, so the preview is
byte-identical to what the engine would send the model.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache(maxsize=None)
def _load_pkg(pkg_name: str) -> ModuleType:
    pkg = importlib.import_module(pkg_name)
    if not hasattr(pkg, "render"):
        raise AttributeError(f"templates package {pkg_name!r} has no render() function")
    return pkg


def node_prompt(template: str, example_vars: dict | None, pkg_name: str) -> dict:
    """Return prompt detail for one node's template.

    On success: ``{frontmatter, raw_source, rendered}``. On any problem (unknown
    package/template, malformed frontmatter, render error): a dict with a
    human-readable ``error`` key (plus whatever detail was recovered) -- callers
    surface this in the UI rather than 500-ing.

    ``example_vars=None`` falls back to the template's own ``sample`` block, so a
    spec node usually needs no ``example_vars`` of its own.
    """
    # Imported lazily so importing this module doesn't hard-require prompty.
    import prompty

    try:
        pkg = _load_pkg(pkg_name)
    except Exception as exc:
        return {"error": f"templates package {pkg_name!r} unavailable: {exc}"}

    path = Path(pkg.__file__).parent / f"{template}.prompty"
    if not path.exists():
        return {"error": f"template {template!r} not found in {pkg_name}"}

    try:
        p = prompty.load(str(path))
    except Exception as exc:
        return {"error": f"could not load template {template!r}: {exc}"}

    inputs = getattr(p, "inputs", {}) or {}
    sample = getattr(p, "sample", None) or {}
    frontmatter = {
        "name": p.name,
        "description": p.description,
        "model_api": getattr(getattr(p, "model", None), "api", "") or "",
        "inputs": {
            k: {
                "type": getattr(v, "type", None),
                "description": getattr(v, "description", "") or "",
            }
            for k, v in inputs.items()
        },
        "sample": sample,
    }

    variables = sample if example_vars is None else example_vars
    try:
        rendered = pkg.render(template, **variables)
    except Exception as exc:
        return {
            "frontmatter": frontmatter,
            "raw_source": p.content or "",
            "rendered": None,
            "error": f"render failed: {exc}",
        }

    return {
        "frontmatter": frontmatter,
        "raw_source": p.content or "",
        "rendered": rendered,
    }
