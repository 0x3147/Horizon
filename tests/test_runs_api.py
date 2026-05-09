from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


class FakeTaskManager:
    def __init__(self):
        self.started = []
        self.cancelled = []

    def start(self, run_id, coro_factory):
        self.started.append((run_id, coro_factory))

    def cancel(self, run_id):
        self.cancelled.append(run_id)
        return True


def test_post_runs_starts_background_task(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.task_manager = FakeTaskManager()
    client = TestClient(app)

    response = client.post("/runs", json={"hours": 12})

    assert response.status_code == 202
    assert response.json()["success"] is True
    assert response.json()["data"]["run_id"].startswith("run-")
    assert app.state.task_manager.started[0][0] == response.json()["data"]["run_id"]


def test_get_runs_and_logs(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.store.create_run("run-1", hours=24, config_snapshot={})
    app.state.store.add_log("run-1", "info", "fetching", "started")
    client = TestClient(app)

    runs = client.get("/runs")
    logs = client.get("/runs/run-1/logs")

    assert runs.status_code == 200
    assert runs.json()["data"]["items"][0]["id"] == "run-1"
    assert logs.json()["data"]["items"][0]["message"] == "started"


def test_get_missing_run_returns_business_error(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/runs/missing")

    assert response.status_code == 404
    assert response.json()["errorCode"] == 4001


def test_cancel_run_returns_request_result(tmp_path):
    app = create_app(settings(tmp_path))
    app.state.task_manager = FakeTaskManager()
    client = TestClient(app)

    response = client.post("/runs/run-1/cancel")

    assert response.status_code == 200
    assert response.json()["data"]["cancel_requested"] is True
    assert app.state.task_manager.cancelled == ["run-1"]
