"""Pydantic models shared across the application."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stock / Screener
# ---------------------------------------------------------------------------

class ScreenerFilter(BaseModel):
    rsi_min: Optional[float] = Field(None, ge=0, le=100, description="Minimum RSI value")
    rsi_max: Optional[float] = Field(None, ge=0, le=100, description="Maximum RSI value")
    macd_signal: Optional[str] = Field(None, description="'bullish' or 'bearish'")
    bb_position: Optional[str] = Field(None, description="'below_lower', 'above_upper', 'middle'")
    min_volume: Optional[int] = Field(None, description="Minimum average daily volume")
    sort_by: str = Field("symbol", description="Field to sort results by")
    sort_order: str = Field("asc", description="'asc' or 'desc'")
    limit: int = Field(50, ge=1, le=200)


class TechnicalIndicators(BaseModel):
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_9: Optional[float] = None
    volume_avg: Optional[float] = None


class StockSummary(BaseModel):
    symbol: str
    name: Optional[str] = None
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    indicators: TechnicalIndicators = TechnicalIndicators()
    last_updated: Optional[datetime] = None


class ScreenerResponse(BaseModel):
    total: int
    stocks: List[StockSummary]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class SignalType(str):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TradeSignal(BaseModel):
    symbol: str
    name: Optional[str] = None
    signal_type: str  # BUY | SELL | HOLD
    confidence: float = Field(..., ge=0.0, le=1.0)
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    expected_return_pct: Optional[float] = None
    rationale: List[str] = []
    timeframe: str = "weekly"  # weekly | monthly
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SignalsResponse(BaseModel):
    buy_signals: List[TradeSignal]
    sell_signals: List[TradeSignal]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class PortfolioHolding(BaseModel):
    symbol: str
    name: Optional[str] = None
    quantity: float
    avg_buy_price: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    invested_value: Optional[float] = None
    unrealised_pnl: Optional[float] = None
    unrealised_pnl_pct: Optional[float] = None
    weight: Optional[float] = None  # % of portfolio


class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    total_pnl: float
    total_pnl_pct: float
    holdings_count: int
    holdings: List[PortfolioHolding]
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class AddHoldingRequest(BaseModel):
    symbol: str
    quantity: float = Field(..., gt=0)
    avg_buy_price: float = Field(..., gt=0)


class RemoveHoldingRequest(BaseModel):
    symbol: str


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

class InsightPeriod(str):
    DAILY = "daily"
    WEEKLY = "weekly"


class MarketInsight(BaseModel):
    period: str  # daily | weekly
    summary: str
    top_gainers: List[StockSummary] = []
    top_losers: List[StockSummary] = []
    sector_performance: dict = {}
    key_observations: List[str] = []
    recommended_actions: List[str] = []
    generated_at: datetime = Field(default_factory=datetime.utcnow)
