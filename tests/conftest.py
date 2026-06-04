"""Make the repo root importable so tests can import `homeworks.*`.

`text_adventure_games` is installed editable, but the `homeworks/` games are
not packaged -- they normally resolve because scripts run from the repo root.
This keeps that working no matter where pytest is invoked from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
