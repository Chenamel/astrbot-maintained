"""Test-local sys.path setup for the maintained tooling.

The tools in ``maintained/tools/`` are importable as ``tools.*`` once the
``maintained`` directory is on ``sys.path``; this mirrors how they are invoked
from the command line.
"""

import sys
from pathlib import Path

MAINTAINED_DIR = Path(__file__).resolve().parents[2] / "maintained"
if str(MAINTAINED_DIR) not in sys.path:
    sys.path.insert(0, str(MAINTAINED_DIR))
