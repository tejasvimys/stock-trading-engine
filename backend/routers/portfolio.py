"""Portfolio management API router."""
from fastapi import APIRouter, HTTPException

from models import AddHoldingRequest, PortfolioSummary, RemoveHoldingRequest
from services.portfolio_service import add_holding, get_portfolio, remove_holding

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


@router.get("", response_model=PortfolioSummary, summary="Get portfolio summary")
async def portfolio_summary():
    """Return the full portfolio with current prices, P&L, and weights."""
    return await get_portfolio()


@router.post("/holdings", response_model=dict, summary="Add or update a holding")
async def add_or_update_holding(req: AddHoldingRequest):
    """Add a new holding or average into an existing position."""
    holding = await add_holding(req)
    return {"message": "Holding added/updated successfully", "symbol": holding.symbol}


@router.delete("/holdings/{symbol}", response_model=dict, summary="Remove a holding")
async def delete_holding(symbol: str):
    """Remove a holding from the portfolio."""
    removed = await remove_holding(symbol)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Holding '{symbol}' not found")
    return {"message": f"Holding '{symbol}' removed successfully"}
