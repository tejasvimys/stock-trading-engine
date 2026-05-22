"""Technical indicator computation and stock screening logic."""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import numpy as np
import pandas as pd
import ta
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator, SMAIndicator
from ta.volatility import BollingerBands

from config import settings
from models import ScreenerFilter, StockSummary, TechnicalIndicators
from services.data_fetcher import (
    fetch_multiple,
    get_cached_history,
    get_change_pct,
    get_latest_price,
    get_tickers,
)

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> TechnicalIndicators:
    """Compute technical indicators for a given OHLCV DataFrame."""
    if df.empty or len(df) < 26:
        return TechnicalIndicators()

    close = df["Close"]
    volume = df["Volume"]

    try:
        rsi = RSIIndicator(close=close, window=14)
        macd_obj = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        bb = BollingerBands(close=close, window=20, window_dev=2)
        sma20 = SMAIndicator(close=close, window=20)
        sma50 = SMAIndicator(close=close, window=50)
        ema9 = EMAIndicator(close=close, window=9)

        return TechnicalIndicators(
            rsi=round(float(rsi.rsi().iloc[-1]), 2),
            macd=round(float(macd_obj.macd().iloc[-1]), 4),
            macd_signal=round(float(macd_obj.macd_signal().iloc[-1]), 4),
            macd_hist=round(float(macd_obj.macd_diff().iloc[-1]), 4),
            bb_upper=round(float(bb.bollinger_hband().iloc[-1]), 2),
            bb_middle=round(float(bb.bollinger_mavg().iloc[-1]), 2),
            bb_lower=round(float(bb.bollinger_lband().iloc[-1]), 2),
            sma_20=round(float(sma20.sma_indicator().iloc[-1]), 2),
            sma_50=round(float(sma50.sma_indicator().iloc[-1]), 2) if len(df) >= 50 else None,
            ema_9=round(float(ema9.ema_indicator().iloc[-1]), 2),
            volume_avg=round(float(volume.rolling(20).mean().iloc[-1]), 0),
        )
    except Exception as exc:
        logger.error("Indicator computation failed: %s", exc)
        return TechnicalIndicators()


def _bb_position(price: Optional[float], ind: TechnicalIndicators) -> Optional[str]:
    if price is None or ind.bb_upper is None or ind.bb_lower is None:
        return None
    if price >= ind.bb_upper:
        return "above_upper"
    if price <= ind.bb_lower:
        return "below_lower"
    return "middle"


def _macd_signal_str(ind: TechnicalIndicators) -> Optional[str]:
    if ind.macd is None or ind.macd_signal is None:
        return None
    return "bullish" if ind.macd > ind.macd_signal else "bearish"


def _passes_filter(
    stock: StockSummary,
    f: ScreenerFilter,
    bb_pos: Optional[str],
    macd_str: Optional[str],
) -> bool:
    ind = stock.indicators
    price = stock.current_price

    if f.rsi_min is not None and (ind.rsi is None or ind.rsi < f.rsi_min):
        return False
    if f.rsi_max is not None and (ind.rsi is None or ind.rsi > f.rsi_max):
        return False
    if f.macd_signal is not None and macd_str != f.macd_signal:
        return False
    if f.bb_position is not None and bb_pos != f.bb_position:
        return False
    if f.min_volume is not None and (ind.volume_avg is None or ind.volume_avg < f.min_volume):
        return False
    return True


async def screen_stocks(screener_filter: ScreenerFilter) -> List[StockSummary]:
    """Fetch data for all tickers and apply the filter."""
    symbols = get_tickers()
    all_data = {symbol: get_cached_history(symbol, period="6mo") for symbol in symbols}
    missing_symbols = [symbol for symbol, df in all_data.items() if df.empty]
    if missing_symbols:
        try:
            fetched_data = await asyncio.wait_for(
                fetch_multiple(missing_symbols, period="6mo"),
                timeout=max(1.0, float(settings.signal_generation_timeout_seconds)),
            )
        except asyncio.TimeoutError:
            logger.warning("Screener timed out while filling %s uncached symbols", len(missing_symbols))
            fetched_data = {symbol: pd.DataFrame() for symbol in missing_symbols}
        all_data.update(fetched_data)

    results: List[StockSummary] = []

    for sym, df in all_data.items():
        if df.empty:
            continue
        price = get_latest_price(df)
        change = get_change_pct(df)
        ind = compute_indicators(df)
        bb_pos = _bb_position(price, ind)
        macd_str = _macd_signal_str(ind)

        stock = StockSummary(
            symbol=sym,
            name=sym,
            current_price=price,
            change_pct=change,
            volume=int(df["Volume"].iloc[-1]) if not df.empty else None,
            market_cap=None,
            indicators=ind,
        )

        if _passes_filter(stock, screener_filter, bb_pos, macd_str):
            results.append(stock)

    # Sorting
    sort_key = screener_filter.sort_by
    reverse = screener_filter.sort_order == "desc"
    key_map = {
        "symbol": lambda s: s.symbol or "",
        "rsi": lambda s: s.indicators.rsi or 0,
        "change_pct": lambda s: s.change_pct or 0,
        "volume": lambda s: s.volume or 0,
        "market_cap": lambda s: s.market_cap or 0,
        "current_price": lambda s: s.current_price or 0,
    }
    key_fn = key_map.get(sort_key, lambda s: s.symbol or "")
    results.sort(key=key_fn, reverse=reverse)

    return results[: screener_filter.limit]
