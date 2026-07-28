from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from screener.modules.market.pipeline import TriggerType
from screener.modules.market.sync import DailyBarSyncService, StockSyncService
from screener.modules.notifications.pipeline import NotificationPublishingPipeline


def build_scheduler(
    stocks: StockSyncService,
    bars: DailyBarSyncService,
    pipeline: NotificationPublishingPipeline,
    *,
    watchlist_hour: int = 18,
    watchlist_minute: int = 10,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        stocks.run,
        "cron",
        id="stock_master",
        hour=6,
        minute=0,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        bars.run,
        "cron",
        id="daily_bars",
        hour=18,
        minute=0,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        partial(pipeline.run, TriggerType.SCHEDULED),
        "cron",
        id="daily_watchlist",
        hour=watchlist_hour,
        minute=watchlist_minute,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
