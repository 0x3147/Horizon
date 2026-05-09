from src.api import server


def test_server_main_uses_process_env_overrides(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "HORIZON_HOST=127.0.0.8\nHORIZON_PORT=9875\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("HORIZON_HOST", "127.0.0.9")
    monkeypatch.setenv("HORIZON_PORT", "9876")
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
