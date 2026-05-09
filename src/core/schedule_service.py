from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from src.core.errors import ErrorCode, HorizonApiError, capture_service_errors
from src.storage.sqlite_store import SQLiteStore


class ScheduleService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    @capture_service_errors("schedule", ErrorCode.INVALID_CRON_EXPRESSION)
    def validate_cron(self, cron_expr: str, timezone_name: str) -> dict:
        parts = cron_expr.split()
        if len(parts) != 5:
            raise HorizonApiError(ErrorCode.UNSUPPORTED_CRON_FORMAT, "Unsupported cron format")
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise HorizonApiError(ErrorCode.INVALID_TIMEZONE, "Invalid timezone") from exc
        try:
            trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
            next_run = trigger.get_next_fire_time(None, datetime.now(tz))
        except ValueError as exc:
            raise HorizonApiError(ErrorCode.INVALID_CRON_EXPRESSION, "Invalid cron expression") from exc
        return {"valid": True, "next_run_at": next_run.isoformat() if next_run else None}

    def create_schedule(
        self,
        name: str,
        cron_expr: str,
        timezone_name: str,
        hours_window: int,
        cron_label: str | None = None,
        enabled: bool = True,
    ) -> dict:
        validation = self.validate_cron(cron_expr, timezone_name)
        schedule = {
            "id": f"schedule-{uuid4().hex}",
            "name": name,
            "enabled": enabled,
            "cron_expr": cron_expr,
            "cron_label": cron_label,
            "timezone": timezone_name,
            "hours_window": hours_window,
            "next_run_at": validation["next_run_at"],
        }
        self.store.save_schedule(schedule)
        return schedule
