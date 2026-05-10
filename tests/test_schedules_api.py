from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.settings import AppSettings


def settings(tmp_path):
    data_dir = tmp_path / "data"
    return AppSettings(data_dir, data_dir / "horizon.db", data_dir / "config.json", "127.0.0.1", 8765)


def test_validate_cron_endpoint(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/schedules/validate-cron",
        json={"cron_expr": "0 8 * * *", "timezone": "Asia/Shanghai"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["valid"] is True


def test_validate_cron_missing_fields_uses_invalid_request(tmp_path):
    client = TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False)

    response = client.post("/schedules/validate-cron", json={})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 1001


def test_create_schedule_missing_fields_uses_invalid_request(tmp_path):
    client = TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False)

    response = client.post("/schedules", json={})

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 1001


def test_create_and_list_schedule(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post(
        "/schedules",
        json={
            "name": "Daily",
            "cron_expr": "0 8 * * *",
            "cron_label": "daily_8am",
            "timezone": "Asia/Shanghai",
            "hours_window": 24,
            "enabled": True,
        },
    )

    assert response.status_code == 201
    schedule_id = response.json()["data"]["id"]
    list_response = client.get("/schedules")
    assert list_response.json()["data"]["items"][0]["id"] == schedule_id


def test_delete_schedule_uses_post_action(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))
    response = client.post(
        "/schedules",
        json={
            "name": "Daily",
            "cron_expr": "0 8 * * *",
            "timezone": "Asia/Shanghai",
        },
    )
    schedule_id = response.json()["data"]["id"]

    delete_response = client.post(f"/schedules/{schedule_id}/delete")

    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["deleted"] is True
