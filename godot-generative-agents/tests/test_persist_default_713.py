"""serve_penn's --persist defaults on (#713).

Both live frontends (Godot viewer + web companion) connect through
serve_penn; a run you forgot to flag was unrecoverable. Now every run is
durable unless you opt out with --no-persist (BooleanOptionalAction gives
that flag for free). Pins the CLI default via the parser seam, offline --
no server boot, no real runs/ dir touched.
"""

import sys
from pathlib import Path

# The Penn sim modules live in the Godot tree and are run as scripts (no
# package); tests import them the way the scripts import each other -- off the
# sim directory itself.
_SIM_DIR = (
    Path(__file__).resolve().parents[2] / "godot-generative-agents" / "backend" / "penn"
)
sys.path.insert(0, str(_SIM_DIR))

from serve_penn import _build_parser  # noqa: E402


def test_persist_defaults_on():
    args = _build_parser().parse_args([])
    assert args.persist is True


def test_no_persist_opts_out():
    args = _build_parser().parse_args(["--no-persist"])
    assert args.persist is False


def test_persist_flag_is_still_accepted():
    # Back-compat no-op alias for existing docs/commands that already say
    # --persist explicitly.
    args = _build_parser().parse_args(["--persist"])
    assert args.persist is True
