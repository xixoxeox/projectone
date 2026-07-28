import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from screener.config import Settings
from screener.modules.market.pipeline import DailyWatchlistPipeline, TriggerType

JOB_ID = "daily-watchlist-pipeline"
logger = logging.getLogger(__name__)


async def run_scheduled_pipeline(pipeline: DailyWatchlistPipeline) -> None:
    result = await pipeline.run(trigger=TriggerType.SCHEDULED)
    logger.info(
        "scheduled_watchlist_outcome execution_id=%s trading_date=%s status=%s stage=%s",
        result.execution_id,
        result.trading_date,
        result.status,
        result.stage,
    )


def build_scheduler(pipeline: DailyWatchlistPipeline, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.watchlist_job_timezone)
    scheduler.add_job(
        run_scheduled_pipeline,
        "cron",
        args=[pipeline],
        id=JOB_ID,
        day_of_week="mon-fri",
        hour=settings.watchlist_job_hour,
        minute=settings.watchlist_job_minute,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=settings.watchlist_job_misfire_grace_seconds,
        timezone=settings.watchlist_job_timezone,
    )
    return scheduler
