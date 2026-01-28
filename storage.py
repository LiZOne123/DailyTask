from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "DailyTask"


def get_app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")

    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_archive_dir() -> Path:
    archive_dir = get_app_data_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def get_api_key_path() -> Path:
    return get_app_data_dir() / "apikey.json"
