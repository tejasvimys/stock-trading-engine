"""Swing-trade signal engine with position sizing and paper-trading evidence."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple

import pandas as pd

from config import settings
from models import BacktestSummary, IntelligenceSnapshot, TradePlan, TradeSignal
from services.data_fetcher import (
    build_intelligence_snapshot,
    fetch_calendar,
    fetch_info,
    fetch_multiple,
    fetch_news,
    fetch_options_summary,
    get_latest_price,
    get_tickers,
)
from services.screener import compute_indicators

logger = logging.getLogger(__name__)

PROFIT_TARGET = settings.profit_target  # default 0.10 (10%)
STOP_LOSS_FACTOR = 0.05  # 5% stop loss


@dataclass(frozen=True)
class PlanningContext:
    account_size: float
    daily_profit_target: float
    max_positions: int
    risk_per_trade_pct: float
    min_hold_days: int
    max_hold_days: int


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _recent_return(close: pd.Series, days: int) -> float | None:
    if len(close) <= days:
        return None
    base = float(close.iloc[-days - 1])
    if base == 0:
        return None
    return (float(close.iloc[-1]) - base) / base


def _estimate_stop_buffer_pct(df: pd.DataFrame) -> float:
    returns = df["Close"].pct_change().dropna().tail(20)
    if returns.empty:
        return STOP_LOSS_FACTOR
    return round(_clamp(float(returns.std()) * 2.5, 0.03, 0.08), 4)


def _compute_target_and_stop(price: float, signal_type: str, df: pd.DataFrame) -> Tuple[float, float]:
    stop_buffer = _estimate_stop_buffer_pct(df)
    if signal_type == "BUY":
        target = round(price * (1 + PROFIT_TARGET), 2)
        stop = round(price * (1 - stop_buffer), 2)
    else:
        target = round(price * (1 - PROFIT_TARGET), 2)
        stop = round(price * (1 + stop_buffer), 2)
    return target, stop


def _score_stock(
    df: pd.DataFrame,
    intelligence: IntelligenceSnapshot | None = None,
) -> Tuple[str, float, List[str], float]:
    """
    Return (signal_type, confidence, rationale_list, strategy_score).
    signal_type: 'BUY' | 'SELL' | 'HOLD'
    confidence : 0.0 – 1.0
    """
    ind = compute_indicators(df)
    rationale: List[str] = []
    buy_score = 0.0
    sell_score = 0.0
    max_score = 0.0

    close = df["Close"]
    price = float(close.iloc[-1])
    ret_5d = _recent_return(close, 5)
    ret_10d = _recent_return(close, 10)
    volatility = float(close.pct_change().dropna().tail(20).std() or 0.0)

    # --- Trend regime ---
    if ind.sma_50 is not None and ind.sma_20 is not None:
        max_score += 2.0
        if price > ind.sma_20 > ind.sma_50:
            buy_score += 2.0
            rationale.append("Strong uptrend: price > SMA20 > SMA50")
        elif price < ind.sma_20 < ind.sma_50:
            sell_score += 2.0
            rationale.append("Strong downtrend: price < SMA20 < SMA50")
        elif price > ind.sma_50:
            buy_score += 1.0
            rationale.append(f"Price holding above SMA50 ({ind.sma_50:.2f})")
        else:
            sell_score += 1.0
            rationale.append(f"Price trading below SMA50 ({ind.sma_50:.2f})")

    # --- RSI ---
    if ind.rsi is not None:
        max_score += 1.5
        if 45 <= ind.rsi <= 62:
            buy_score += 1.5
            rationale.append(f"RSI in bullish swing zone ({ind.rsi:.1f})")
        elif 35 <= ind.rsi < 45 and (ind.sma_50 is None or price > ind.sma_50):
            buy_score += 1.0
            rationale.append(f"RSI pullback within uptrend ({ind.rsi:.1f})")
        elif ind.rsi < 30:
            buy_score += 0.75
            rationale.append(f"RSI deeply oversold ({ind.rsi:.1f})")
        elif ind.rsi > 70:
            sell_score += 1.5
            rationale.append(f"RSI overbought ({ind.rsi:.1f})")
        elif 38 <= ind.rsi <= 55:
            sell_score += 0.75
            rationale.append(f"RSI losing momentum ({ind.rsi:.1f})")

    # --- MACD crossover ---
    if ind.macd is not None and ind.macd_signal is not None:
        max_score += 1.5
        if ind.macd > ind.macd_signal and (ind.macd_hist or 0) >= 0:
            buy_score += 1.5
            rationale.append("MACD bullish crossover with positive histogram")
        elif ind.macd < ind.macd_signal and (ind.macd_hist or 0) <= 0:
            sell_score += 1.5
            rationale.append("MACD bearish crossover with negative histogram")

    # --- Bollinger context ---
    if ind.bb_lower is not None and ind.bb_upper is not None and ind.bb_middle is not None:
        max_score += 1.0
        if ind.bb_middle <= price < ind.bb_upper:
            buy_score += 1.0
            rationale.append("Price advancing in upper half of Bollinger range")
        elif price <= ind.bb_lower and (ind.sma_50 is None or price > ind.sma_50):
            buy_score += 0.75
            rationale.append("Price pulling back to lower Bollinger band support")
        elif price >= ind.bb_upper:
            sell_score += 1.0
            rationale.append("Price stretched near upper Bollinger band")

    # --- Volume surge ---
    if ind.volume_avg is not None and not df.empty:
        max_score += 1.0
        vol_today = float(df["Volume"].iloc[-1])
        if vol_today > 1.25 * ind.volume_avg:
            if (ret_5d or 0) >= 0:
                buy_score += 1.0
                rationale.append(f"Volume expansion ({vol_today / ind.volume_avg:.1f}x avg)")
            else:
                sell_score += 1.0
                rationale.append("Heavy volume on downside move")

    # --- Multi-day momentum ---
    max_score += 2.0
    if ret_5d is not None:
        if ret_5d > 0.015:
            buy_score += 1.0
            rationale.append(f"5-day momentum +{ret_5d * 100:.1f}%")
        elif ret_5d < -0.015:
            sell_score += 1.0
            rationale.append(f"5-day momentum {ret_5d * 100:.1f}%")
    if ret_10d is not None:
        if ret_10d > 0.03:
            buy_score += 1.0
            rationale.append(f"10-day trend +{ret_10d * 100:.1f}%")
        elif ret_10d < -0.03:
            sell_score += 1.0
            rationale.append(f"10-day trend {ret_10d * 100:.1f}%")

    # --- Volatility quality ---
    max_score += 1.0
    if volatility <= 0.03:
        if buy_score >= sell_score:
            buy_score += 1.0
            rationale.append("Volatility is controlled for a swing setup")
        else:
            sell_score += 1.0
            rationale.append("Volatility supports a controlled downside setup")
    elif volatility >= 0.055:
        rationale.append("Volatility is elevated; size positions cautiously")

    if intelligence is not None:
        max_score += 3.5
        if intelligence.fundamentals.score >= 0.65:
            buy_score += 1.0
            rationale.append(f"Fundamentals supportive ({intelligence.fundamentals.score:.2f})")
        elif intelligence.fundamentals.score <= 0.35:
            sell_score += 1.0
            rationale.append(f"Fundamentals weak ({intelligence.fundamentals.score:.2f})")

        if intelligence.analyst.score >= 0.65:
            buy_score += 0.75
            rationale.append("Analyst consensus and targets support upside")
        elif intelligence.analyst.score <= 0.35:
            sell_score += 0.75
            rationale.append("Analyst positioning is cautious")

        if intelligence.sentiment.score >= 0.6:
            buy_score += 0.5
            rationale.append("Recent news sentiment is favorable")
        elif intelligence.sentiment.score <= 0.4:
            sell_score += 0.5
            rationale.append("Recent news sentiment is unfavorable")

        if intelligence.options.score >= 0.6:
            buy_score += 0.5
            rationale.append("Options flow is constructive")
        elif intelligence.options.score <= 0.4:
            sell_score += 0.5
            rationale.append("Options flow is defensive")

        if intelligence.events.score <= 0.35:
            sell_score += 0.75
            rationale.append("Near-term event risk is elevated")
        elif intelligence.events.score >= 0.6:
            buy_score += 0.25

        rationale.extend(intelligence.notes)

    if max_score == 0:
        return "HOLD", 0.0, [], 0.0

    dominant = max(buy_score, sell_score)
    opposing = min(buy_score, sell_score)
    edge = dominant - opposing
    confidence = round(min(dominant / max_score, 1.0), 2)
    strategy_score = round(min((dominant - (0.35 * opposing)) / max_score, 1.0), 2)

    if dominant < 3.0 or edge < 1.25:
        return "HOLD", confidence, ["Mixed signals – no clear swing edge"], strategy_score

    if buy_score > sell_score:
        return "BUY", confidence, rationale, strategy_score
    return "SELL", confidence, rationale, strategy_score


def _simulate_trade_path(
    future_df: pd.DataFrame,
    signal_type: str,
    entry_price: float,
    target_price: float,
    stop_loss: float,
    max_hold_days: int,
) -> Tuple[float, int, str]:
    if future_df.empty:
        return 0.0, 0, "no-data"

    horizon = future_df.head(max_hold_days)
    for hold_days, (_, row) in enumerate(horizon.iterrows(), start=1):
        high = float(row.get("High", row["Close"]))
        low = float(row.get("Low", row["Close"]))

        if signal_type == "BUY":
            # Conservative assumption with daily candles: stop is hit before target.
            if low <= stop_loss:
                return round(((stop_loss - entry_price) / entry_price) * 100, 2), hold_days, "stop"
            if high >= target_price:
                return round(((target_price - entry_price) / entry_price) * 100, 2), hold_days, "target"
        else:
            if high >= stop_loss:
                return round(((entry_price - stop_loss) / entry_price) * 100, 2), hold_days, "stop"
            if low <= target_price:
                return round(((entry_price - target_price) / entry_price) * 100, 2), hold_days, "target"

    exit_price = float(horizon["Close"].iloc[-1])
    if signal_type == "BUY":
        return round(((exit_price - entry_price) / entry_price) * 100, 2), len(horizon), "time"
    return round(((entry_price - exit_price) / entry_price) * 100, 2), len(horizon), "time"


def _backtest_signal(df: pd.DataFrame, signal_type: str, max_hold_days: int) -> BacktestSummary:
    if signal_type not in {"BUY", "SELL"} or len(df) < 80:
        return BacktestSummary()

    start_index = max(55, len(df) - settings.backtest_lookback_bars)
    results: List[Tuple[float, int]] = []

    for end_idx in range(start_index, len(df) - max_hold_days):
        history = df.iloc[:end_idx]
        historical_signal, confidence, _, strategy_score = _score_stock(history)
        if historical_signal != signal_type or confidence < 0.55 or strategy_score < 0.5:
            continue

        entry_price = float(df["Close"].iloc[end_idx])
        target_price, stop_loss = _compute_target_and_stop(entry_price, signal_type, history)
        future_df = df.iloc[end_idx + 1 : end_idx + 1 + max_hold_days]
        trade_return, hold_days, _ = _simulate_trade_path(
            future_df=future_df,
            signal_type=signal_type,
            entry_price=entry_price,
            target_price=target_price,
            stop_loss=stop_loss,
            max_hold_days=max_hold_days,
        )
        results.append((trade_return, hold_days))

    if not results:
        return BacktestSummary()

    trades = len(results)
    wins = sum(1 for ret, _ in results if ret > 0)
    losses = trades - wins
    avg_return = sum(ret for ret, _ in results) / trades
    avg_hold_days = sum(days for _, days in results) / trades

    return BacktestSummary(
        trades=trades,
        wins=wins,
        losses=losses,
        win_rate=round(wins / trades, 2),
        avg_return_pct=round(avg_return, 2),
        expected_value_pct=round(avg_return, 2),
        avg_hold_days=round(avg_hold_days, 1),
    )


def _build_trade_plan(
    price: float,
    target_price: float,
    stop_loss: float,
    signal_type: str,
    backtest: BacktestSummary,
    context: PlanningContext,
) -> TradePlan | None:
    if signal_type not in {"BUY", "SELL"}:
        return None

    capital_per_position = context.account_size / context.max_positions
    risk_budget_usd = context.account_size * context.risk_per_trade_pct
    if signal_type == "BUY":
        profit_per_share = max(target_price - price, 0.01)
        risk_per_share = max(price - stop_loss, 0.01)
    else:
        profit_per_share = max(price - target_price, 0.01)
        risk_per_share = max(stop_loss - price, 0.01)

    max_shares_by_capital = int(capital_per_position // price)
    max_shares_by_risk = int(risk_budget_usd // risk_per_share)
    recommended_shares = max(0, min(max_shares_by_capital, max_shares_by_risk))
    expected_hold_days = int(round(backtest.avg_hold_days or context.max_hold_days))
    expected_hold_days = max(context.min_hold_days, min(context.max_hold_days, expected_hold_days))

    position_size_usd = round(recommended_shares * price, 2)
    projected_profit_usd = round(recommended_shares * profit_per_share, 2)
    projected_daily_profit_usd = round(projected_profit_usd / expected_hold_days, 2) if expected_hold_days else 0.0
    risk_amount_usd = round(recommended_shares * risk_per_share, 2)
    reward_risk_ratio = round(profit_per_share / risk_per_share, 2) if risk_per_share else None

    return TradePlan(
        account_size=context.account_size,
        daily_profit_target=context.daily_profit_target,
        capital_per_position=round(capital_per_position, 2),
        risk_budget_usd=round(risk_budget_usd, 2),
        recommended_shares=recommended_shares,
        position_size_usd=position_size_usd,
        projected_profit_usd=projected_profit_usd,
        projected_daily_profit_usd=projected_daily_profit_usd,
        risk_amount_usd=risk_amount_usd,
        reward_risk_ratio=reward_risk_ratio,
        min_holding_days=context.min_hold_days,
        max_holding_days=context.max_hold_days,
    )


def _passes_trade_quality_gate(
    signal_type: str,
    confidence: float,
    strategy_score: float,
    backtest: BacktestSummary,
    trade_plan: TradePlan | None,
    daily_profit_target: float,
    intelligence: IntelligenceSnapshot | None = None,
) -> bool:
    if signal_type not in {"BUY", "SELL"}:
        return False

    if trade_plan is None or trade_plan.recommended_shares <= 0:
        return False

    if confidence < 0.54 or strategy_score < 0.5:
        return False

    reward_risk_ratio = trade_plan.reward_risk_ratio or 0.0
    if reward_risk_ratio < 1.45:
        return False

    if trade_plan.projected_daily_profit_usd < (daily_profit_target * 0.18):
        return False

    if backtest.trades >= 3:
        if (backtest.expected_value_pct or 0.0) <= 0.0:
            return False
        if (backtest.win_rate or 0.0) < 0.46:
            return False
    else:
        if confidence < 0.61 or strategy_score < 0.57:
            return False

    if intelligence is not None:
        if intelligence.composite_score < 0.48:
            return False
        if intelligence.events.score <= 0.35:
            return False

    return True


def _rank_signal(
    signal_type: str,
    confidence: float,
    strategy_score: float,
    backtest: BacktestSummary,
    trade_plan: TradePlan | None,
    daily_profit_target: float,
    intelligence: IntelligenceSnapshot | None = None,
) -> float:
    win_rate = backtest.win_rate or 0.0
    expected_value = backtest.expected_value_pct or 0.0
    expected_value_component = _clamp((expected_value + 5.0) / 10.0, 0.0, 1.0)
    profit_component = 0.0
    intelligence_component = intelligence.composite_score if intelligence is not None else 0.5
    if trade_plan and daily_profit_target > 0:
        profit_component = _clamp(trade_plan.projected_daily_profit_usd / daily_profit_target, 0.0, 1.0)

    weight = (
        0.35 * strategy_score
        + 0.2 * confidence
        + 0.15 * win_rate
        + 0.1 * expected_value_component
        + 0.15 * intelligence_component
    )
    if signal_type in {"BUY", "SELL"}:
        weight += 0.05 * profit_component
    return round(min(weight, 1.0), 2)


def _passes_buy_quality_gate(
    confidence: float,
    strategy_score: float,
    backtest: BacktestSummary,
    trade_plan: TradePlan | None,
    daily_profit_target: float,
    intelligence: IntelligenceSnapshot | None = None,
) -> bool:
    return _passes_trade_quality_gate(
        signal_type="BUY",
        confidence=confidence,
        strategy_score=strategy_score,
        backtest=backtest,
        trade_plan=trade_plan,
        daily_profit_target=daily_profit_target,
        intelligence=intelligence,
    )


async def generate_signals(
    timeframe: str = "weekly",
    account_size: float = settings.default_account_size,
    daily_profit_target: float = settings.default_daily_profit_target,
    max_positions: int = settings.max_positions,
    risk_per_trade_pct: float = settings.risk_per_trade_pct,
    min_hold_days: int = settings.min_hold_days,
    max_hold_days: int = settings.max_hold_days,
) -> dict:
    """Generate buy/sell signals for all tracked stocks."""
    context = PlanningContext(
        account_size=account_size,
        daily_profit_target=daily_profit_target,
        max_positions=max_positions,
        risk_per_trade_pct=risk_per_trade_pct,
        min_hold_days=min_hold_days,
        max_hold_days=max(max_hold_days, min_hold_days),
    )
    symbols = get_tickers()
    period = "3mo" if timeframe == "weekly" else "6mo"
    all_data = await fetch_multiple(symbols, period=period)

    buy_signals: List[TradeSignal] = []
    sell_signals: List[TradeSignal] = []

    for sym, df in all_data.items():
        if df.empty or len(df) < 26:
            continue

        info = fetch_info(sym)
        price = get_latest_price(df)
        if price is None:
            continue

        intelligence = build_intelligence_snapshot(
            info=info,
            news_items=fetch_news(sym),
            options_summary=fetch_options_summary(sym),
            calendar=fetch_calendar(sym),
            current_price=price,
        )

        signal_type, confidence, rationale, strategy_score = _score_stock(df, intelligence=intelligence)
        if signal_type == "HOLD":
            continue

        target, stop = _compute_target_and_stop(price, signal_type, df)
        backtest = _backtest_signal(df, signal_type, context.max_hold_days)
        trade_plan = _build_trade_plan(price, target, stop, signal_type, backtest, context)
        if trade_plan is not None:
            if not _passes_trade_quality_gate(
                signal_type=signal_type,
                confidence=confidence,
                strategy_score=strategy_score,
                backtest=backtest,
                trade_plan=trade_plan,
                daily_profit_target=context.daily_profit_target,
                intelligence=intelligence,
            ):
                continue

        expected_return = round(PROFIT_TARGET * 100 if signal_type == "BUY" else -PROFIT_TARGET * 100, 2)
        rank_score = _rank_signal(
            signal_type=signal_type,
            confidence=confidence,
            strategy_score=strategy_score,
            backtest=backtest,
            trade_plan=trade_plan,
            daily_profit_target=context.daily_profit_target,
            intelligence=intelligence,
        )

        signal = TradeSignal(
            symbol=sym,
            name=info.get("longName") or info.get("shortName") or sym,
            signal_type=signal_type,
            confidence=confidence,
            strategy_score=rank_score,
            entry_price=round(price, 2),
            target_price=target,
            stop_loss=stop,
            expected_return_pct=expected_return,
            rationale=rationale,
            trade_plan=trade_plan,
            backtest=backtest,
            intelligence=intelligence,
            timeframe=timeframe,
            generated_at=datetime.utcnow(),
        )

        if signal_type == "BUY":
            buy_signals.append(signal)
        else:
            sell_signals.append(signal)

    buy_signals.sort(key=lambda s: (s.strategy_score or 0, s.confidence), reverse=True)
    sell_signals.sort(key=lambda s: (s.strategy_score or 0, s.confidence), reverse=True)

    return {
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "account_size": context.account_size,
        "daily_profit_target": context.daily_profit_target,
        "max_positions": context.max_positions,
        "risk_per_trade_pct": context.risk_per_trade_pct,
        "generated_at": datetime.utcnow(),
    }
