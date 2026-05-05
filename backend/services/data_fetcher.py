"""Data fetching layer using yfinance."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from config import settings

logger = logging.getLogger(__name__)

# In-memory cache: symbol -> (timestamp, DataFrame)
_cache: Dict[str, tuple[datetime, pd.DataFrame]] = {}
_CACHE_TTL_MINUTES = 15


def _is_cache_fresh(symbol: str) -> bool:
    if symbol not in _cache:
        return False
    cached_at, _ = _cache[symbol]
    return (datetime.utcnow() - cached_at) < timedelta(minutes=_CACHE_TTL_MINUTES)


def get_tickers() -> List[str]:
    """Return the configured stock universe."""
    return [t.strip() for t in settings.default_tickers.split(",") if t.strip()]


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLCV history for *symbol*.
    Returns an empty DataFrame on failure.
    """
    cache_key = f"{symbol}_{period}_{interval}"
    if _is_cache_fresh(cache_key):
        _, df = _cache[cache_key]
        return df

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning("No data returned for %s", symbol)
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        _cache[cache_key] = (datetime.utcnow(), df)
        return df
    except Exception as exc:
        logger.error("Failed to fetch history for %s: %s", symbol, exc)
        return pd.DataFrame()


def fetch_info(symbol: str) -> dict:
    """Fetch ticker metadata (name, market cap, sector, etc.)."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return info
    except Exception as exc:
        logger.error("Failed to fetch info for %s: %s", symbol, exc)
        return {}


async def fetch_history_async(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Async wrapper around the blocking fetch_history."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_history, symbol, period)


async def fetch_info_async(symbol: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_info, symbol)


async def fetch_multiple(
    symbols: List[str], period: str = "6mo"
) -> Dict[str, pd.DataFrame]:
    """Fetch histories for multiple symbols concurrently."""
    tasks = [fetch_history_async(sym, period) for sym in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    data: Dict[str, pd.DataFrame] = {}
    for sym, result in zip(symbols, results):
        if isinstance(result, Exception):
            logger.error("Error fetching %s: %s", sym, result)
            data[sym] = pd.DataFrame()
        else:
            data[sym] = result
    return data


def get_latest_price(df: pd.DataFrame) -> Optional[float]:
    if df.empty:
        return None
    return float(df["Close"].iloc[-1])


def get_change_pct(df: pd.DataFrame) -> Optional[float]:
    if df.empty or len(df) < 2:
        return None
    prev = float(df["Close"].iloc[-2])
    curr = float(df["Close"].iloc[-1])
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)
