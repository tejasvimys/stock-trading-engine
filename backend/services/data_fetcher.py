"""Data fetching layer using yfinance."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import yfinance as yf

from config import settings
from models import (
    AnalystSignals,
    EventSignals,
    FundamentalSignals,
    IntelligenceSnapshot,
    OptionsSignals,
    OwnershipSignals,
    SentimentSignals,
)

logger = logging.getLogger(__name__)

# In-memory cache: request key -> (timestamp, DataFrame)
_cache: Dict[str, tuple[datetime, pd.DataFrame]] = {}
_CACHE_TTL_MINUTES = 15
_DAILY_HISTORY_CACHE_TTL_HOURS = 6
_FETCH_CONCURRENCY_LIMIT = 2
POSITIVE_NEWS_TERMS = {
    "beat", "beats", "upgrade", "upgrades", "growth", "surge", "record", "strong",
    "bullish", "buyback", "guidance raised", "outperform", "momentum", "profit",
}
NEGATIVE_NEWS_TERMS = {
    "miss", "misses", "downgrade", "downgrades", "probe", "lawsuit", "cut", "weak",
    "bearish", "selloff", "decline", "guidance lowered", "risk", "loss",
}
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
_ALPHA_VANTAGE_MIN_INTERVAL_SECONDS = 1.1
_alpha_vantage_lock = Lock()
_alpha_vantage_last_request_at = 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    number = _safe_float(value)
    return int(number) if number is not None else None


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cutoff_for_period(period: str) -> Optional[datetime]:
    now = datetime.utcnow()
    mapping = {
        "5d": timedelta(days=5),
        "1mo": timedelta(days=31),
        "3mo": timedelta(days=93),
        "6mo": timedelta(days=186),
        "1y": timedelta(days=366),
        "2y": timedelta(days=732),
    }
    delta = mapping.get(period)
    return now - delta if delta is not None else None


def _http_get_json(url: str, params: dict[str, Any]) -> Any:
    try:
        response = httpx.get(url, params=params, timeout=settings.provider_timeout_seconds)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("Provider request failed for %s: %s", url, exc)
        return None


def _history_cache_ttl(interval: str) -> timedelta:
    if interval.endswith("d"):
        return timedelta(hours=_DAILY_HISTORY_CACHE_TTL_HOURS)
    return timedelta(minutes=_CACHE_TTL_MINUTES)


def _trim_history_to_period(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    trimmed = frame.sort_index()
    cutoff = _cutoff_for_period(period)
    if cutoff is not None:
        trimmed = trimmed[trimmed.index >= cutoff]
    return trimmed


def _daily_source_cache_key(symbol: str) -> str:
    return f"{symbol}_daily_source"


def _history_cache_dir() -> Path:
    cache_dir = Path(settings.history_cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path(__file__).resolve().parents[1] / cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _history_cache_path(cache_key: str) -> Path:
    safe_key = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in cache_key)
    return _history_cache_dir() / f"{safe_key}.pkl"


def _read_persisted_frame(cache_key: str) -> Optional[tuple[datetime, pd.DataFrame]]:
    cache_path = _history_cache_path(cache_key)
    if not cache_path.exists():
        return None
    try:
        frame = pd.read_pickle(cache_path)
        if not isinstance(frame, pd.DataFrame):
            return None
        cached_at = datetime.utcfromtimestamp(cache_path.stat().st_mtime)
        return cached_at, frame
    except Exception as exc:
        logger.warning("Ignoring unreadable persisted cache for %s: %s", cache_key, exc)
        return None


def _write_persisted_frame(cache_key: str, frame: pd.DataFrame, cached_at: datetime) -> None:
    if frame.empty:
        return
    cache_path = _history_cache_path(cache_key)
    try:
        frame.to_pickle(cache_path)
        timestamp = cached_at.timestamp()
        os.utime(cache_path, (timestamp, timestamp))
    except Exception as exc:
        logger.warning("Failed to persist history cache for %s: %s", cache_key, exc)


def _get_cached_frame(cache_key: str, ttl: Optional[timedelta] = None) -> Optional[pd.DataFrame]:
    cached = _cache.get(cache_key)
    if cached is not None:
        cached_at, frame = cached
        if ttl is None or (datetime.utcnow() - cached_at) < ttl:
            return frame

    persisted = _read_persisted_frame(cache_key)
    if persisted is None:
        return None
    cached_at, frame = persisted
    _cache[cache_key] = (cached_at, frame)
    if ttl is not None and (datetime.utcnow() - cached_at) >= ttl:
        return None
    return frame


def _set_cached_frame(cache_key: str, frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    cached_at = datetime.utcnow()
    _cache[cache_key] = (cached_at, frame)
    _write_persisted_frame(cache_key, frame, cached_at)
    return frame


def _cache_history_frame(symbol: str, period: str, interval: str, frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    normalised = frame.copy()
    normalised.index = pd.to_datetime(normalised.index)
    normalised = normalised.sort_index()
    cache_key = f"{symbol}_{period}_{interval}"
    trimmed = _trim_history_to_period(normalised, period)
    _set_cached_frame(cache_key, trimmed)
    if interval == "1d":
        _set_cached_frame(_daily_source_cache_key(symbol), normalised)
    return trimmed


def _get_cached_daily_source(symbol: str, period: str, ttl: Optional[timedelta] = None) -> Optional[pd.DataFrame]:
    source_frame = _get_cached_frame(_daily_source_cache_key(symbol), ttl=ttl)
    if source_frame is None or source_frame.empty:
        return None
    trimmed = _trim_history_to_period(source_frame, period)
    return trimmed if not trimmed.empty else None


def _alpha_vantage_get_json(params: dict[str, Any]) -> Any:
    global _alpha_vantage_last_request_at
    with _alpha_vantage_lock:
        elapsed = time.monotonic() - _alpha_vantage_last_request_at
        if elapsed < _ALPHA_VANTAGE_MIN_INTERVAL_SECONDS:
            time.sleep(_ALPHA_VANTAGE_MIN_INTERVAL_SECONDS - elapsed)
        _alpha_vantage_last_request_at = time.monotonic()
    return _http_get_json(ALPHA_VANTAGE_BASE_URL, params)


def _parse_alpha_vantage_history(payload: dict[str, Any], period: str = "6mo") -> pd.DataFrame:
    if not isinstance(payload, dict):
        return pd.DataFrame()
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict) or not series:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for date_value, item in series.items():
        if not isinstance(item, dict):
            continue
        records.append(
            {
                "Date": date_value,
                "Open": _safe_float(item.get("1. open")),
                "High": _safe_float(item.get("2. high")),
                "Low": _safe_float(item.get("3. low")),
                "Close": _safe_float(item.get("4. close")),
                "Volume": _safe_float(item.get("5. volume")) or 0.0,
            }
        )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_records(records).dropna(subset=["Date", "Close"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    return _trim_history_to_period(df, period)


def fetch_alpha_vantage_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    if not settings.alpha_vantage_api_key:
        return pd.DataFrame()

    payload = _alpha_vantage_get_json(
        {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full",
            "apikey": settings.alpha_vantage_api_key,
        }
    )
    if not isinstance(payload, dict):
        return pd.DataFrame()

    info_message = payload.get("Information") or payload.get("Note") or payload.get("Error Message")
    if info_message:
        logger.warning("Alpha Vantage history unavailable for %s: %s", symbol, info_message)
        return pd.DataFrame()

    return _parse_alpha_vantage_history(payload, period=period)


def _parse_ticker_list(raw: str) -> List[str]:
    return [ticker.strip() for ticker in raw.split(",") if ticker.strip()]


def get_tickers() -> List[str]:
    """Return the configured stock universe, including defensive inverse ETFs."""
    return list(
        dict.fromkeys(
            [
                *_parse_ticker_list(settings.default_tickers),
                *_parse_ticker_list(settings.defensive_tickers),
            ]
        )
    )


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLCV history for *symbol*.
    Returns an empty DataFrame on failure.
    """
    cache_key = f"{symbol}_{period}_{interval}"
    cache_ttl = _history_cache_ttl(interval)
    fresh_cache = _get_cached_frame(cache_key, ttl=cache_ttl)
    if fresh_cache is not None:
        return fresh_cache

    if interval == "1d":
        source_cache = _get_cached_daily_source(symbol, period, ttl=cache_ttl)
        if source_cache is not None:
            return source_cache

    stale_cache = _get_cached_frame(cache_key)
    stale_source_cache = _get_cached_daily_source(symbol, period) if interval == "1d" else None

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning("No data returned for %s from Yahoo; trying provider fallback", symbol)
            fallback = fetch_alpha_vantage_history(symbol, period=period) if interval == "1d" else pd.DataFrame()
            if fallback.empty:
                fallback = fetch_fmp_history(symbol, period=period)
            if not fallback.empty:
                return _cache_history_frame(symbol, period, interval, fallback)
            if stale_source_cache is not None and not stale_source_cache.empty:
                logger.warning("Using stale shared daily history for %s after provider fallback returned no data", symbol)
                return stale_source_cache
            if stale_cache is not None and not stale_cache.empty:
                logger.warning("Using stale cached history for %s after provider fallback returned no data", symbol)
                return stale_cache
            return fallback
        return _cache_history_frame(symbol, period, interval, df)
    except Exception as exc:
        logger.error("Failed to fetch history for %s via Yahoo: %s", symbol, exc)
        fallback = fetch_alpha_vantage_history(symbol, period=period) if interval == "1d" else pd.DataFrame()
        if fallback.empty:
            fallback = fetch_fmp_history(symbol, period=period)
        if not fallback.empty:
            return _cache_history_frame(symbol, period, interval, fallback)
        if stale_source_cache is not None and not stale_source_cache.empty:
            logger.warning("Using stale shared daily history for %s after refresh failure", symbol)
            return stale_source_cache
        if stale_cache is not None and not stale_cache.empty:
            logger.warning("Using stale cached history for %s after refresh failure", symbol)
            return stale_cache
        return fallback


def fetch_info(symbol: str) -> dict:
    """Fetch ticker metadata (name, market cap, sector, etc.)."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return info
    except Exception as exc:
        logger.error("Failed to fetch info for %s: %s", symbol, exc)
        return {}


def fetch_news(symbol: str) -> list[dict]:
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news or []
        return [item for item in news if isinstance(item, dict)]
    except Exception as exc:
        logger.error("Failed to fetch news for %s: %s", symbol, exc)
        return []


def fetch_fmp_profile(symbol: str) -> dict:
    if not settings.fmp_api_key:
        return {}
    payload = _http_get_json(
        f"{FMP_BASE_URL}/profile",
        {"symbol": symbol, "apikey": settings.fmp_api_key},
    )
    if isinstance(payload, list) and payload:
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def fetch_fmp_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    if not settings.fmp_api_key:
        return pd.DataFrame()

    payload = _http_get_json(
        f"{FMP_BASE_URL}/historical-price-eod/full",
        {"symbol": symbol, "apikey": settings.fmp_api_key},
    )
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        date_value = item.get("date")
        if not date_value:
            continue
        records.append(
            {
                "Date": date_value,
                "Open": _safe_float(item.get("open")),
                "High": _safe_float(item.get("high")),
                "Low": _safe_float(item.get("low")),
                "Close": _safe_float(item.get("close") or item.get("price")),
                "Volume": _safe_float(item.get("volume")) or 0.0,
            }
        )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame.from_records(records).dropna(subset=["Date", "Close"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    cutoff = _cutoff_for_period(period)
    if cutoff is not None:
        df = df[df.index >= cutoff]
    return df


def fetch_fmp_quote(symbol: str) -> dict:
    if not settings.fmp_api_key:
        return {}
    payload = _http_get_json(
        f"{FMP_BASE_URL}/quote",
        {"symbol": symbol, "apikey": settings.fmp_api_key},
    )
    if isinstance(payload, list) and payload:
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def fetch_fmp_price_target(symbol: str) -> dict:
    if not settings.fmp_api_key:
        return {}
    payload = _http_get_json(
        f"{FMP_BASE_URL}/price-target-consensus",
        {"symbol": symbol, "apikey": settings.fmp_api_key},
    )
    if isinstance(payload, list) and payload:
        return payload[0]
    return payload if isinstance(payload, dict) else {}


def fetch_fmp_news(symbol: str, limit: int = 10) -> list[dict]:
    if not settings.fmp_api_key:
        return []
    payload = _http_get_json(
        f"{FMP_BASE_URL}/news/stock",
        {"symbols": symbol, "limit": limit, "apikey": settings.fmp_api_key},
    )
    return payload if isinstance(payload, list) else []


def fetch_finnhub_basic_financials(symbol: str) -> dict:
    if not settings.finnhub_api_key:
        return {}
    payload = _http_get_json(
        f"{FINNHUB_BASE_URL}/stock/metric",
        {"symbol": symbol, "metric": "all", "token": settings.finnhub_api_key},
    )
    if isinstance(payload, dict):
        metric = payload.get("metric")
        return metric if isinstance(metric, dict) else {}
    return {}


def fetch_finnhub_recommendation(symbol: str) -> dict:
    if not settings.finnhub_api_key:
        return {}
    payload = _http_get_json(
        f"{FINNHUB_BASE_URL}/stock/recommendation",
        {"symbol": symbol, "token": settings.finnhub_api_key},
    )
    if isinstance(payload, list) and payload:
        return payload[0]
    return {}


def fetch_finnhub_company_news(symbol: str, days: int = 14) -> list[dict]:
    if not settings.finnhub_api_key:
        return []
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    payload = _http_get_json(
        f"{FINNHUB_BASE_URL}/company-news",
        {
            "symbol": symbol,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "token": settings.finnhub_api_key,
        },
    )
    return payload if isinstance(payload, list) else []


def fetch_finnhub_insider_sentiment(symbol: str) -> dict:
    if not settings.finnhub_api_key:
        return {}
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=365)
    payload = _http_get_json(
        f"{FINNHUB_BASE_URL}/stock/insider-sentiment",
        {
            "symbol": symbol,
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
            "token": settings.finnhub_api_key,
        },
    )
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("data")
    if not isinstance(entries, list) or not entries:
        return {}
    mspr_values = [_safe_float(item.get("mspr")) for item in entries]
    change_values = [_safe_float(item.get("change")) for item in entries]
    mspr_values = [value for value in mspr_values if value is not None]
    change_values = [value for value in change_values if value is not None]
    return {
        "avg_mspr": round(_mean(mspr_values), 4) if mspr_values else None,
        "avg_change": round(_mean(change_values), 4) if change_values else None,
    }


def _dedupe_news_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _recommendation_key_from_finnhub(recommendation: dict) -> Optional[str]:
    if not recommendation:
        return None
    strong_buy = _safe_int(recommendation.get("strongBuy")) or 0
    buy = _safe_int(recommendation.get("buy")) or 0
    hold = _safe_int(recommendation.get("hold")) or 0
    sell = _safe_int(recommendation.get("sell")) or 0
    strong_sell = _safe_int(recommendation.get("strongSell")) or 0
    bullish = strong_buy + buy
    bearish = strong_sell + sell
    if bullish > bearish and bullish > hold:
        return "buy"
    if bearish > bullish and bearish > hold:
        return "sell"
    if hold > 0:
        return "hold"
    return None


def _extract_target_price(price_target: dict) -> Optional[float]:
    for key in ("targetConsensus", "targetMedian", "priceTarget", "targetMean", "targetHigh"):
        value = _safe_float(price_target.get(key))
        if value is not None:
            return value
    return None


def merge_provider_info(
    yahoo_info: Optional[dict] = None,
    fmp_profile: Optional[dict] = None,
    fmp_quote: Optional[dict] = None,
    fmp_price_target: Optional[dict] = None,
    finnhub_basic: Optional[dict] = None,
    finnhub_recommendation: Optional[dict] = None,
    finnhub_insider: Optional[dict] = None,
) -> dict:
    yahoo_info = yahoo_info or {}
    fmp_profile = fmp_profile or {}
    fmp_quote = fmp_quote or {}
    fmp_price_target = fmp_price_target or {}
    finnhub_basic = finnhub_basic or {}
    finnhub_recommendation = finnhub_recommendation or {}
    finnhub_insider = finnhub_insider or {}

    recommendation_key = _recommendation_key_from_finnhub(finnhub_recommendation) or yahoo_info.get("recommendationKey")
    analyst_total = sum(
        (_safe_int(finnhub_recommendation.get(key)) or 0)
        for key in ("strongBuy", "buy", "hold", "sell", "strongSell")
    ) or _safe_int(yahoo_info.get("numberOfAnalystOpinions"))

    return {
        **yahoo_info,
        "longName": yahoo_info.get("longName") or fmp_profile.get("companyName") or fmp_profile.get("name"),
        "shortName": yahoo_info.get("shortName") or fmp_profile.get("companyName") or fmp_profile.get("name"),
        "marketCap": yahoo_info.get("marketCap") or fmp_profile.get("mktCap") or fmp_quote.get("marketCap"),
        "sector": yahoo_info.get("sector") or fmp_profile.get("sector"),
        "industry": yahoo_info.get("industry") or fmp_profile.get("industry"),
        "currentPrice": yahoo_info.get("currentPrice") or fmp_quote.get("price"),
        "revenueGrowth": yahoo_info.get("revenueGrowth")
            or finnhub_basic.get("revenueGrowthTTMYoy")
            or finnhub_basic.get("revenueGrowth5Y"),
        "earningsGrowth": yahoo_info.get("earningsGrowth")
            or finnhub_basic.get("epsGrowthTTMYoy")
            or finnhub_basic.get("epsGrowth5Y"),
        "forwardPE": yahoo_info.get("forwardPE")
            or finnhub_basic.get("peTTM")
            or fmp_profile.get("pe"),
        "profitMargins": yahoo_info.get("profitMargins")
            or finnhub_basic.get("netMarginTTM")
            or finnhub_basic.get("netMarginAnnual"),
        "returnOnEquity": yahoo_info.get("returnOnEquity")
            or finnhub_basic.get("roeTTM")
            or finnhub_basic.get("roeAnnual"),
        "recommendationKey": recommendation_key,
        "numberOfAnalystOpinions": analyst_total,
        "targetMedianPrice": yahoo_info.get("targetMedianPrice") or _extract_target_price(fmp_price_target),
        "targetMeanPrice": yahoo_info.get("targetMeanPrice") or _extract_target_price(fmp_price_target),
        "heldPercentInsiders": yahoo_info.get("heldPercentInsiders")
            or (_safe_float(finnhub_insider.get("avg_mspr")) / 100 if _safe_float(finnhub_insider.get("avg_mspr")) is not None else None),
        "heldPercentInstitutions": yahoo_info.get("heldPercentInstitutions"),
    }


def merge_news_sources(
    yahoo_news: Optional[list[dict]] = None,
    fmp_news: Optional[list[dict]] = None,
    finnhub_news: Optional[list[dict]] = None,
) -> list[dict]:
    merged: list[dict] = []
    for item in yahoo_news or []:
        merged.append(item)
    for item in fmp_news or []:
        merged.append(
            {
                "title": item.get("title"),
                "text": item.get("text") or item.get("content"),
                "url": item.get("url"),
                "publishedDate": item.get("publishedDate"),
            }
        )
    for item in finnhub_news or []:
        merged.append(
            {
                "title": item.get("headline"),
                "summary": item.get("summary"),
                "url": item.get("url"),
                "datetime": item.get("datetime"),
            }
        )
    return _dedupe_news_items(merged)


def fetch_calendar(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        if isinstance(calendar, pd.DataFrame):
            flattened = {}
            for column in calendar.columns:
                series = calendar[column]
                flattened[column] = series.iloc[0] if not series.empty else None
            return flattened
        if isinstance(calendar, dict):
            return calendar
        return {}
    except Exception as exc:
        logger.error("Failed to fetch calendar for %s: %s", symbol, exc)
        return {}


def fetch_options_summary(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        expirations = ticker.options or []
        if not expirations:
            return {}
        chain = ticker.option_chain(expirations[0])
        calls = getattr(chain, "calls", pd.DataFrame())
        puts = getattr(chain, "puts", pd.DataFrame())
        call_oi = int(calls["openInterest"].fillna(0).sum()) if not calls.empty and "openInterest" in calls else 0
        put_oi = int(puts["openInterest"].fillna(0).sum()) if not puts.empty and "openInterest" in puts else 0

        iv_values: List[float] = []
        if not calls.empty and "impliedVolatility" in calls:
            iv_values.extend([float(v) for v in calls["impliedVolatility"].dropna().head(25)])
        if not puts.empty and "impliedVolatility" in puts:
            iv_values.extend([float(v) for v in puts["impliedVolatility"].dropna().head(25)])

        return {
            "call_open_interest": call_oi,
            "put_open_interest": put_oi,
            "put_call_ratio": round(put_oi / call_oi, 2) if call_oi > 0 else None,
            "implied_volatility": round(_mean(iv_values), 4) if iv_values else None,
        }
    except Exception as exc:
        logger.error("Failed to fetch options summary for %s: %s", symbol, exc)
        return {}


def build_fundamental_signals(info: dict) -> FundamentalSignals:
    revenue_growth = _safe_float(info.get("revenueGrowth"))
    earnings_growth = _safe_float(info.get("earningsGrowth"))
    forward_pe = _safe_float(info.get("forwardPE"))
    profit_margin = _safe_float(info.get("profitMargins"))
    roe = _safe_float(info.get("returnOnEquity"))
    score_parts: List[float] = []

    if revenue_growth is not None:
        score_parts.append(_clamp((revenue_growth + 0.1) / 0.3, 0.0, 1.0))
    if earnings_growth is not None:
        score_parts.append(_clamp((earnings_growth + 0.1) / 0.35, 0.0, 1.0))
    if forward_pe is not None:
        score_parts.append(_clamp((35.0 - forward_pe) / 25.0, 0.0, 1.0))
    if profit_margin is not None:
        score_parts.append(_clamp((profit_margin + 0.05) / 0.25, 0.0, 1.0))
    if roe is not None:
        score_parts.append(_clamp((roe + 0.05) / 0.3, 0.0, 1.0))

    return FundamentalSignals(
        score=round(_mean(score_parts), 2) if score_parts else 0.5,
        revenue_growth=revenue_growth,
        earnings_growth=earnings_growth,
        forward_pe=forward_pe,
        profit_margin=profit_margin,
        return_on_equity=roe,
    )


def build_analyst_signals(info: dict, current_price: Optional[float] = None) -> AnalystSignals:
    recommendation = str(info.get("recommendationKey") or info.get("recommendationMean") or "").lower() or None
    analyst_count = _safe_int(info.get("numberOfAnalystOpinions"))
    target_median = _safe_float(info.get("targetMedianPrice"))
    target_mean = _safe_float(info.get("targetMeanPrice"))
    target_price = target_median or target_mean
    upside = None
    if current_price and target_price:
        upside = round(((target_price - current_price) / current_price) * 100, 2)

    score = 0.5
    if recommendation in {"strong_buy", "buy"}:
        score += 0.2
    elif recommendation in {"hold", "neutral"}:
        score += 0.0
    elif recommendation in {"underperform", "sell"}:
        score -= 0.2
    if upside is not None:
        score += _clamp(upside / 25.0, -0.2, 0.2)
    if analyst_count is not None:
        score += _clamp((analyst_count - 5) / 40.0, 0.0, 0.1)

    return AnalystSignals(
        score=round(_clamp(score, 0.0, 1.0), 2),
        recommendation=recommendation,
        analyst_count=analyst_count,
        target_upside_pct=upside,
    )


def build_ownership_signals(info: dict) -> OwnershipSignals:
    insider = _safe_float(info.get("heldPercentInsiders"))
    institutional = _safe_float(info.get("heldPercentInstitutions"))
    score_parts: List[float] = []
    if insider is not None:
        score_parts.append(_clamp(insider / 0.2, 0.0, 1.0))
    if institutional is not None:
        score_parts.append(_clamp(institutional / 0.85, 0.0, 1.0))
    return OwnershipSignals(
        score=round(_mean(score_parts), 2) if score_parts else 0.5,
        insider_ownership_pct=round(insider * 100, 2) if insider is not None else None,
        institutional_ownership_pct=round(institutional * 100, 2) if institutional is not None else None,
    )


def build_event_signals(info: dict, calendar: Optional[dict] = None) -> EventSignals:
    calendar = calendar or {}
    candidates = [
        info.get("earningsTimestampStart"),
        info.get("earningsTimestamp"),
        calendar.get("Earnings Date"),
        calendar.get("earningsDate"),
    ]
    earnings_dt: Optional[datetime] = None
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, (list, tuple)) and candidate:
            candidate = candidate[0]
        if isinstance(candidate, pd.Timestamp):
            earnings_dt = candidate.to_pydatetime()
            break
        if isinstance(candidate, datetime):
            earnings_dt = candidate
            break
        if isinstance(candidate, (int, float)):
            earnings_dt = datetime.utcfromtimestamp(candidate)
            break
        if isinstance(candidate, str):
            try:
                earnings_dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                break
            except ValueError:
                continue

    days_to_earnings = None
    score = 0.6
    event_risk = "normal"
    if earnings_dt is not None:
        days_to_earnings = (earnings_dt.date() - datetime.utcnow().date()).days
        if days_to_earnings <= 3:
            score = 0.2
            event_risk = "high"
        elif days_to_earnings <= 7:
            score = 0.35
            event_risk = "elevated"
        elif days_to_earnings <= 14:
            score = 0.5
            event_risk = "moderate"

    return EventSignals(
        score=round(score, 2),
        upcoming_earnings=days_to_earnings is not None and days_to_earnings >= 0,
        days_to_earnings=days_to_earnings,
        event_risk=event_risk,
    )


def build_sentiment_signals(news_items: list[dict]) -> SentimentSignals:
    positive_hits = 0
    negative_hits = 0
    for item in news_items:
        title = str(item.get("title") or item.get("headline") or "").lower()
        positive_hits += sum(1 for term in POSITIVE_NEWS_TERMS if term in title)
        negative_hits += sum(1 for term in NEGATIVE_NEWS_TERMS if term in title)

    total_hits = positive_hits + negative_hits
    raw_score = 0.5
    bias = "neutral"
    if total_hits > 0:
        raw_score = 0.5 + ((positive_hits - negative_hits) / (2 * total_hits))
        if positive_hits > negative_hits:
            bias = "positive"
        elif negative_hits > positive_hits:
            bias = "negative"

    return SentimentSignals(
        score=round(_clamp(raw_score, 0.0, 1.0), 2),
        headline_count=len(news_items),
        sentiment_bias=bias,
        positive_hits=positive_hits,
        negative_hits=negative_hits,
    )


def build_options_signals(options_summary: dict) -> OptionsSignals:
    put_call_ratio = _safe_float(options_summary.get("put_call_ratio"))
    implied_volatility = _safe_float(options_summary.get("implied_volatility"))
    call_oi = _safe_int(options_summary.get("call_open_interest"))
    put_oi = _safe_int(options_summary.get("put_open_interest"))

    score = 0.5
    if put_call_ratio is not None:
        if put_call_ratio < 0.8:
            score += 0.2
        elif put_call_ratio > 1.2:
            score -= 0.2
    if implied_volatility is not None:
        if implied_volatility < 0.35:
            score += 0.1
        elif implied_volatility > 0.65:
            score -= 0.1
    if call_oi is not None and put_oi is not None and (call_oi + put_oi) > 0:
        score += _clamp((call_oi - put_oi) / max(call_oi + put_oi, 1), -0.1, 0.1)

    return OptionsSignals(
        score=round(_clamp(score, 0.0, 1.0), 2),
        put_call_ratio=put_call_ratio,
        implied_volatility=implied_volatility,
        call_open_interest=call_oi,
        put_open_interest=put_oi,
    )


def build_intelligence_snapshot(
    info: Optional[dict] = None,
    news_items: Optional[list[dict]] = None,
    options_summary: Optional[dict] = None,
    calendar: Optional[dict] = None,
    current_price: Optional[float] = None,
) -> IntelligenceSnapshot:
    info = info or {}
    news_items = news_items or []
    options_summary = options_summary or {}
    calendar = calendar or {}

    fundamentals = build_fundamental_signals(info)
    analyst = build_analyst_signals(info, current_price=current_price)
    ownership = build_ownership_signals(info)
    events = build_event_signals(info, calendar=calendar)
    sentiment = build_sentiment_signals(news_items)
    options = build_options_signals(options_summary)

    component_scores = [
        fundamentals.score,
        analyst.score,
        ownership.score,
        events.score,
        sentiment.score,
        options.score,
    ]
    notes: List[str] = []
    if analyst.target_upside_pct is not None and analyst.target_upside_pct > 10:
        notes.append(f"Analyst target implies {analyst.target_upside_pct:.1f}% upside")
    if events.days_to_earnings is not None and events.days_to_earnings <= 7:
        notes.append("Upcoming earnings raise event risk")
    if sentiment.sentiment_bias == "positive":
        notes.append("Recent headline flow skews positive")
    elif sentiment.sentiment_bias == "negative":
        notes.append("Recent headline flow skews negative")
    if options.put_call_ratio is not None and options.put_call_ratio < 0.8:
        notes.append("Options positioning leans call-heavy")
    elif options.put_call_ratio is not None and options.put_call_ratio > 1.2:
        notes.append("Options positioning leans defensive")

    return IntelligenceSnapshot(
        composite_score=round(_mean(component_scores), 2),
        source_count=sum(
            1
            for source in (info, news_items, options_summary, calendar)
            if source
        ),
        fundamentals=fundamentals,
        analyst=analyst,
        ownership=ownership,
        events=events,
        sentiment=sentiment,
        options=options,
        notes=notes,
    )


def fetch_intelligence_snapshot(symbol: str, current_price: Optional[float] = None) -> IntelligenceSnapshot:
    yahoo_info = fetch_info(symbol)
    info = merge_provider_info(
        yahoo_info=yahoo_info,
        fmp_profile=fetch_fmp_profile(symbol),
        fmp_quote=fetch_fmp_quote(symbol),
        fmp_price_target=fetch_fmp_price_target(symbol),
        finnhub_basic=fetch_finnhub_basic_financials(symbol),
        finnhub_recommendation=fetch_finnhub_recommendation(symbol),
        finnhub_insider=fetch_finnhub_insider_sentiment(symbol),
    )
    news = merge_news_sources(
        yahoo_news=fetch_news(symbol),
        fmp_news=fetch_fmp_news(symbol),
        finnhub_news=fetch_finnhub_company_news(symbol),
    )
    calendar = fetch_calendar(symbol)
    options_summary = fetch_options_summary(symbol)
    return build_intelligence_snapshot(
        info=info,
        news_items=news,
        options_summary=options_summary,
        calendar=calendar,
        current_price=current_price,
    )


async def fetch_history_async(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Async wrapper around the blocking fetch_history."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_history, symbol, period)


async def fetch_info_async(symbol: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_info, symbol)


async def fetch_intelligence_snapshot_async(symbol: str, current_price: Optional[float] = None) -> IntelligenceSnapshot:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_intelligence_snapshot, symbol, current_price)


async def fetch_multiple(
    symbols: List[str], period: str = "6mo"
) -> Dict[str, pd.DataFrame]:
    """Fetch histories for multiple symbols concurrently."""
    semaphore = asyncio.Semaphore(_FETCH_CONCURRENCY_LIMIT)

    async def _fetch_symbol(sym: str) -> pd.DataFrame:
        async with semaphore:
            return await fetch_history_async(sym, period)

    tasks = [_fetch_symbol(sym) for sym in symbols]
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
