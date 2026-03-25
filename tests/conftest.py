"""Add app/ to sys.path so tests can import app modules directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
