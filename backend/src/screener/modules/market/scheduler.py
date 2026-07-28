from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from screener.modules.market.pipeline import TriggerType
from screener.modules.notifications.pipeline import NotificationPublishingPipeline


def build_scheduler(pipeline: NotificationPublishingPipeline) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        partial(pipeline.run, TriggerType.SCHEDULED),
        "cron",
        id="daily_watchlist",
        hour=18,
        minute=0,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
