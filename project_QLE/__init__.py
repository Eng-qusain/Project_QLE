## Project_QLE/project_QLE/__init__.py
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
__path__.insert(0, str(ROOT))
