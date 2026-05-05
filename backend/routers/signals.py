"""Signal generation API router."""
from fastapi import APIRouter, Query

from models import SignalsResponse
from services.signal_engine import generate_signals

router = APIRouter(prefix="/signals", tags=["Signals"])


@router.get("", response_model=SignalsResponse, summary="Get buy/sell trade signals")
async def get_signals(
    timeframe: str = Query("weekly", description="'weekly' or 'monthly'"),
):
    """
    Generate buy and sell signals targeting at least 10% profit.
    Signals are sorted by confidence descending.
    """
    data = await generate_signals(timeframe=timeframe)
    return SignalsResponse(**data)
