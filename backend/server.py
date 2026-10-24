"""Vercel entrypoint. The repo root is not the backend package root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.main import app

__all__ = ["app"]
