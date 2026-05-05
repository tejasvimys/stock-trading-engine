"""Insights API router."""
from fastapi import APIRouter, Query

from models import MarketInsight
from services.insights_service import generate_insights

router = APIRouter(prefix="/insights", tags=["Insights"])


@router.get("", response_model=MarketInsight, summary="Get AI-driven market insights")
async def get_insights(
    period: str = Query("daily", description="'daily' or 'weekly'"),
):
    """
    Returns AI-driven market insights including top gainers/losers,
    sector performance, key observations, and recommended actions.
    """
    return await generate_insights(period=period)
