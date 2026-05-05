"""Buy/sell signal generation engine targeting ≥10% profit."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Tuple

import numpy as np
import pandas as pd

from config import settings
from models import TradeSignal
from services.data_fetcher import (
    fetch_info,
    fetch_multiple,
    get_latest_price,
    get_tickers,
)
from services.screener import compute_indicators

logger = logging.getLogger(__name__)

PROFIT_TARGET = settings.profit_target  # default 0.10 (10%)
STOP_LOSS_FACTOR = 0.05  # 5% stop loss


def _compute_target_and_stop(price: float, signal_type: str) -> Tuple[float, float]:
    if signal_type == "BUY":
        target = round(price * (1 + PROFIT_TARGET), 2)
        stop = round(price * (1 - STOP_LOSS_FACTOR), 2)
    else:
        target = round(price * (1 - PROFIT_TARGET), 2)
        stop = round(price * (1 + STOP_LOSS_FACTOR), 2)
    return target, stop


def _score_stock(df: pd.DataFrame) -> Tuple[str, float, List[str]]:
    """
    Return (signal_type, confidence, rationale_list).
    signal_type: 'BUY' | 'SELL' | 'HOLD'
    confidence : 0.0 – 1.0
    """
    ind = compute_indicators(df)
    rationale: List[str] = []
    buy_score = 0
    sell_score = 0
    total_checks = 0

    close = df["Close"]
    price = float(close.iloc[-1])

    # --- RSI ---
    if ind.rsi is not None:
        total_checks += 1
        if ind.rsi < 35:
            buy_score += 1
            rationale.append(f"RSI oversold ({ind.rsi:.1f} < 35)")
        elif ind.rsi > 65:
            sell_score += 1
            rationale.append(f"RSI overbought ({ind.rsi:.1f} > 65)")

    # --- MACD crossover ---
    if ind.macd is not None and ind.macd_signal is not None:
        total_checks += 1
        if ind.macd > ind.macd_signal:
            buy_score += 1
            rationale.append("MACD bullish crossover")
        else:
            sell_score += 1
            rationale.append("MACD bearish crossover")

    # --- Bollinger Bands ---
    if ind.bb_lower is not None and ind.bb_upper is not None:
        total_checks += 1
        if price <= ind.bb_lower:
            buy_score += 1
            rationale.append(f"Price near lower BB ({ind.bb_lower:.2f})")
        elif price >= ind.bb_upper:
            sell_score += 1
            rationale.append(f"Price near upper BB ({ind.bb_upper:.2f})")

    # --- Price vs SMA ---
    if ind.sma_50 is not None and ind.sma_20 is not None:
        total_checks += 2
        if price > ind.sma_50:
            buy_score += 1
            rationale.append(f"Price above SMA50 ({ind.sma_50:.2f})")
        else:
            sell_score += 1
            rationale.append(f"Price below SMA50 ({ind.sma_50:.2f})")
        if ind.sma_20 > ind.sma_50:
            buy_score += 1
            rationale.append("Golden cross: SMA20 above SMA50")
        else:
            sell_score += 1
            rationale.append("Death cross: SMA20 below SMA50")

    # --- Volume surge ---
    if ind.volume_avg is not None and not df.empty:
        total_checks += 1
        vol_today = float(df["Volume"].iloc[-1])
        if vol_today > 1.5 * ind.volume_avg:
            if buy_score >= sell_score:
                buy_score += 1
                rationale.append(f"Volume surge ({vol_today / ind.volume_avg:.1f}x avg)")
            else:
                sell_score += 1
                rationale.append(f"Volume surge on down move")

    # --- Recent momentum (5-day return) ---
    if len(df) >= 5:
        total_checks += 1
        ret_5d = (float(close.iloc[-1]) - float(close.iloc[-5])) / float(close.iloc[-5])
        if ret_5d > 0.02:
            buy_score += 1
            rationale.append(f"5-day momentum +{ret_5d*100:.1f}%")
        elif ret_5d < -0.02:
            sell_score += 1
            rationale.append(f"5-day momentum {ret_5d*100:.1f}%")

    if total_checks == 0:
        return "HOLD", 0.0, []

    if buy_score > sell_score:
        confidence = buy_score / total_checks
        return "BUY", round(min(confidence, 1.0), 2), rationale
    elif sell_score > buy_score:
        confidence = sell_score / total_checks
        return "SELL", round(min(confidence, 1.0), 2), rationale
    else:
        return "HOLD", 0.3, ["Mixed signals – no clear direction"]


async def generate_signals(timeframe: str = "weekly") -> dict:
    """Generate buy/sell signals for all tracked stocks."""
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

        signal_type, confidence, rationale = _score_stock(df)
        if signal_type == "HOLD":
            continue

        target, stop = _compute_target_and_stop(price, signal_type)
        expected_return = round(PROFIT_TARGET * 100 if signal_type == "BUY" else -PROFIT_TARGET * 100, 2)

        signal = TradeSignal(
            symbol=sym,
            name=info.get("longName") or info.get("shortName") or sym,
            signal_type=signal_type,
            confidence=confidence,
            entry_price=round(price, 2),
            target_price=target,
            stop_loss=stop,
            expected_return_pct=expected_return,
            rationale=rationale,
            timeframe=timeframe,
            generated_at=datetime.utcnow(),
        )

        if signal_type == "BUY":
            buy_signals.append(signal)
        else:
            sell_signals.append(signal)

    # Sort by confidence descending
    buy_signals.sort(key=lambda s: s.confidence, reverse=True)
    sell_signals.sort(key=lambda s: s.confidence, reverse=True)

    return {
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "generated_at": datetime.utcnow(),
    }
