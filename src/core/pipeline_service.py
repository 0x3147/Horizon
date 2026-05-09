from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from src.ai.client import create_ai_client
from src.ai.analyzer import ContentAnalyzer
from src.ai.summarizer import DailySummarizer
from src.core.config_service import ConfigService
from src.core.errors import ErrorCode, HorizonApiError
from src.core.settings import AppSettings
from src.models import Config, ContentItem
from src.orchestrator import HorizonOrchestrator
from src.storage.manager import StorageManager
from src.storage.sqlite_store import SQLiteStore


class PipelineService:
    def __init__(
        self,
        store: SQLiteStore,
        settings: AppSettings,
        orchestrator_factory: Callable[[Config, StorageManager], Any] | None = None,
        analyzer_factory: Callable[[Config], Any] | None = None,
        summarizer_factory: Callable[[], Any] | None = None,
    ):
        self.store = store
        self.settings = settings
        self.orchestrator_factory = orchestrator_factory or HorizonOrchestrator
        self.analyzer_factory = analyzer_factory
        self.summarizer_factory = summarizer_factory or DailySummarizer
        self.store.initialize()

    async def run(
        self,
        hours: int = 24,
        run_id: str | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or f"run-{uuid4().hex}"
        cancel_event = cancel_event or asyncio.Event()
        self.store.create_run(run_id, hours=hours, config_snapshot={})

        try:
            self._check_cancel(cancel_event)
            config = ConfigService(self.settings.config_path).get_config()
            self.store.update_run(
                run_id,
                status="running",
                config_snapshot=config.model_dump(mode="json"),
            )
            self.store.add_log(run_id, "info", "run", "started")

            storage = StorageManager(str(self.settings.data_dir), config_path=self.settings.config_path)
            orchestrator = self.orchestrator_factory(config, storage)

            raw_items = await self._fetch_items(run_id, orchestrator, hours, cancel_event)
            scored_items = await self._score_items(run_id, config, orchestrator, raw_items, cancel_event)
            filtered_items = await self._filter_items(run_id, config, orchestrator, scored_items, cancel_event)
            enriched_items = await self._enrich_items(run_id, orchestrator, filtered_items, cancel_event)
            summaries = await self._save_summaries(
                run_id,
                config,
                storage,
                enriched_items,
                total_fetched=len(raw_items),
                cancel_event=cancel_event,
            )

            self.store.update_run(run_id, status="succeeded", finished_at=_utc_now())
            self.store.add_log(run_id, "info", "run", "succeeded")
            return {"run_id": run_id, "status": "succeeded", "summaries": summaries}
        except asyncio.CancelledError:
            self.store.update_run(run_id, status="cancelled", finished_at=_utc_now())
            self.store.add_log(run_id, "warning", "run", "cancelled")
            raise
        except Exception as exc:
            self.store.update_run(
                run_id,
                status="failed",
                finished_at=_utc_now(),
                error_message=str(exc),
            )
            self.store.add_log(run_id, "error", "run", str(exc))
            raise HorizonApiError(ErrorCode.PIPELINE_EXECUTION_FAILED, "Pipeline execution failed") from exc

    async def _fetch_items(
        self,
        run_id: str,
        orchestrator: Any,
        hours: int,
        cancel_event: asyncio.Event,
    ) -> list[ContentItem]:
        self._check_cancel(cancel_event)
        self.store.update_run(run_id, status="fetching")
        self.store.add_log(run_id, "info", "fetching", "started")
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        raw_items = await orchestrator.fetch_all_sources(since)
        if hasattr(orchestrator, "merge_cross_source_duplicates"):
            raw_items = await _maybe_await(orchestrator.merge_cross_source_duplicates(raw_items))
        self.store.save_items(run_id, raw_items, stage="raw", selected=False)
        self.store.add_log(run_id, "info", "raw", f"saved {len(raw_items)} items")
        return raw_items

    async def _score_items(
        self,
        run_id: str,
        config: Config,
        orchestrator: Any,
        raw_items: list[ContentItem],
        cancel_event: asyncio.Event,
    ) -> list[ContentItem]:
        self._check_cancel(cancel_event)
        self.store.update_run(run_id, status="scoring")
        self.store.add_log(run_id, "info", "scoring", "started")
        if self.analyzer_factory:
            analyzer = self.analyzer_factory(config)
            scored_items = await analyzer.analyze_batch(raw_items)
        elif hasattr(orchestrator, "_analyze_content"):
            scored_items = await orchestrator._analyze_content(raw_items)
        else:
            ai_client = create_ai_client(config.ai)
            scored_items = await ContentAnalyzer(ai_client).analyze_batch(raw_items)
        self.store.save_items(run_id, scored_items, stage="scored", selected=False)
        self.store.add_log(run_id, "info", "scored", f"saved {len(scored_items)} items")
        return scored_items

    async def _filter_items(
        self,
        run_id: str,
        config: Config,
        orchestrator: Any,
        scored_items: list[ContentItem],
        cancel_event: asyncio.Event,
    ) -> list[ContentItem]:
        self._check_cancel(cancel_event)
        self.store.update_run(run_id, status="filtering")
        threshold = config.filtering.ai_score_threshold
        filtered_items = [item for item in scored_items if item.ai_score and item.ai_score >= threshold]
        filtered_items.sort(key=lambda item: item.ai_score or 0, reverse=True)
        if hasattr(orchestrator, "merge_topic_duplicates"):
            filtered_items = await _maybe_await(orchestrator.merge_topic_duplicates(filtered_items))
        if hasattr(orchestrator, "_expand_twitter_discussion"):
            await _maybe_await(orchestrator._expand_twitter_discussion(filtered_items))
        self.store.save_items(run_id, filtered_items, stage="filtered", selected=True)
        self.store.add_log(run_id, "info", "filtered", f"saved {len(filtered_items)} items")
        return filtered_items

    async def _enrich_items(
        self,
        run_id: str,
        orchestrator: Any,
        filtered_items: list[ContentItem],
        cancel_event: asyncio.Event,
    ) -> list[ContentItem]:
        self._check_cancel(cancel_event)
        self.store.update_run(run_id, status="enriching")
        if hasattr(orchestrator, "_enrich_important_items"):
            await _maybe_await(orchestrator._enrich_important_items(filtered_items))
        self.store.save_items(run_id, filtered_items, stage="enriched", selected=True)
        self.store.add_log(run_id, "info", "enriched", f"saved {len(filtered_items)} items")
        return filtered_items

    async def _save_summaries(
        self,
        run_id: str,
        config: Config,
        storage: StorageManager,
        items: list[ContentItem],
        total_fetched: int,
        cancel_event: asyncio.Event,
    ) -> list[dict[str, Any]]:
        self._check_cancel(cancel_event)
        self.store.update_run(run_id, status="summarizing")
        summarizer = self.summarizer_factory()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summaries = []
        for language in config.ai.languages:
            markdown = await summarizer.generate_summary(items, today, total_fetched, language=language)
            saved_path = storage.save_daily_summary(today, markdown, language=language)
            summaries.append(
                self.store.save_summary(
                    run_id,
                    language,
                    markdown,
                    saved_path=str(saved_path),
                )
            )
        self.store.add_log(run_id, "info", "summary", f"saved {len(summaries)} summaries")
        return summaries

    @staticmethod
    def _check_cancel(cancel_event: asyncio.Event) -> None:
        if cancel_event.is_set():
            raise asyncio.CancelledError()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
