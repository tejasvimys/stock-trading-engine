"""Stock screening API router."""
from fastapi import APIRouter, Query
from typing import Optional

from models import ScreenerFilter, ScreenerResponse
from services.screener import screen_stocks

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/screen", response_model=ScreenerResponse, summary="Screen stocks by technical indicators")
async def screen(
    rsi_min: Optional[float] = Query(None, ge=0, le=100, description="Minimum RSI"),
    rsi_max: Optional[float] = Query(None, ge=0, le=100, description="Maximum RSI"),
    macd_signal: Optional[str] = Query(None, description="'bullish' or 'bearish'"),
    bb_position: Optional[str] = Query(None, description="'below_lower', 'above_upper', 'middle'"),
    min_volume: Optional[int] = Query(None, ge=0, description="Minimum average volume"),
    sort_by: str = Query("symbol", description="Sort field"),
    sort_order: str = Query("asc", description="'asc' or 'desc'"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Screen stocks by RSI, MACD, Bollinger Bands, volume and other indicators.
    Returns filtered and sorted results.
    """
    f = ScreenerFilter(
        rsi_min=rsi_min,
        rsi_max=rsi_max,
        macd_signal=macd_signal,
        bb_position=bb_position,
        min_volume=min_volume,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
    )
    stocks = await screen_stocks(f)
    return ScreenerResponse(total=len(stocks), stocks=stocks)
