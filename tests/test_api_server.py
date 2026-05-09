import os

from src.api import server


def test_server_main_loads_horizon_home_secrets(tmp_path, monkeypatch):
    horizon_home = tmp_path / ".horizon"
    horizon_home.mkdir()
    (horizon_home / "secrets.env").write_text(
        "HORIZON_TRACE_TEST_SECRET=secret-value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HORIZON_TRACE_TEST_SECRET", raising=False)
    captured = {}

    def fake_run(app, host, port):
        captured["secret"] = os.environ.get("HORIZON_TRACE_TEST_SECRET")
        captured["secrets_path"] = app.state.settings.secrets_path

    monkeypatch.setattr(server.uvicorn, "run", fake_run)

    server.main()

    assert captured["secret"] == "secret-value"
    assert captured["secrets_path"] == horizon_home / "secrets.env"


def test_server_main_loads_dotenv_before_settings(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "HORIZON_HOST=127.0.0.9\nHORIZON_PORT=9876\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HORIZON_HOST", raising=False)
    monkeypatch.delenv("HORIZON_PORT", raising=False)
    captured = {}

    def fake_run(app, host, port):
        captured["host"] = host
        captured["port"] = port
        captured["settings"] = app.state.settings

    monkeypatch.setattr(server.uvicorn, "run", fake_run)

    server.main()

    assert captured["host"] == "127.0.0.9"
    assert captured["port"] == 9876
    assert captured["settings"].host == "127.0.0.9"
    assert captured["settings"].port == 9876
