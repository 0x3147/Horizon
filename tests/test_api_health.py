from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / ".horizon"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def test_health_uses_unified_response(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "success": True,
        "data": {"status": "ok"},
        "errorCode": None,
        "errorMessage": None,
    }


def test_openapi_and_swagger_are_available(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    openapi = client.get("/openapi.json")
    docs = client.get("/docs")

    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Horizon Local API"
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
