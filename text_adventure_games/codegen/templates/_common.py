"""Shared helpers used by every template emitter.

Lives in its own module so ``actions.py`` and ``blocks.py`` can import from
it without triggering circular imports through ``templates/__init__.py``
(which builds the registry by importing both).
"""

from __future__ import annotations


def python_class_name(id_: str) -> str:
    """Turn a spec id or name into a Python class name (Title_Case).

    Matches the convention in ``notebooks/hw1_solution/action_castle.py``:
    ``read_runes`` -> ``Read_Runes``, ``ghost_touch`` -> ``Ghost_Touch``.
    Any non-alphanumeric character (space, hyphen, etc.) is a separator,
    so block names like ``"troll blocking bridge"`` become
    ``Troll_Blocking_Bridge`` rather than passing spaces through.
    """
    parts = []
    current = []
    for ch in id_:
        if ch.isalnum():
            current.append(ch)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    name = "_".join(p.capitalize() for p in parts)
    if not name:
        return "Unnamed"
    if name[0].isdigit():
        name = "_" + name
    return name


def q(s) -> str:
    """Repr a value for safe embedding as a Python literal."""
    return repr(s)


def py_value(v) -> str:
    """Render a Python literal for a primitive (bool, str, int, None)."""
    if isinstance(v, bool):
        return "True" if v else "False"
    if v is None:
        return "None"
    return repr(v)


def safe_var(s: str) -> str:
    """Turn a name like 'Garden Path' into a Python identifier 'garden_path'."""
    out = []
    prev_us = False
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append("_")
                prev_us = True
    return "".join(out).strip("_") or "thing"


def humanize_property(prop: str) -> str:
    """Render a property name for an in-game message.

    ``is_royal`` -> ``royal``; ``is_crowned`` -> ``crowned``;
    ``emotional_state`` -> ``emotional state``. The point is to surface
    *why* a precondition failed in language the player understands,
    rather than a raw property identifier.
    """
    if prop.startswith("is_"):
        return prop[3:].replace("_", " ")
    return prop.replace("_", " ")


def safe_factory_name(s: str) -> str:
    """Lowercase identifier for use in factory function names."""
    out = []
    for ch in s.lower():
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "unnamed"
