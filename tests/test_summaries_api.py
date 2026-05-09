from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def test_list_summaries(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.save_summary("run-1", "en", "# Summary")
    client = TestClient(app)

    response = client.get("/summaries")

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["markdown"] == "# Summary"


def test_list_run_summaries(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.create_run("run-2", hours=24, config_snapshot={})
    app.state.store.save_summary("run-1", "en", "# Summary")
    client = TestClient(app)

    response = client.get("/runs/run-1/summaries")

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["run_id"] == "run-1"


def test_missing_run_summaries_return_empty_list(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/runs/missing/summaries")

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
