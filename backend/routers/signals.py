"""Signal generation API router."""
from fastapi import APIRouter, Query

from models import SignalsResponse
from services.signal_engine import generate_signals

router = APIRouter(prefix="/signals", tags=["Signals"])


@router.get("", response_model=SignalsResponse, summary="Get buy/sell trade signals")
async def get_signals(
    timeframe: str = Query("weekly", pattern="^(weekly|monthly)$", description="'weekly' or 'monthly'"),
    account_size: float = Query(5000.0, gt=0, description="Account size in USD"),
    daily_profit_target: float = Query(20.0, ge=0, description="Target daily profit in USD"),
    max_positions: int = Query(5, ge=1, le=20, description="Maximum concurrent swing positions"),
    risk_per_trade_pct: float = Query(0.01, gt=0, le=0.05, description="Max account risk per trade"),
    min_hold_days: int = Query(3, ge=1, le=30, description="Minimum swing holding window"),
    max_hold_days: int = Query(15, ge=1, le=60, description="Maximum swing holding window"),
):
    """
    Generate buy and sell swing-trade signals with account-aware sizing
    and paper-trading evidence.
    """
    data = await generate_signals(
        timeframe=timeframe,
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max_hold_days,
    )
    return SignalsResponse(**data)
