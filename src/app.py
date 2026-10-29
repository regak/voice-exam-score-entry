"""Application entry point.

Loads config.json and launches the Tkinter desktop UI (src/ui/desktop_app.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python src/app.py` as well as `python -m src.app`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AppConfig
from src.ui.desktop_app import run_app


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    config = AppConfig.load(config_path)
    run_app(config)


if __name__ == "__main__":
    main()
