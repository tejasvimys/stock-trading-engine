"""Background scheduler for automatic local paper-trading cycles."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from models import AutoTradingStatus
from services.paper_trading_service import run_paper_cycle

logger = logging.getLogger(__name__)

AUTO_TRADING_JOB_ID = "paper-auto-trading-cycle"

_scheduler: Optional[AsyncIOScheduler] = None
_run_lock = asyncio.Lock()
_is_running = False
_interval_minutes = settings.paper_auto_cycle_interval_minutes
_last_run_started_at: Optional[datetime] = None
_last_run_completed_at: Optional[datetime] = None
_last_cycle_date: Optional[datetime] = None
_last_run_outcome: Optional[str] = None
_last_error: Optional[str] = None
_total_runs = 0


def _get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
        _scheduler.start()
    return _scheduler


def _get_job():
    scheduler = _scheduler
    if scheduler is None:
        return None
    return scheduler.get_job(AUTO_TRADING_JOB_ID)


def _normalise_job_time(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _format_cycle_outcome(as_of_date: datetime, buys_count: int, sells_count: int) -> str:
    return f"{as_of_date.date().isoformat()}: {buys_count} buys, {sells_count} sells"


def _initial_next_run_time(run_immediately: bool, interval_minutes: int) -> datetime:
    return datetime.utcnow() if run_immediately else datetime.utcnow() + timedelta(minutes=interval_minutes)


def _build_status() -> AutoTradingStatus:
    job = _get_job()
    next_run_at = _normalise_job_time(getattr(job, "next_run_time", None))
    return AutoTradingStatus(
        enabled=job is not None,
        is_running=_is_running,
        interval_minutes=_interval_minutes,
        account_size=settings.default_account_size,
        daily_profit_target=settings.default_daily_profit_target,
        max_positions=settings.max_positions,
        next_run_at=next_run_at,
        last_run_started_at=_last_run_started_at,
        last_run_completed_at=_last_run_completed_at,
        last_cycle_date=_last_cycle_date,
        last_run_outcome=_last_run_outcome,
        last_error=_last_error,
        total_runs=_total_runs,
    )


async def _execute_auto_cycle() -> None:
    global _is_running, _last_run_started_at, _last_run_completed_at
    global _last_cycle_date, _last_run_outcome, _last_error, _total_runs

    async with _run_lock:
        _is_running = True
        _last_run_started_at = datetime.utcnow()
        _last_error = None
        try:
            result = await run_paper_cycle(
                account_size=settings.default_account_size,
                daily_profit_target=settings.default_daily_profit_target,
                max_positions=settings.max_positions,
                risk_per_trade_pct=settings.risk_per_trade_pct,
                min_hold_days=settings.min_hold_days,
                max_hold_days=settings.max_hold_days,
            )
            _last_cycle_date = result.as_of_date
            _last_run_outcome = _format_cycle_outcome(
                as_of_date=result.as_of_date,
                buys_count=len(result.buys_executed),
                sells_count=len(result.sells_executed),
            )
            _total_runs += 1
        except Exception as exc:
            _last_run_outcome = "failed"
            _last_error = str(exc)
            logger.exception("Automatic paper-trading cycle failed")
        finally:
            _last_run_completed_at = datetime.utcnow()
            _is_running = False


async def get_auto_trading_status() -> AutoTradingStatus:
    return _build_status()


async def start_auto_trading(
    interval_minutes: Optional[int] = None,
    run_immediately: bool = True,
) -> AutoTradingStatus:
    global _interval_minutes

    scheduler = _get_scheduler()
    _interval_minutes = int(interval_minutes or settings.paper_auto_cycle_interval_minutes)
    scheduler.add_job(
        _execute_auto_cycle,
        trigger=IntervalTrigger(minutes=_interval_minutes),
        id=AUTO_TRADING_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=_initial_next_run_time(run_immediately, _interval_minutes),
    )
    return _build_status()


async def stop_auto_trading() -> AutoTradingStatus:
    scheduler = _scheduler
    if scheduler is not None:
        job = scheduler.get_job(AUTO_TRADING_JOB_ID)
        if job is not None:
            scheduler.remove_job(AUTO_TRADING_JOB_ID)
    return _build_status()


async def initialise_auto_trading() -> None:
    _get_scheduler()
    if settings.paper_auto_trading_enabled:
        await start_auto_trading(
            interval_minutes=settings.paper_auto_cycle_interval_minutes,
            run_immediately=True,
        )


async def shutdown_auto_trading() -> None:
    global _scheduler

    scheduler = _scheduler
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        _scheduler = None
