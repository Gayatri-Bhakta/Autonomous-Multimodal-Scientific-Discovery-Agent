import os
import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

runpy.run_path(str(PROJECT_ROOT / "app.py"), run_name="__main__")
