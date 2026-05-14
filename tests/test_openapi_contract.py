from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def openapi_schema(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_only_exposes_get_post_and_item_flag_patch_methods(tmp_path):
    schema = openapi_schema(tmp_path)
    exposed_methods = {}
    for path, operations in schema["paths"].items():
        for method in operations:
            if method in {"get", "post", "put", "delete", "patch"}:
                exposed_methods.setdefault(method, set()).add(path)

    assert set(exposed_methods) <= {"get", "post", "patch"}
    assert exposed_methods.get("patch", set()) <= {"/items/{item_id}", "/write/artifacts/{artifact_id}"}


def test_openapi_hides_put_and_delete_replacements(tmp_path):
    schema = openapi_schema(tmp_path)

    assert "put" not in schema["paths"]["/config"]
    assert "delete" not in schema["paths"].get("/schedules/{schedule_id}", {})
    assert "post" in schema["paths"]["/config"]
    assert "post" in schema["paths"]["/schedules/{schedule_id}/delete"]


def test_openapi_documents_request_models(tmp_path):
    schema = openapi_schema(tmp_path)
    schemas = schema["components"]["schemas"]

    assert "RunStartRequest" in schemas
    assert "ScheduleCreateRequest" in schemas
    assert "CronValidationRequest" in schemas


def test_openapi_documents_unified_response_models(tmp_path):
    schema = openapi_schema(tmp_path)
    schemas = schema["components"]["schemas"]

    assert _has_schema(schemas, "ApiResponse_HealthData")
    assert _has_schema(schemas, "ApiResponse_RunAcceptedData")
    assert _has_schema(schemas, "ApiResponse_ScheduleListData")


def _has_schema(schemas: dict, prefix: str) -> bool:
    return any(name.startswith(prefix) for name in schemas)
