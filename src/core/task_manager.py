from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


class TaskManager:
    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}
        self.cancel_events: dict[str, asyncio.Event] = {}

    def start(
        self,
        run_id: str,
        coro_factory: Callable[[asyncio.Event], Awaitable[object]],
    ) -> None:
        if run_id in self.tasks and not self.tasks[run_id].done():
            raise ValueError(f"Run already in progress: {run_id}")
        cancel_event = asyncio.Event()
        self.cancel_events[run_id] = cancel_event
        task = asyncio.create_task(coro_factory(cancel_event))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _task: self._cleanup(run_id))

    def cancel(self, run_id: str) -> bool:
        cancel_event = self.cancel_events.get(run_id)
        task = self.tasks.get(run_id)
        if cancel_event is None or task is None or task.done():
            return False
        cancel_event.set()
        task.cancel()
        return True

    def _cleanup(self, run_id: str) -> None:
        self.tasks.pop(run_id, None)
        self.cancel_events.pop(run_id, None)
