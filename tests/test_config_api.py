import json

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / ".horizon"
    return AppSettings(
        data_dir=data_dir,
        db_path=data_dir / "horizon.db",
        config_path=data_dir / "settings.json",
        host="127.0.0.1",
        port=8765,
    )


def minimal_config():
    return {
        "version": "1.0",
        "ai": {
            "provider": "openai",
            "model": "gpt-4",
            "api_key": "sk-local",
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
    assert response.json()["data"]["ai"]["api_key"] == "sk-local"


def test_post_config_validates_and_saves(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    s.config_path.write_text(json.dumps(minimal_config()), encoding="utf-8")
    client = TestClient(create_app(s))
    updated = minimal_config()
    updated["filtering"]["ai_score_threshold"] = 8.0
    updated["webhook"] = {"enabled": True, "url": "https://example.com/webhook"}
    updated["email"] = {
        "enabled": False,
        "smtp_server": "smtp.example.com",
        "imap_server": "imap.example.com",
        "email_address": "user@example.com",
        "password": "mail-password",
    }

    response = client.post("/config", json=updated)

    assert response.status_code == 200
    assert response.json()["data"]["filtering"]["ai_score_threshold"] == 8.0
    saved = json.loads(s.config_path.read_text(encoding="utf-8"))
    assert saved["filtering"]["ai_score_threshold"] == 8.0
    assert saved["ai"]["api_key"] == "sk-local"
    assert saved["webhook"]["url"] == "https://example.com/webhook"
    assert saved["email"]["password"] == "mail-password"


def test_validate_config_rejects_invalid_payload(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post("/config/validate", json={"bad": "payload"})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 2002
