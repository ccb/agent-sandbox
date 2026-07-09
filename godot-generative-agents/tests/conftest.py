"""Make the godot-generative-agents modules importable in tests."""

import sys
from pathlib import Path

# Add the penn backend dir to sys.path so imports like
# `from penn_world import ...` work inside serve_penn.py
penn_dir = Path(__file__).resolve().parent.parent / "backend" / "penn"
sys.path.insert(0, str(penn_dir))
