from apscheduler.schedulers.asyncio import AsyncIOScheduler

from screener.modules.market.sync import DailyBarSyncService, StockSyncService


def build_scheduler(stocks: StockSyncService, bars: DailyBarSyncService) -> AsyncIOScheduler:
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
    return scheduler
