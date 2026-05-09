from fastapi.testclient import TestClient

from src.api.app import create_app


def test_health_uses_unified_response():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 200,
        "success": True,
        "data": {"status": "ok"},
        "errorCode": None,
        "errorMessage": None,
    }


def test_openapi_and_swagger_are_available():
    client = TestClient(create_app())

    openapi = client.get("/openapi.json")
    docs = client.get("/docs")

    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Horizon Local API"
    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
