"""Make the repo root importable when pytest chooses ``tests/`` as its root.

This keeps local source imports working no matter where pytest is invoked from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
