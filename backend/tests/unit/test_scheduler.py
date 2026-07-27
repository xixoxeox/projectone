from unittest.mock import AsyncMock

from screener.config import Settings
from screener.modules.market.pipeline import TriggerType
from screener.modules.market.scheduler import JOB_ID, build_scheduler, run_scheduled_pipeline


def test_scheduler_registers_only_configured_daily_pipeline() -> None:
    pipeline = AsyncMock()
    settings = Settings(
        watchlist_job_hour=7, watchlist_job_minute=45, watchlist_job_misfire_grace_seconds=123
    )
    scheduler = build_scheduler(pipeline, settings)
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == JOB_ID
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == 123
    assert "day_of_week='mon-fri'" in str(job.trigger)
    assert "hour='7'" in str(job.trigger)
    assert "minute='45'" in str(job.trigger)
    assert str(scheduler.timezone) == "Asia/Seoul"
    pipeline.run.assert_not_awaited()


def test_scheduled_wrapper_uses_scheduled_trigger() -> None:
    pipeline = AsyncMock()
    pipeline.run.return_value = AsyncMock(
        execution_id=None, trading_date="2026-07-27", status="skipped", stage="completed"
    )
    import asyncio

    asyncio.run(run_scheduled_pipeline(pipeline))
    pipeline.run.assert_awaited_once_with(trigger=TriggerType.SCHEDULED)


def test_scheduler_defaults_are_opt_in_and_expected() -> None:
    settings = Settings()
    assert settings.scheduler_enabled is False
    scheduler = build_scheduler(AsyncMock(), settings)
    job = scheduler.get_job(JOB_ID)
    assert job is not None
    assert "hour='18'" in str(job.trigger)
    assert "minute='20'" in str(job.trigger)
