"""Shared pytest setup (Member 5)."""
import sys
from pathlib import Path

# Make "from src...." imports work no matter where pytest is started from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
