import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("AI_FILM_DATA", ROOT / "runtime_data")).resolve()
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "film_factory.sqlite3"

@contextmanager
def connect():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, story TEXT NOT NULL,
          minutes INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'planned', characters TEXT NOT NULL,
          shots TEXT NOT NULL, final_video TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
          step TEXT NOT NULL, current INTEGER NOT NULL DEFAULT 0,
          total INTEGER NOT NULL DEFAULT 0, preview_seconds INTEGER NOT NULL,
          created TEXT NOT NULL, updated TEXT NOT NULL, error TEXT,
          FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
          created TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS character_library (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
          costume TEXT NOT NULL DEFAULT '', voice TEXT NOT NULL DEFAULT '',
          image_filename TEXT, created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_workflows (
          project_id TEXT PRIMARY KEY, data TEXT NOT NULL,
          updated TEXT NOT NULL,
          FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        ''')
