import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(
        data_dir=data_dir,
        db_path=data_dir / "horizon.db",
        config_path=data_dir / "config.json",
        host="127.0.0.1",
        port=8765,
    )


def minimal_config():
    return {
        "version": "1.0",
        "ai": {
            "provider": "openai",
            "model": "gpt-4",
            "api_key_env": "OPENAI_API_KEY",
        },
        "sources": {
            "github": [],
            "hackernews": {"enabled": False},
            "rss": [],
            "reddit": {"enabled": False, "subreddits": [], "users": []},
            "telegram": {"enabled": False, "channels": []},
        },
        "filtering": {"ai_score_threshold": 7.0, "time_window_hours": 24},
    }


def test_get_config(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    s.config_path.write_text(json.dumps(minimal_config()), encoding="utf-8")
    client = TestClient(create_app(s))

    response = client.get("/config")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["ai"]["model"] == "gpt-4"


def test_put_config_validates_and_saves(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    s.config_path.write_text(json.dumps(minimal_config()), encoding="utf-8")
    client = TestClient(create_app(s))
    updated = minimal_config()
    updated["filtering"]["ai_score_threshold"] = 8.0

    response = client.put("/config", json=updated)

    assert response.status_code == 200
    assert response.json()["data"]["filtering"]["ai_score_threshold"] == 8.0
    saved = json.loads(s.config_path.read_text(encoding="utf-8"))
    assert saved["filtering"]["ai_score_threshold"] == 8.0


def test_validate_config_rejects_invalid_payload(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post("/config/validate", json={"bad": "payload"})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 2002
