from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def test_app_exposes_scheduler_runtime(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app(AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765))

    assert hasattr(app.state, "scheduler_runtime")


def test_lifespan_health_still_works(tmp_path):
    data_dir = tmp_path / "data"
    app = create_app(AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
