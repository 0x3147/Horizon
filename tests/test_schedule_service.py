import pytest

from src.core.errors import HorizonApiError
from src.core.schedule_service import ScheduleService
from src.storage.sqlite_store import SQLiteStore


def test_validate_five_field_cron(tmp_path):
    service = ScheduleService(SQLiteStore(tmp_path / "horizon.db"))

    result = service.validate_cron("0 8 * * *", "Asia/Shanghai")

    assert result["valid"] is True
    assert result["next_run_at"]


def test_reject_six_field_cron(tmp_path):
    service = ScheduleService(SQLiteStore(tmp_path / "horizon.db"))

    with pytest.raises(HorizonApiError) as exc:
        service.validate_cron("0 0 8 * * *", "Asia/Shanghai")

    assert int(exc.value.error_code) == 3003


def test_create_schedule_persists(tmp_path):
    store = SQLiteStore(tmp_path / "horizon.db")
    store.initialize()
    service = ScheduleService(store)

    schedule = service.create_schedule(
        name="Daily",
        cron_expr="0 8 * * *",
        timezone_name="Asia/Shanghai",
        hours_window=24,
        cron_label="daily_8am",
        enabled=True,
    )

    assert store.get_schedule(schedule["id"])["name"] == "Daily"
