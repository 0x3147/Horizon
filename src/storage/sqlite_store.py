from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        hours INTEGER NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        config_snapshot_json TEXT,
        raw_count INTEGER NOT NULL DEFAULT 0,
        scored_count INTEGER NOT NULL DEFAULT 0,
        filtered_count INTEGER NOT NULL DEFAULT 0,
        enriched_count INTEGER NOT NULL DEFAULT 0,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS items (
        id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        source_type TEXT NOT NULL,
        source_name TEXT,
        native_id TEXT,
        title TEXT NOT NULL,
        url TEXT NOT NULL,
        content TEXT,
        author TEXT,
        published_at TEXT,
        fetched_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        stage TEXT NOT NULL DEFAULT 'raw',
        is_selected INTEGER NOT NULL DEFAULT 0,
        duplicate_of_item_id TEXT,
        PRIMARY KEY (run_id, id),
        FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS item_analysis (
        run_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        ai_score REAL,
        ai_reason TEXT,
        ai_summary TEXT,
        ai_tags_json TEXT NOT NULL DEFAULT '[]',
        detailed_summary_json TEXT NOT NULL DEFAULT '{}',
        background_json TEXT NOT NULL DEFAULT '{}',
        community_discussion_json TEXT NOT NULL DEFAULT '{}',
        citations_json TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (run_id, item_id),
        FOREIGN KEY (run_id, item_id) REFERENCES items(run_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS summaries (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        language TEXT NOT NULL,
        markdown TEXT NOT NULL,
        saved_path TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        level TEXT NOT NULL,
        stage TEXT,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        cron_expr TEXT NOT NULL,
        cron_label TEXT,
        timezone TEXT NOT NULL,
        hours_window INTEGER NOT NULL DEFAULT 24,
        source_filter_json TEXT,
        last_run_id TEXT,
        last_run_at TEXT,
        next_run_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            for statement in SCHEMA_SQL:
                conn.execute(statement)
            conn.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)")
            conn.commit()
