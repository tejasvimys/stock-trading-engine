"""Paper trading and learning API router."""
from typing import Optional

from fastapi import APIRouter, Query

from config import settings
from models import (
    AutoTradingStatus,
    PaperCycleResult,
    PaperPortfolioSnapshot,
    PaperPortfolioSummary,
    PaperTrade,
    StrategyLearningState,
)
from services.paper_scheduler import get_auto_trading_status, start_auto_trading, stop_auto_trading
from services.paper_trading_service import (
    get_learning_state,
    get_paper_portfolio_summary,
    list_paper_snapshots,
    list_paper_trades,
    replay_paper_trading,
    reset_paper_trading,
    run_paper_cycle,
)

router = APIRouter(prefix="/paper", tags=["Paper Trading"])


@router.get("/summary", response_model=PaperPortfolioSummary, summary="Get paper portfolio summary")
async def paper_summary():
    return await get_paper_portfolio_summary()


@router.get("/trades", response_model=list[PaperTrade], summary="List paper trades")
async def paper_trades(limit: int = Query(50, ge=1, le=500)):
    return await list_paper_trades(limit=limit)


@router.get("/snapshots", response_model=list[PaperPortfolioSnapshot], summary="List paper equity snapshots")
async def paper_snapshots(limit: int = Query(60, ge=1, le=365)):
    return await list_paper_snapshots(limit=limit)


@router.get("/strategy", response_model=StrategyLearningState, summary="Get adaptive learning weights")
async def paper_strategy():
    return await get_learning_state()


@router.get("/auto/status", response_model=AutoTradingStatus, summary="Get automatic paper-trading status")
async def paper_auto_status():
    return await get_auto_trading_status()


@router.post("/auto/start", response_model=AutoTradingStatus, summary="Start automatic paper-trading cycles")
async def paper_auto_start(
    interval_minutes: int = Query(settings.paper_auto_cycle_interval_minutes, ge=1, le=1440),
    run_immediately: bool = Query(True),
):
    return await start_auto_trading(interval_minutes=interval_minutes, run_immediately=run_immediately)


@router.post("/auto/stop", response_model=AutoTradingStatus, summary="Stop automatic paper-trading cycles")
async def paper_auto_stop():
    return await stop_auto_trading()


@router.post("/run-cycle", response_model=PaperCycleResult, summary="Run one end-of-day paper cycle")
async def paper_run_cycle(
    account_size: float = Query(5000.0, gt=0),
    daily_profit_target: float = Query(20.0, ge=0),
    max_positions: int = Query(5, ge=1, le=20),
    risk_per_trade_pct: float = Query(0.01, gt=0, le=0.05),
    min_hold_days: int = Query(3, ge=1, le=30),
    max_hold_days: int = Query(15, ge=1, le=60),
    as_of: Optional[str] = Query(None, description="ISO date such as 2026-05-08"),
):
    return await run_paper_cycle(
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max_hold_days,
        as_of=as_of,
    )


@router.post("/replay", response_model=dict, summary="Replay recent end-of-day paper cycles")
async def paper_replay(
    days: int = Query(30, ge=5, le=180),
    reset: bool = Query(False),
    account_size: float = Query(5000.0, gt=0),
    daily_profit_target: float = Query(20.0, ge=0),
    max_positions: int = Query(5, ge=1, le=20),
    risk_per_trade_pct: float = Query(0.01, gt=0, le=0.05),
    min_hold_days: int = Query(3, ge=1, le=30),
    max_hold_days: int = Query(15, ge=1, le=60),
):
    return await replay_paper_trading(
        days=days,
        reset=reset,
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max_hold_days,
    )


@router.post("/reset", response_model=dict, summary="Reset local paper trading state")
async def paper_reset(account_size: float = Query(5000.0, gt=0)):
    return await reset_paper_trading(account_size=account_size)
