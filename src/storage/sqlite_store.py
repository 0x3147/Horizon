from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def create_run(self, run_id: str, hours: int, config_snapshot: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (id, status, hours, started_at, config_snapshot_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "pending",
                    hours,
                    _utc_now(),
                    _json_dumps(config_snapshot or {}),
                ),
            )
            conn.commit()

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        updates = []
        values = []
        allowed = {
            "status",
            "hours",
            "started_at",
            "finished_at",
            "raw_count",
            "scored_count",
            "filtered_count",
            "enriched_count",
            "error_message",
        }
        for key, value in fields.items():
            if key == "config_snapshot":
                updates.append("config_snapshot_json = ?")
                values.append(_json_dumps(value or {}))
            elif key in allowed:
                updates.append(f"{key} = ?")
                values.append(_serialize_scalar(value))
        if not updates:
            return
        values.append(run_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_from_row(row) if row else None

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM runs
                ORDER BY started_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [_run_from_row(row) for row in rows]

    def add_log(self, run_id: str | None, level: str, stage: str | None, message: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO run_logs (run_id, level, stage, message)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, level, stage, message),
            )
            conn.commit()

    def list_logs(
        self,
        run_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if run_id is not None:
            where = "WHERE run_id = ?"
            params.append(run_id)
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM run_logs
                {where}
                ORDER BY id ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def save_items(
        self,
        run_id: str,
        items: list[Any],
        stage: str,
        selected: bool = False,
    ) -> None:
        with self.connect() as conn:
            for item in items:
                metadata = dict(getattr(item, "metadata", {}) or {})
                conn.execute(
                    """
                    INSERT INTO items (
                        id, run_id, source_type, source_name, native_id, title, url,
                        content, author, published_at, fetched_at, metadata_json,
                        stage, is_selected, duplicate_of_item_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, id) DO UPDATE SET
                        source_type = excluded.source_type,
                        source_name = excluded.source_name,
                        native_id = excluded.native_id,
                        title = excluded.title,
                        url = excluded.url,
                        content = excluded.content,
                        author = excluded.author,
                        published_at = excluded.published_at,
                        fetched_at = excluded.fetched_at,
                        metadata_json = excluded.metadata_json,
                        stage = excluded.stage,
                        is_selected = excluded.is_selected,
                        duplicate_of_item_id = excluded.duplicate_of_item_id
                    """,
                    (
                        item.id,
                        run_id,
                        _enum_value(item.source_type),
                        _source_name(metadata),
                        metadata.get("native_id") or str(item.id).split(":")[-1],
                        item.title,
                        str(item.url),
                        item.content,
                        item.author,
                        _serialize_scalar(item.published_at),
                        _serialize_scalar(item.fetched_at),
                        _json_dumps(metadata),
                        stage,
                        1 if selected else 0,
                        metadata.get("duplicate_of_item_id"),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO item_analysis (
                        run_id, item_id, ai_score, ai_reason, ai_summary, ai_tags_json,
                        detailed_summary_json, background_json, community_discussion_json,
                        citations_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, item_id) DO UPDATE SET
                        ai_score = excluded.ai_score,
                        ai_reason = excluded.ai_reason,
                        ai_summary = excluded.ai_summary,
                        ai_tags_json = excluded.ai_tags_json,
                        detailed_summary_json = excluded.detailed_summary_json,
                        background_json = excluded.background_json,
                        community_discussion_json = excluded.community_discussion_json,
                        citations_json = excluded.citations_json
                    """,
                    (
                        run_id,
                        item.id,
                        getattr(item, "ai_score", None),
                        getattr(item, "ai_reason", None),
                        getattr(item, "ai_summary", None),
                        _json_dumps(getattr(item, "ai_tags", []) or []),
                        _json_dumps(getattr(item, "detailed_summary", {}) or {}),
                        _json_dumps(getattr(item, "background", {}) or {}),
                        _json_dumps(getattr(item, "community_discussion", {}) or {}),
                        _json_dumps(getattr(item, "citations", []) or []),
                    ),
                )
            count_column = {
                "raw": "raw_count",
                "scored": "scored_count",
                "filtered": "filtered_count",
                "enriched": "enriched_count",
            }.get(stage)
            if count_column:
                conn.execute(
                    f"UPDATE runs SET {count_column} = ? WHERE id = ?",
                    (len(items), run_id),
                )
            conn.commit()

    def query_items(
        self,
        run_id: str | None = None,
        source_type: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        selected_only: bool = False,
        stage: str | None = None,
        tag: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if run_id:
            where.append("i.run_id = ?")
            params.append(run_id)
        if source_type:
            where.append("i.source_type = ?")
            params.append(_enum_value(source_type))
        if min_score is not None:
            where.append("a.ai_score >= ?")
            params.append(min_score)
        if max_score is not None:
            where.append("a.ai_score <= ?")
            params.append(max_score)
        if selected_only:
            where.append("i.is_selected = 1")
        if stage:
            where.append("i.stage = ?")
            params.append(stage)
        if tag:
            where.append("a.ai_tags_json LIKE ?")
            params.append(f'%"{tag}"%')
        if q:
            where.append("(LOWER(i.title) LIKE ? OR LOWER(i.content) LIKE ? OR LOWER(a.ai_summary) LIKE ?)")
            needle = f"%{q.lower()}%"
            params.extend([needle, needle, needle])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT i.*, a.ai_score, a.ai_reason, a.ai_summary, a.ai_tags_json,
                       a.detailed_summary_json, a.background_json,
                       a.community_discussion_json, a.citations_json
                FROM items i
                LEFT JOIN item_analysis a ON a.run_id = i.run_id AND a.item_id = i.id
                {where_sql}
                ORDER BY COALESCE(a.ai_score, -1) DESC, i.published_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [_item_from_row(row) for row in rows]

    def get_item(self, item_id: str, run_id: str | None = None) -> dict[str, Any] | None:
        where = ["i.id = ?"]
        params: list[Any] = [item_id]
        if run_id:
            where.append("i.run_id = ?")
            params.append(run_id)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT i.*, a.ai_score, a.ai_reason, a.ai_summary, a.ai_tags_json,
                       a.detailed_summary_json, a.background_json,
                       a.community_discussion_json, a.citations_json
                FROM items i
                LEFT JOIN item_analysis a ON a.run_id = i.run_id AND a.item_id = i.id
                WHERE {' AND '.join(where)}
                ORDER BY i.fetched_at DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return _item_from_row(row) if row else None

    def save_summary(
        self,
        run_id: str,
        language: str,
        markdown: str,
        saved_path: str | None = None,
        summary_id: str | None = None,
    ) -> dict[str, Any]:
        summary_id = summary_id or f"{run_id}:{language}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO summaries (id, run_id, language, markdown, saved_path)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    language = excluded.language,
                    markdown = excluded.markdown,
                    saved_path = excluded.saved_path
                """,
                (summary_id, run_id, language, markdown, saved_path),
            )
            row = conn.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()
            conn.commit()
        return dict(row)

    def list_summaries(
        self,
        run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where = ""
        params: list[Any] = []
        if run_id:
            where = "WHERE run_id = ?"
            params.append(run_id)
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM summaries
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_summary(self, summary_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM summaries WHERE id = ?", (summary_id,)).fetchone()
        return dict(row) if row else None

    def save_schedule(self, schedule: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO schedules (
                    id, name, enabled, cron_expr, cron_label, timezone,
                    hours_window, source_filter_json, last_run_id, last_run_at,
                    next_run_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    enabled = excluded.enabled,
                    cron_expr = excluded.cron_expr,
                    cron_label = excluded.cron_label,
                    timezone = excluded.timezone,
                    hours_window = excluded.hours_window,
                    source_filter_json = excluded.source_filter_json,
                    last_run_id = excluded.last_run_id,
                    last_run_at = excluded.last_run_at,
                    next_run_at = excluded.next_run_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    schedule["id"],
                    schedule["name"],
                    1 if schedule.get("enabled", True) else 0,
                    schedule["cron_expr"],
                    schedule.get("cron_label"),
                    schedule["timezone"],
                    schedule.get("hours_window", 24),
                    _json_dumps(schedule.get("source_filter") or {}),
                    schedule.get("last_run_id"),
                    schedule.get("last_run_at"),
                    schedule.get("next_run_at"),
                ),
            )
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule["id"],)).fetchone()
            conn.commit()
        return _schedule_from_row(row)

    def list_schedules(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY created_at DESC, id DESC"
            ).fetchall()
        return [_schedule_from_row(row) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
        return _schedule_from_row(row) if row else None

    def delete_schedule(self, schedule_id: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
        return cursor.rowcount > 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _serialize_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value)


def _source_name(metadata: dict[str, Any]) -> str | None:
    for key in ("source_name", "feed_name", "subreddit", "channel", "repo"):
        if metadata.get(key):
            return str(metadata[key])
    return None


def _run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["config_snapshot"] = _json_loads(data.pop("config_snapshot_json", None), {})
    return data


def _item_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = _json_loads(data.pop("metadata_json", None), {})
    data["is_selected"] = bool(data["is_selected"])
    data["ai_tags"] = _json_loads(data.pop("ai_tags_json", None), [])
    data["detailed_summary"] = _json_loads(data.pop("detailed_summary_json", None), {})
    data["background"] = _json_loads(data.pop("background_json", None), {})
    data["community_discussion"] = _json_loads(data.pop("community_discussion_json", None), {})
    data["citations"] = _json_loads(data.pop("citations_json", None), [])
    return data


def _schedule_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["enabled"] = bool(data["enabled"])
    data["source_filter"] = _json_loads(data.pop("source_filter_json", None), {})
    return data
