import sqlite3

from src.storage.sqlite_store import SQLiteStore


def tables(db_path):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_initialize_creates_schema(tmp_path):
    db_path = tmp_path / "horizon.db"
    store = SQLiteStore(db_path)

    store.initialize()

    assert {
        "schema_migrations",
        "runs",
        "items",
        "item_analysis",
        "summaries",
        "run_logs",
        "schedules",
    }.issubset(tables(db_path))


def test_initialize_is_idempotent(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")

    store.initialize()
    store.initialize()

    assert "runs" in tables(tmp_path / "horizon.db")
