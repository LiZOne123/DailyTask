from __future__ import annotations

import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional


APP_NAME = "DailyTask"
DB_NAME = "dailytask.db"


@dataclass(frozen=True)
class TaskRecord:
    text: str
    done: bool
    pinned: bool


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


def get_db_path() -> Path:
    return get_app_data_dir() / DB_NAME


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_date TEXT NOT NULL,
                position INTEGER NOT NULL,
                text TEXT NOT NULL,
                done INTEGER NOT NULL,
                pinned INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_date_pos ON tasks(task_date, position)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                api_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def load_tasks_for_date(task_date: date) -> List[TaskRecord]:
    init_db()
    iso = task_date.isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT text, done, pinned FROM tasks WHERE task_date = ? ORDER BY position ASC",
            (iso,),
        ).fetchall()

    if rows:
        return [TaskRecord(r["text"], bool(r["done"]), bool(r["pinned"])) for r in rows]

    migrated = _migrate_tasks_from_json(task_date)
    if migrated:
        save_tasks_for_date(task_date, migrated)
        return list(migrated)
    return []


def save_tasks_for_date(task_date: date, tasks: Iterable[TaskRecord]) -> None:
    init_db()
    iso = task_date.isoformat()
    items = list(tasks)
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE task_date = ?", (iso,))
        conn.executemany(
            "INSERT INTO tasks (task_date, position, text, done, pinned) VALUES (?, ?, ?, ?, ?)",
            [
                (iso, idx, t.text, int(bool(t.done)), int(bool(t.pinned)))
                for idx, t in enumerate(items)
            ],
        )


def load_api_key() -> Optional[str]:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT api_key FROM api_keys WHERE id = 1"
        ).fetchone()
    if row and isinstance(row["api_key"], str) and row["api_key"].strip():
        return row["api_key"].strip()

    legacy = _load_api_key_from_json()
    if legacy:
        save_api_key(legacy)
    return legacy


def save_api_key(api_key: str) -> None:
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO api_keys (id, api_key, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET api_key = excluded.api_key, updated_at = excluded.updated_at",
            (api_key, now),
        )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_tasks_from_json(task_date: date) -> List[TaskRecord]:
    iso = task_date.isoformat()
    candidates = [
        get_archive_dir() / f"{iso}.json",
        _get_legacy_archive_dir() / f"{iso}.json",
    ]
    for path in candidates:
        tasks = _read_tasks_from_json(path)
        if tasks:
            return tasks
    return []


def _read_tasks_from_json(path: Path) -> List[TaskRecord]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        import json

        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: List[TaskRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        done = item.get("done", False)
        pinned = item.get("pinned", False)
        if isinstance(text, str):
            out.append(TaskRecord(text=text, done=bool(done), pinned=bool(pinned)))
    return out


def _load_api_key_from_json() -> Optional[str]:
    api_key_path = get_api_key_path()
    if not api_key_path.exists():
        return None
    try:
        raw = api_key_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        import json

        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    key = data.get("api_key") if isinstance(data, dict) else None
    return key.strip() if isinstance(key, str) and key.strip() else None


def _get_legacy_archive_dir() -> Path:
    return Path(__file__).resolve().parent / "archive"
