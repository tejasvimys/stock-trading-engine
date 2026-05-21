"""Local adaptive paper-trading service."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Iterable, Optional

import pandas as pd
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, delete, select

from config import settings
from models import (
    GoalProgress,
    IntelligenceSnapshot,
    PaperCycleResult,
    PaperPortfolioSnapshot,
    PaperPortfolioSummary,
    PaperPosition,
    PaperTrade,
    StrategyLearningState,
    TradeSignal,
)
from services.data_fetcher import fetch_history_async, fetch_multiple, get_tickers
from services.data_fetcher import fetch_intelligence_snapshot
from services.portfolio_service import AsyncSessionLocal, Base
from services.signal_engine import (
    PlanningContext,
    _backtest_signal,
    _build_trade_plan,
    _compute_target_and_stop,
    _passes_trade_quality_gate,
    _rank_signal,
    _score_stock,
)

logger = logging.getLogger(__name__)


class PaperAccountORM(Base):
    __tablename__ = "paper_account"

    id = Column(Integer, primary_key=True, default=1)
    starting_cash = Column(Float, nullable=False)
    cash_balance = Column(Float, nullable=False)
    created_at = Column(String, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class PaperPositionORM(Base):
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, nullable=False, index=True)
    side = Column(String, nullable=False, default="LONG")
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    opened_at = Column(String, nullable=False)
    last_marked_at = Column(String, nullable=False)
    days_held = Column(Integer, default=0)
    confidence = Column(Float, nullable=False)
    strategy_score = Column(Float, nullable=False)
    rationale_json = Column(Text, nullable=False)
    feature_json = Column(Text, nullable=False)


class PaperTradeORM(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    executed_at = Column(String, nullable=False, index=True)
    reason = Column(String, nullable=False)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    strategy_score = Column(Float, nullable=True)
    market_regime = Column(String, nullable=True)
    feature_json = Column(Text, nullable=True)


class PaperSnapshotORM(Base):
    __tablename__ = "paper_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    as_of_date = Column(String, unique=True, nullable=False, index=True)
    cash_balance = Column(Float, nullable=False)
    market_value = Column(Float, nullable=False)
    total_equity = Column(Float, nullable=False)
    realised_pnl = Column(Float, nullable=False)
    unrealised_pnl = Column(Float, nullable=False)
    total_return_pct = Column(Float, nullable=False)
    daily_pnl = Column(Float, nullable=False)
    weekly_pnl = Column(Float, nullable=False)
    monthly_pnl = Column(Float, nullable=False)
    open_positions = Column(Integer, nullable=False)
    closed_trades = Column(Integer, nullable=False)
    market_regime = Column(String, nullable=False)


class StrategyStateORM(Base):
    __tablename__ = "paper_strategy_state"

    id = Column(Integer, primary_key=True, default=1)
    weights_json = Column(Text, nullable=False)
    learning_rate = Column(Float, nullable=False)
    trades_evaluated = Column(Integer, nullable=False, default=0)
    updated_at = Column(String, default=lambda: datetime.utcnow().isoformat())


class SignalJournalORM(Base):
    __tablename__ = "paper_signal_journal"

    id = Column(Integer, primary_key=True, index=True)
    as_of_date = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    signal_type = Column(String, nullable=False)
    selected = Column(Boolean, nullable=False, default=False)
    confidence = Column(Float, nullable=False)
    strategy_score = Column(Float, nullable=False)
    market_regime = Column(String, nullable=False)
    feature_json = Column(Text, nullable=False)
    rationale_json = Column(Text, nullable=False)


def _to_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _from_json(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.fromisoformat(value).date()


def _date_key(value: date) -> str:
    return value.isoformat()


def _dt_from_date(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time())


def _position_side(value: Any) -> str:
    side = str(getattr(value, "side", "LONG") or "LONG").upper()
    return "SHORT" if side == "SHORT" else "LONG"


def _signed_position_value(price: float, quantity: int, side: str) -> float:
    gross = price * quantity
    return gross if side == "LONG" else -gross


def _default_weights() -> dict[str, float]:
    return {
        "technical_quality": 0.35,
        "confidence": 0.2,
        "win_rate": 0.2,
        "expected_value": 0.15,
        "profit_fit": 0.1,
    }


def _normalise_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.05, float(value)) for key, value in weights.items()}
    total = sum(cleaned.values()) or 1.0
    return {key: round(value / total, 4) for key, value in cleaned.items()}


def _goal_targets(account_size: float) -> dict[str, float]:
    scale = account_size / 5000.0
    return {
        "daily": round(20.0 * scale, 2),
        "weekly": round(200.0 * scale, 2),
        "monthly": round(800.0 * scale, 2),
    }


def _safe_ratio(actual: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return round((actual / target) * 100, 2)


def _goal_progress(actual: float, target: float) -> GoalProgress:
    return GoalProgress(target=round(target, 2), actual=round(actual, 2), progress_pct=_safe_ratio(actual, target))


def _derive_market_regime(df: pd.DataFrame) -> str:
    if df.empty or len(df) < 50:
        return "neutral"

    close = df["Close"]
    price = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    ret_10d = (price - float(close.iloc[-11])) / float(close.iloc[-11]) if len(close) > 10 else 0.0

    if price > sma20 > sma50 and ret_10d > 0.01:
        return "bullish"
    if price < sma20 < sma50 and ret_10d < -0.01:
        return "bearish"
    return "neutral"


def _feature_snapshot(signal: TradeSignal, daily_profit_target: float) -> dict[str, float]:
    expected_value = signal.backtest.expected_value_pct if signal.backtest else 0.0
    projected_daily_profit = signal.trade_plan.projected_daily_profit_usd if signal.trade_plan else 0.0
    features = {
        "technical_quality": float(signal.strategy_score or 0.0),
        "confidence": float(signal.confidence or 0.0),
        "win_rate": float(signal.backtest.win_rate or 0.0) if signal.backtest else 0.0,
        "expected_value": min(max(((expected_value or 0.0) + 5.0) / 10.0, 0.0), 1.0),
        "profit_fit": min(max((projected_daily_profit / daily_profit_target), 0.0), 1.0) if daily_profit_target > 0 else 0.0,
    }
    return {key: round(value, 4) for key, value in features.items()}


def _adaptive_score(features: dict[str, float], weights: dict[str, float]) -> float:
    normalised = _normalise_weights(weights)
    return round(sum(features.get(key, 0.0) * normalised.get(key, 0.0) for key in normalised), 4)


def _update_learning_weights(
    current_weights: dict[str, float],
    feature_snapshots: list[dict[str, float]],
    returns_pct: list[float],
    learning_rate: float,
) -> dict[str, float]:
    if not feature_snapshots or len(feature_snapshots) != len(returns_pct):
        return _normalise_weights(current_weights)

    winners = [snap for snap, ret in zip(feature_snapshots, returns_pct) if ret > 0]
    losers = [snap for snap, ret in zip(feature_snapshots, returns_pct) if ret <= 0]
    if not winners or not losers:
        return _normalise_weights(current_weights)

    updated: dict[str, float] = {}
    keys = set(current_weights) | set(winners[0]) | set(losers[0])
    for key in keys:
        win_avg = sum(snap.get(key, 0.0) for snap in winners) / len(winners)
        loss_avg = sum(snap.get(key, 0.0) for snap in losers) / len(losers)
        updated[key] = current_weights.get(key, 0.0) + (learning_rate * (win_avg - loss_avg))

    return _normalise_weights(updated)


def _slice_to_date(df: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[df.index.date <= as_of_date]


def _row_for_date(df: pd.DataFrame, as_of_date: date) -> Optional[pd.Series]:
    sliced = _slice_to_date(df, as_of_date)
    if sliced.empty:
        return None
    return sliced.iloc[-1]


def _count_holding_days(df: pd.DataFrame, opened_at: date, as_of_date: date) -> int:
    sliced = df[(df.index.date > opened_at) & (df.index.date <= as_of_date)]
    return int(len(sliced))


def _latest_history_date(histories: dict[str, pd.DataFrame]) -> Optional[date]:
    available_dates = [
        df.index[-1].date()
        for df in histories.values()
        if not df.empty
    ]
    return max(available_dates) if available_dates else None


async def _load_histories() -> dict[str, pd.DataFrame]:
    symbols = list(dict.fromkeys([*get_tickers(), "SPY"]))
    histories = await fetch_multiple(symbols, period="6mo")
    return histories


async def _get_or_create_account(session, account_size: float) -> PaperAccountORM:
    result = await session.execute(select(PaperAccountORM).where(PaperAccountORM.id == 1))
    account = result.scalar_one_or_none()
    if account is None:
        account = PaperAccountORM(id=1, starting_cash=account_size, cash_balance=account_size)
        session.add(account)
        await session.flush()
    return account


async def _get_or_create_strategy_state(session) -> StrategyStateORM:
    result = await session.execute(select(StrategyStateORM).where(StrategyStateORM.id == 1))
    state = result.scalar_one_or_none()
    if state is None:
        state = StrategyStateORM(
            id=1,
            weights_json=_to_json(_default_weights()),
            learning_rate=settings.paper_learning_rate,
            trades_evaluated=0,
        )
        session.add(state)
        await session.flush()
    return state


async def _refresh_learning_state(session, strategy_state: StrategyStateORM) -> None:
    result = await session.execute(select(PaperTradeORM).where(PaperTradeORM.side == "SELL").order_by(PaperTradeORM.id))
    closed_trades = result.scalars().all()
    if len(closed_trades) <= strategy_state.trades_evaluated:
        return

    new_trades = closed_trades[strategy_state.trades_evaluated :]
    feature_snapshots = [_from_json(trade.feature_json, {}) for trade in new_trades if trade.feature_json]
    returns_pct = [float(trade.pnl_pct or 0.0) for trade in new_trades if trade.feature_json]
    if feature_snapshots and len(feature_snapshots) == len(returns_pct):
        current_weights = _from_json(strategy_state.weights_json, _default_weights())
        strategy_state.weights_json = _to_json(
            _update_learning_weights(current_weights, feature_snapshots, returns_pct, strategy_state.learning_rate)
        )
        strategy_state.updated_at = datetime.utcnow().isoformat()

    strategy_state.trades_evaluated = len(closed_trades)
    await session.flush()


def _trade_model_from_orm(orm_obj: PaperTradeORM) -> PaperTrade:
    return PaperTrade(
        symbol=orm_obj.symbol,
        side=orm_obj.side,
        quantity=orm_obj.quantity,
        price=round(orm_obj.price, 2),
        executed_at=datetime.fromisoformat(orm_obj.executed_at),
        reason=orm_obj.reason,
        pnl=round(float(orm_obj.pnl), 2) if orm_obj.pnl is not None else None,
        pnl_pct=round(float(orm_obj.pnl_pct), 2) if orm_obj.pnl_pct is not None else None,
        holding_days=orm_obj.holding_days,
        confidence=orm_obj.confidence,
        strategy_score=orm_obj.strategy_score,
        market_regime=orm_obj.market_regime,
    )


def _position_model_from_orm(orm_obj: PaperPositionORM) -> PaperPosition:
    side = _position_side(orm_obj)
    market_value = _signed_position_value(orm_obj.current_price, orm_obj.quantity, side)
    invested_value = _signed_position_value(orm_obj.entry_price, orm_obj.quantity, side)
    unrealised_pnl = market_value - invested_value
    unrealised_pnl_pct = (unrealised_pnl / abs(invested_value) * 100) if invested_value else 0.0
    return PaperPosition(
        symbol=orm_obj.symbol,
        side=side,
        quantity=orm_obj.quantity,
        entry_price=round(orm_obj.entry_price, 2),
        current_price=round(orm_obj.current_price, 2),
        market_value=round(market_value, 2),
        invested_value=round(invested_value, 2),
        target_price=round(orm_obj.target_price, 2),
        stop_loss=round(orm_obj.stop_loss, 2),
        opened_at=datetime.fromisoformat(orm_obj.opened_at),
        last_marked_at=datetime.fromisoformat(orm_obj.last_marked_at),
        days_held=orm_obj.days_held,
        confidence=round(orm_obj.confidence, 2),
        strategy_score=round(orm_obj.strategy_score, 2),
        unrealised_pnl=round(unrealised_pnl, 2),
        unrealised_pnl_pct=round(unrealised_pnl_pct, 2),
        rationale=_from_json(orm_obj.rationale_json, []),
    )


def _snapshot_model_from_orm(orm_obj: PaperSnapshotORM) -> PaperPortfolioSnapshot:
    return PaperPortfolioSnapshot(
        as_of_date=datetime.fromisoformat(orm_obj.as_of_date),
        cash_balance=round(orm_obj.cash_balance, 2),
        market_value=round(orm_obj.market_value, 2),
        total_equity=round(orm_obj.total_equity, 2),
        realised_pnl=round(orm_obj.realised_pnl, 2),
        unrealised_pnl=round(orm_obj.unrealised_pnl, 2),
        total_return_pct=round(orm_obj.total_return_pct, 2),
        daily_pnl=round(orm_obj.daily_pnl, 2),
        weekly_pnl=round(orm_obj.weekly_pnl, 2),
        monthly_pnl=round(orm_obj.monthly_pnl, 2),
        open_positions=orm_obj.open_positions,
        closed_trades=orm_obj.closed_trades,
        market_regime=orm_obj.market_regime,
    )


async def get_learning_state() -> StrategyLearningState:
    async with AsyncSessionLocal() as session:
        state = await _get_or_create_strategy_state(session)
        await session.commit()
        return StrategyLearningState(
            weights=_from_json(state.weights_json, _default_weights()),
            learning_rate=state.learning_rate,
            trades_evaluated=state.trades_evaluated,
            last_updated=datetime.fromisoformat(state.updated_at),
        )


async def list_paper_trades(limit: int = 50) -> list[PaperTrade]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PaperTradeORM).order_by(PaperTradeORM.id.desc()).limit(limit))
        return [_trade_model_from_orm(item) for item in result.scalars().all()]


async def list_paper_snapshots(limit: int = 60) -> list[PaperPortfolioSnapshot]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PaperSnapshotORM).order_by(PaperSnapshotORM.as_of_date.desc()).limit(limit))
        return [_snapshot_model_from_orm(item) for item in result.scalars().all()]


async def reset_paper_trading(account_size: float = settings.default_account_size) -> dict:
    async with AsyncSessionLocal() as session:
        for model in (SignalJournalORM, PaperTradeORM, PaperSnapshotORM, PaperPositionORM, StrategyStateORM, PaperAccountORM):
            await session.execute(delete(model))

        account = PaperAccountORM(id=1, starting_cash=account_size, cash_balance=account_size)
        state = StrategyStateORM(
            id=1,
            weights_json=_to_json(_default_weights()),
            learning_rate=settings.paper_learning_rate,
            trades_evaluated=0,
        )
        session.add_all([account, state])
        await session.commit()

    return {"message": "Paper trading state reset", "starting_cash": round(account_size, 2)}


async def get_paper_portfolio_summary() -> PaperPortfolioSummary:
    async with AsyncSessionLocal() as session:
        account = await _get_or_create_account(session, settings.default_account_size)
        strategy_state = await _get_or_create_strategy_state(session)

        positions_result = await session.execute(select(PaperPositionORM).order_by(PaperPositionORM.symbol))
        trade_result = await session.execute(select(PaperTradeORM).order_by(PaperTradeORM.id.desc()).limit(25))
        realised_result = await session.execute(select(PaperTradeORM))
        snapshot_result = await session.execute(select(PaperSnapshotORM).order_by(PaperSnapshotORM.as_of_date))

        positions = positions_result.scalars().all()
        trades = trade_result.scalars().all()
        realised_trades = realised_result.scalars().all()
        snapshots = snapshot_result.scalars().all()

        market_value = sum(
            _signed_position_value(position.current_price, position.quantity, _position_side(position))
            for position in positions
        )
        invested_value = sum(
            _signed_position_value(position.entry_price, position.quantity, _position_side(position))
            for position in positions
        )
        realised_pnl = sum(float(trade.pnl or 0.0) for trade in realised_trades if trade.pnl is not None)
        unrealised_pnl = market_value - invested_value
        total_equity = account.cash_balance + market_value
        total_return_pct = ((total_equity - account.starting_cash) / account.starting_cash * 100) if account.starting_cash else 0.0

        latest_snapshot = _snapshot_model_from_orm(snapshots[-1]) if snapshots else None
        weekly_actual = latest_snapshot.weekly_pnl if latest_snapshot else 0.0
        monthly_actual = latest_snapshot.monthly_pnl if latest_snapshot else 0.0
        daily_actual = latest_snapshot.daily_pnl if latest_snapshot else 0.0
        goals = _goal_targets(account.starting_cash)

        await session.commit()
        return PaperPortfolioSummary(
            starting_cash=round(account.starting_cash, 2),
            cash_balance=round(account.cash_balance, 2),
            market_value=round(market_value, 2),
            total_equity=round(total_equity, 2),
            realised_pnl=round(realised_pnl, 2),
            unrealised_pnl=round(unrealised_pnl, 2),
            total_return_pct=round(total_return_pct, 2),
            open_positions=[_position_model_from_orm(position) for position in positions],
            recent_trades=[_trade_model_from_orm(trade) for trade in trades],
            latest_snapshot=latest_snapshot,
            daily_goal=_goal_progress(daily_actual, goals["daily"]),
            weekly_goal=_goal_progress(weekly_actual, goals["weekly"]),
            monthly_goal=_goal_progress(monthly_actual, goals["monthly"]),
            learning_state=StrategyLearningState(
                weights=_from_json(strategy_state.weights_json, _default_weights()),
                learning_rate=strategy_state.learning_rate,
                trades_evaluated=strategy_state.trades_evaluated,
                last_updated=datetime.fromisoformat(strategy_state.updated_at),
            ),
        )


def _build_historical_signal(
    symbol: str,
    df: pd.DataFrame,
    context: PlanningContext,
    weights: dict[str, float],
    intelligence: IntelligenceSnapshot | None = None,
) -> Optional[tuple[TradeSignal, dict[str, float]]]:
    if df.empty or len(df) < 60:
        return None

    price = float(df["Close"].iloc[-1])
    signal_type, confidence, rationale, strategy_score = _score_stock(df, intelligence=intelligence)
    if signal_type not in {"BUY", "SELL"}:
        return None

    target_price, stop_loss = _compute_target_and_stop(price, signal_type, df)
    backtest = _backtest_signal(df, signal_type, context.max_hold_days)
    trade_plan = _build_trade_plan(price, target_price, stop_loss, signal_type, backtest, context)
    if not _passes_trade_quality_gate(
        signal_type=signal_type,
        confidence=confidence,
        strategy_score=strategy_score,
        backtest=backtest,
        trade_plan=trade_plan,
        daily_profit_target=context.daily_profit_target,
        intelligence=intelligence,
    ):
        return None

    signal = TradeSignal(
        symbol=symbol,
        signal_type=signal_type,
        confidence=confidence,
        strategy_score=_rank_signal(
            signal_type=signal_type,
            confidence=confidence,
            strategy_score=strategy_score,
            backtest=backtest,
            trade_plan=trade_plan,
            daily_profit_target=context.daily_profit_target,
        ),
        entry_price=round(price, 2),
        target_price=target_price,
        stop_loss=stop_loss,
        expected_return_pct=round(settings.profit_target * 100 if signal_type == "BUY" else -settings.profit_target * 100, 2),
        rationale=rationale,
        trade_plan=trade_plan,
        backtest=backtest,
        intelligence=intelligence,
        timeframe="weekly",
        generated_at=datetime.utcnow(),
    )
    features = _feature_snapshot(signal, context.daily_profit_target)
    signal.strategy_score = _adaptive_score(features, weights)
    return signal, features


async def _run_cycle_with_histories(
    histories: dict[str, pd.DataFrame],
    as_of_date: date,
    context: PlanningContext,
) -> PaperCycleResult:
    market_df = _slice_to_date(histories.get("SPY", pd.DataFrame()), as_of_date)
    market_regime = _derive_market_regime(market_df)
    latest_market_date = histories.get("SPY", pd.DataFrame()).index[-1].date() if not histories.get("SPY", pd.DataFrame()).empty else as_of_date
    use_live_intelligence = as_of_date == latest_market_date

    async with AsyncSessionLocal() as session:
        account = await _get_or_create_account(session, context.account_size)
        strategy_state = await _get_or_create_strategy_state(session)
        await _refresh_learning_state(session, strategy_state)

        snapshot_result = await session.execute(select(PaperSnapshotORM).where(PaperSnapshotORM.as_of_date == _date_key(as_of_date)))
        existing_snapshot = snapshot_result.scalar_one_or_none()
        if existing_snapshot is not None:
            await session.commit()
            return PaperCycleResult(
                as_of_date=_dt_from_date(as_of_date),
                market_regime=existing_snapshot.market_regime,
                buys_executed=[],
                sells_executed=[],
                skipped_symbols=[],
                summary=await get_paper_portfolio_summary(),
            )

        weights = _from_json(strategy_state.weights_json, _default_weights())
        positions_result = await session.execute(select(PaperPositionORM).order_by(PaperPositionORM.symbol))
        open_positions = positions_result.scalars().all()

        sells_executed: list[PaperTrade] = []
        for position in list(open_positions):
            history = histories.get(position.symbol, pd.DataFrame())
            row = _row_for_date(history, as_of_date)
            if row is None:
                continue

            position_side = _position_side(position)
            high = float(row.get("High", row["Close"]))
            low = float(row.get("Low", row["Close"]))
            close = float(row["Close"])
            position.current_price = close
            position.last_marked_at = _dt_from_date(as_of_date).isoformat()
            position.days_held = _count_holding_days(history, _as_date(position.opened_at) or as_of_date, as_of_date)

            exit_price: Optional[float] = None
            exit_reason: Optional[str] = None
            if position_side == "LONG":
                if low <= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "stop_loss"
                elif high >= position.target_price:
                    exit_price = position.target_price
                    exit_reason = "target_hit"
            else:
                if high >= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "stop_loss"
                elif low <= position.target_price:
                    exit_price = position.target_price
                    exit_reason = "target_hit"
            if exit_price is None and position.days_held >= context.max_hold_days:
                exit_price = close
                exit_reason = "max_hold"

            if exit_price is not None:
                entry_value = position.entry_price * position.quantity
                if position_side == "LONG":
                    proceeds = exit_price * position.quantity
                    account.cash_balance += proceeds
                    pnl = proceeds - entry_value
                    close_side = "SELL"
                else:
                    cover_cost = exit_price * position.quantity
                    account.cash_balance -= cover_cost
                    pnl = entry_value - cover_cost
                    close_side = "BUY_TO_COVER"
                pnl_pct = (pnl / entry_value * 100) if entry_value else 0.0
                trade_orm = PaperTradeORM(
                    symbol=position.symbol,
                    side=close_side,
                    quantity=position.quantity,
                    price=exit_price,
                    executed_at=_dt_from_date(as_of_date).isoformat(),
                    reason=exit_reason,
                    pnl=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    holding_days=position.days_held,
                    confidence=position.confidence,
                    strategy_score=position.strategy_score,
                    market_regime=market_regime,
                    feature_json=position.feature_json,
                )
                session.add(trade_orm)
                sells_executed.append(_trade_model_from_orm(trade_orm))
                await session.delete(position)

        await session.flush()
        account.updated_at = datetime.utcnow().isoformat()

        positions_result = await session.execute(select(PaperPositionORM).order_by(PaperPositionORM.symbol))
        open_positions = positions_result.scalars().all()
        held_symbols = {position.symbol for position in open_positions}

        candidates: list[tuple[TradeSignal, dict[str, float]]] = []
        for symbol in get_tickers():
            if symbol in held_symbols:
                continue
            historical_df = _slice_to_date(histories.get(symbol, pd.DataFrame()), as_of_date)
            current_price = float(historical_df["Close"].iloc[-1]) if not historical_df.empty else None
            intelligence = fetch_intelligence_snapshot(symbol, current_price=current_price) if use_live_intelligence and current_price is not None else None
            candidate = _build_historical_signal(symbol, historical_df, context, weights, intelligence=intelligence)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(key=lambda item: item[0].strategy_score or 0.0, reverse=True)
        available_slots = max(context.max_positions - len(open_positions), 0)
        buys_executed: list[PaperTrade] = []
        skipped_symbols: list[str] = []

        for signal, features in candidates:
            selected = False
            if available_slots > 0 and signal.trade_plan is not None and signal.entry_price is not None:
                capital_limited_shares = int(signal.trade_plan.capital_per_position // signal.entry_price)
                if signal.signal_type == "BUY":
                    cash_limited_shares = int(account.cash_balance // signal.entry_price)
                    max_affordable_shares = min(capital_limited_shares, cash_limited_shares)
                else:
                    max_affordable_shares = capital_limited_shares
                shares = min(signal.trade_plan.recommended_shares, max_affordable_shares)
                if shares > 0:
                    trade_value = round(shares * signal.entry_price, 2)
                    if signal.signal_type == "BUY":
                        account.cash_balance -= trade_value
                        position_side = "LONG"
                        opening_side = "BUY"
                    else:
                        account.cash_balance += trade_value
                        position_side = "SHORT"
                        opening_side = "SELL_SHORT"
                    selected = True
                    available_slots -= 1
                    position = PaperPositionORM(
                        symbol=signal.symbol,
                        side=position_side,
                        quantity=shares,
                        entry_price=signal.entry_price,
                        current_price=signal.entry_price,
                        target_price=signal.target_price or signal.entry_price,
                        stop_loss=signal.stop_loss or signal.entry_price,
                        opened_at=_dt_from_date(as_of_date).isoformat(),
                        last_marked_at=_dt_from_date(as_of_date).isoformat(),
                        days_held=0,
                        confidence=signal.confidence,
                        strategy_score=float(signal.strategy_score or 0.0),
                        rationale_json=_to_json(signal.rationale),
                        feature_json=_to_json(features),
                    )
                    buy_trade = PaperTradeORM(
                        symbol=signal.symbol,
                        side=opening_side,
                        quantity=shares,
                        price=signal.entry_price,
                        executed_at=_dt_from_date(as_of_date).isoformat(),
                        reason="signal_entry",
                        confidence=signal.confidence,
                        strategy_score=float(signal.strategy_score or 0.0),
                        market_regime=market_regime,
                        feature_json=_to_json(features),
                    )
                    session.add(position)
                    session.add(buy_trade)
                    buys_executed.append(_trade_model_from_orm(buy_trade))
                else:
                    skipped_symbols.append(signal.symbol)
            else:
                skipped_symbols.append(signal.symbol)

            journal = SignalJournalORM(
                as_of_date=_dt_from_date(as_of_date).isoformat(),
                symbol=signal.symbol,
                signal_type=signal.signal_type,
                selected=selected,
                confidence=signal.confidence,
                strategy_score=float(signal.strategy_score or 0.0),
                market_regime=market_regime,
                feature_json=_to_json(features),
                rationale_json=_to_json(signal.rationale),
            )
            session.add(journal)

        await session.flush()
        await _refresh_learning_state(session, strategy_state)

        positions_result = await session.execute(select(PaperPositionORM).order_by(PaperPositionORM.symbol))
        open_positions = positions_result.scalars().all()
        trades_result = await session.execute(select(PaperTradeORM).order_by(PaperTradeORM.id))
        all_trades = trades_result.scalars().all()
        snapshots_result = await session.execute(select(PaperSnapshotORM).order_by(PaperSnapshotORM.as_of_date))
        snapshots = snapshots_result.scalars().all()

        market_value = sum(
            _signed_position_value(position.current_price, position.quantity, _position_side(position))
            for position in open_positions
        )
        invested_value = sum(
            _signed_position_value(position.entry_price, position.quantity, _position_side(position))
            for position in open_positions
        )
        realised_pnl = sum(float(trade.pnl or 0.0) for trade in all_trades if trade.pnl is not None)
        unrealised_pnl = market_value - invested_value
        total_equity = account.cash_balance + market_value
        previous_equity = snapshots[-1].total_equity if snapshots else account.starting_cash
        daily_pnl = total_equity - previous_equity
        weekly_equity = snapshots[-5].total_equity if len(snapshots) >= 5 else account.starting_cash
        monthly_equity = snapshots[-20].total_equity if len(snapshots) >= 20 else account.starting_cash
        total_return_pct = ((total_equity - account.starting_cash) / account.starting_cash * 100) if account.starting_cash else 0.0

        snapshot = PaperSnapshotORM(
            as_of_date=_dt_from_date(as_of_date).isoformat(),
            cash_balance=round(account.cash_balance, 2),
            market_value=round(market_value, 2),
            total_equity=round(total_equity, 2),
            realised_pnl=round(realised_pnl, 2),
            unrealised_pnl=round(unrealised_pnl, 2),
            total_return_pct=round(total_return_pct, 2),
            daily_pnl=round(daily_pnl, 2),
            weekly_pnl=round(total_equity - weekly_equity, 2),
            monthly_pnl=round(total_equity - monthly_equity, 2),
            open_positions=len(open_positions),
            closed_trades=sum(1 for trade in all_trades if trade.pnl is not None),
            market_regime=market_regime,
        )
        session.add(snapshot)
        account.updated_at = datetime.utcnow().isoformat()
        await session.commit()

    return PaperCycleResult(
        as_of_date=_dt_from_date(as_of_date),
        market_regime=market_regime,
        buys_executed=buys_executed,
        sells_executed=sells_executed,
        skipped_symbols=sorted(set(skipped_symbols)),
        summary=await get_paper_portfolio_summary(),
    )


async def run_paper_cycle(
    account_size: float = settings.default_account_size,
    daily_profit_target: float = settings.default_daily_profit_target,
    max_positions: int = settings.max_positions,
    risk_per_trade_pct: float = settings.risk_per_trade_pct,
    min_hold_days: int = settings.min_hold_days,
    max_hold_days: int = settings.max_hold_days,
    as_of: Optional[str] = None,
) -> PaperCycleResult:
    histories = await _load_histories()
    spy_history = histories.get("SPY", pd.DataFrame())
    fallback_date = _latest_history_date(histories)
    if fallback_date is None:
        raise ValueError("Unable to load market history for paper-trading cycle.")
    if spy_history.empty:
        logger.warning("SPY market history unavailable; running paper cycle with neutral market fallback")

    as_of_date = datetime.fromisoformat(as_of).date() if as_of else (spy_history.index[-1].date() if not spy_history.empty else fallback_date)
    context = PlanningContext(
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max(max_hold_days, min_hold_days),
    )
    return await _run_cycle_with_histories(histories, as_of_date, context)


async def replay_paper_trading(
    days: int = 30,
    reset: bool = False,
    account_size: float = settings.default_account_size,
    daily_profit_target: float = settings.default_daily_profit_target,
    max_positions: int = settings.max_positions,
    risk_per_trade_pct: float = settings.risk_per_trade_pct,
    min_hold_days: int = settings.min_hold_days,
    max_hold_days: int = settings.max_hold_days,
) -> dict:
    if reset:
        await reset_paper_trading(account_size=account_size)

    histories = await _load_histories()
    spy_history = histories.get("SPY", pd.DataFrame())
    fallback_date = _latest_history_date(histories)
    if fallback_date is None:
        raise ValueError("Unable to load market history for replay.")
    if spy_history.empty:
        logger.warning("SPY market history unavailable; replay will use available symbol histories only")

    if not spy_history.empty:
        dates = [idx.date() for idx in spy_history.index[-days:]]
    else:
        start_date = fallback_date - pd.Timedelta(days=max(days * 2, days))
        available_dates = sorted(
            {
                idx.date()
                for df in histories.values()
                if not df.empty
                for idx in df.index
                if idx.date() >= start_date.date()
            }
        )
        dates = available_dates[-days:]
    context = PlanningContext(
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max(max_hold_days, min_hold_days),
    )

    last_result: Optional[PaperCycleResult] = None
    for trading_date in dates:
        last_result = await _run_cycle_with_histories(histories, trading_date, context)

    return {
        "days_replayed": len(dates),
        "last_cycle": last_result,
        "summary": await get_paper_portfolio_summary(),
    }
