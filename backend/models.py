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


class BacktestSummary(BaseModel):
    trades: int = Field(0, ge=0)
    wins: int = Field(0, ge=0)
    losses: int = Field(0, ge=0)
    win_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    avg_return_pct: Optional[float] = None
    expected_value_pct: Optional[float] = None
    avg_hold_days: Optional[float] = None


class FundamentalSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None
    forward_pe: Optional[float] = None
    profit_margin: Optional[float] = None
    return_on_equity: Optional[float] = None


class AnalystSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    recommendation: Optional[str] = None
    analyst_count: Optional[int] = None
    target_upside_pct: Optional[float] = None


class OwnershipSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    insider_ownership_pct: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None


class EventSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    upcoming_earnings: bool = False
    days_to_earnings: Optional[int] = None
    event_risk: str = "normal"


class SentimentSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    headline_count: int = Field(0, ge=0)
    sentiment_bias: Optional[str] = None
    positive_hits: int = Field(0, ge=0)
    negative_hits: int = Field(0, ge=0)


class OptionsSignals(BaseModel):
    score: float = Field(0.5, ge=0.0, le=1.0)
    put_call_ratio: Optional[float] = None
    implied_volatility: Optional[float] = None
    call_open_interest: Optional[int] = None
    put_open_interest: Optional[int] = None


class IntelligenceSnapshot(BaseModel):
    composite_score: float = Field(0.5, ge=0.0, le=1.0)
    source_count: int = Field(0, ge=0)
    fundamentals: FundamentalSignals = FundamentalSignals()
    analyst: AnalystSignals = AnalystSignals()
    ownership: OwnershipSignals = OwnershipSignals()
    events: EventSignals = EventSignals()
    sentiment: SentimentSignals = SentimentSignals()
    options: OptionsSignals = OptionsSignals()
    notes: List[str] = []


class TradePlan(BaseModel):
    account_size: float = Field(..., gt=0)
    daily_profit_target: float = Field(..., ge=0)
    capital_per_position: float = Field(..., ge=0)
    risk_budget_usd: float = Field(..., ge=0)
    recommended_shares: int = Field(..., ge=0)
    position_size_usd: float = Field(..., ge=0)
    projected_profit_usd: float = Field(..., ge=0)
    projected_daily_profit_usd: float = Field(..., ge=0)
    risk_amount_usd: float = Field(..., ge=0)
    reward_risk_ratio: Optional[float] = None
    min_holding_days: int = Field(..., ge=1)
    max_holding_days: int = Field(..., ge=1)


class TradeSignal(BaseModel):
    symbol: str
    name: Optional[str] = None
    signal_type: str  # BUY | SELL | HOLD
    confidence: float = Field(..., ge=0.0, le=1.0)
    strategy_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    expected_return_pct: Optional[float] = None
    rationale: List[str] = []
    trade_plan: Optional[TradePlan] = None
    backtest: Optional[BacktestSummary] = None
    intelligence: Optional[IntelligenceSnapshot] = None
    timeframe: str = "weekly"  # weekly | monthly
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SignalsResponse(BaseModel):
    buy_signals: List[TradeSignal]
    sell_signals: List[TradeSignal]
    account_size: Optional[float] = Field(None, gt=0)
    daily_profit_target: Optional[float] = Field(None, ge=0)
    max_positions: Optional[int] = Field(None, ge=1)
    risk_per_trade_pct: Optional[float] = Field(None, ge=0.0, le=1.0)
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
# Paper trading / learning
# ---------------------------------------------------------------------------

class PaperPosition(BaseModel):
    symbol: str
    side: str
    quantity: int
    entry_price: float
    current_price: float
    market_value: float
    invested_value: float
    target_price: float
    stop_loss: float
    opened_at: datetime
    last_marked_at: datetime
    days_held: int
    confidence: float
    strategy_score: float
    unrealised_pnl: float
    unrealised_pnl_pct: float
    rationale: List[str] = []


class PaperTrade(BaseModel):
    symbol: str
    side: str
    quantity: int
    price: float
    executed_at: datetime
    reason: str
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    holding_days: Optional[int] = None
    confidence: Optional[float] = None
    strategy_score: Optional[float] = None
    market_regime: Optional[str] = None


class StrategyLearningState(BaseModel):
    weights: dict[str, float]
    learning_rate: float = Field(..., gt=0, le=1)
    trades_evaluated: int = Field(..., ge=0)
    last_updated: datetime


class GoalProgress(BaseModel):
    target: float
    actual: float
    progress_pct: float


class PaperPortfolioSnapshot(BaseModel):
    as_of_date: datetime
    cash_balance: float
    market_value: float
    total_equity: float
    realised_pnl: float
    unrealised_pnl: float
    total_return_pct: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float
    open_positions: int
    closed_trades: int
    market_regime: str


class PaperPortfolioSummary(BaseModel):
    starting_cash: float
    cash_balance: float
    market_value: float
    total_equity: float
    realised_pnl: float
    unrealised_pnl: float
    total_return_pct: float
    open_positions: List[PaperPosition]
    recent_trades: List[PaperTrade]
    latest_snapshot: Optional[PaperPortfolioSnapshot] = None
    daily_goal: GoalProgress
    weekly_goal: GoalProgress
    monthly_goal: GoalProgress
    learning_state: StrategyLearningState


class PaperCycleResult(BaseModel):
    as_of_date: datetime
    market_regime: str
    buys_executed: List[PaperTrade]
    sells_executed: List[PaperTrade]
    skipped_symbols: List[str] = []
    summary: PaperPortfolioSummary


class AutoTradingStatus(BaseModel):
    enabled: bool
    is_running: bool = False
    interval_minutes: int = Field(..., ge=1)
    account_size: float = Field(..., gt=0)
    daily_profit_target: float = Field(..., ge=0)
    max_positions: int = Field(..., ge=1)
    next_run_at: Optional[datetime] = None
    last_run_started_at: Optional[datetime] = None
    last_run_completed_at: Optional[datetime] = None
    last_cycle_date: Optional[datetime] = None
    last_run_outcome: Optional[str] = None
    last_error: Optional[str] = None
    total_runs: int = Field(0, ge=0)


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
