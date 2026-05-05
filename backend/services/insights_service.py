"""AI-style insights generation (rule-based with narrative generation)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple

from models import MarketInsight, StockSummary, TechnicalIndicators
from services.data_fetcher import (
    fetch_info,
    fetch_multiple,
    get_change_pct,
    get_latest_price,
    get_tickers,
)
from services.screener import compute_indicators

logger = logging.getLogger(__name__)

SECTOR_TICKERS: Dict[str, List[str]] = {
    "Technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS"],
    "Banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS"],
    "Energy": ["RELIANCE.NS", "NTPC.NS", "ONGC.NS"],
    "FMCG": ["HINDUNILVR.NS"],
    "Telecom": ["BHARTIARTL.NS"],
    "Finance": ["BAJFINANCE.NS"],
    "Auto": ["MARUTI.NS"],
    "Pharma": ["SUNPHARMA.NS"],
    "Jewellery": ["TITAN.NS"],
    "Infrastructure": ["LT.NS", "ADANIENT.NS"],
}


def _sector_for(symbol: str) -> str:
    for sector, tickers in SECTOR_TICKERS.items():
        if symbol in tickers:
            return sector
    return "Other"


def _narrative_daily(
    gainers: List[StockSummary],
    losers: List[StockSummary],
    sector_perf: Dict[str, float],
) -> Tuple[str, List[str], List[str]]:
    best_sector = max(sector_perf, key=sector_perf.get) if sector_perf else "N/A"
    worst_sector = min(sector_perf, key=sector_perf.get) if sector_perf else "N/A"

    top_gainer = gainers[0] if gainers else None
    top_loser = losers[0] if losers else None

    summary_parts = ["Daily market snapshot based on latest trading session."]
    if top_gainer:
        summary_parts.append(
            f"{top_gainer.name or top_gainer.symbol} led gains with "
            f"{top_gainer.change_pct:+.2f}%."
        )
    if top_loser:
        summary_parts.append(
            f"{top_loser.name or top_loser.symbol} was the biggest decliner at "
            f"{top_loser.change_pct:+.2f}%."
        )
    if best_sector != "N/A":
        summary_parts.append(
            f"{best_sector} was the top performing sector; {worst_sector} lagged behind."
        )

    key_obs: List[str] = []
    if top_gainer and top_gainer.change_pct and top_gainer.change_pct > 3:
        key_obs.append(f"Strong momentum in {top_gainer.name or top_gainer.symbol}.")
    if sector_perf.get("Banking", 0) > 0:
        key_obs.append("Banking sector showed positive breadth – watch for continued strength.")
    if sector_perf.get("Technology", 0) < -1:
        key_obs.append("IT sector under pressure; consider reducing tech exposure short-term.")

    actions: List[str] = []
    if gainers:
        actions.append(
            f"Consider trailing stop-loss on {gainers[0].name or gainers[0].symbol} "
            f"after strong run-up."
        )
    if losers:
        chg = losers[0].change_pct or 0
        if chg < -3:
            actions.append(
                f"Avoid chasing {losers[0].name or losers[0].symbol} today; "
                f"wait for stabilisation."
            )

    return " ".join(summary_parts), key_obs, actions


def _narrative_weekly(
    gainers: List[StockSummary],
    losers: List[StockSummary],
    sector_perf: Dict[str, float],
) -> Tuple[str, List[str], List[str]]:
    best_sector = max(sector_perf, key=sector_perf.get) if sector_perf else "N/A"

    summary = (
        "Weekly market review: The past week showed mixed performance across sectors. "
    )
    if gainers:
        summary += (
            f"Top performer: {gainers[0].name or gainers[0].symbol} "
            f"({gainers[0].change_pct:+.2f}%). "
        )
    if best_sector != "N/A":
        summary += f"Best sector: {best_sector}."

    key_obs = [
        "Review positions that have hit the 10% profit target – consider booking partial gains.",
        "Rebalance portfolio if any single holding exceeds 25% weight.",
    ]
    if sector_perf.get("Banking", 0) > 2:
        key_obs.append("Banking rally – high quality private banks remain good swing holds.")

    actions = [
        "Screen for oversold stocks (RSI < 35) as potential buy setups for next week.",
        "Check upcoming earnings announcements to avoid overnight risk.",
    ]

    return summary, key_obs, actions


async def generate_insights(period: str = "daily") -> MarketInsight:
    symbols = get_tickers()
    all_data = await fetch_multiple(symbols, period="1mo" if period == "daily" else "3mo")

    stock_summaries: List[StockSummary] = []
    sector_changes: Dict[str, List[float]] = {}

    for sym, df in all_data.items():
        if df.empty:
            continue
        info = fetch_info(sym)
        price = get_latest_price(df)
        chg = get_change_pct(df)
        ind = compute_indicators(df)
        s = StockSummary(
            symbol=sym,
            name=info.get("longName") or info.get("shortName") or sym,
            current_price=price,
            change_pct=chg,
            indicators=ind,
        )
        stock_summaries.append(s)

        sector = _sector_for(sym)
        sector_changes.setdefault(sector, [])
        if chg is not None:
            sector_changes[sector].append(chg)

    sector_perf: Dict[str, float] = {
        sec: round(sum(vals) / len(vals), 2)
        for sec, vals in sector_changes.items()
        if vals
    }

    gainers = sorted(
        [s for s in stock_summaries if s.change_pct is not None],
        key=lambda s: s.change_pct,
        reverse=True,
    )[:5]
    losers = sorted(
        [s for s in stock_summaries if s.change_pct is not None],
        key=lambda s: s.change_pct,
    )[:5]

    if period == "weekly":
        summary, key_obs, actions = _narrative_weekly(gainers, losers, sector_perf)
    else:
        summary, key_obs, actions = _narrative_daily(gainers, losers, sector_perf)

    return MarketInsight(
        period=period,
        summary=summary,
        top_gainers=gainers,
        top_losers=losers,
        sector_performance=sector_perf,
        key_observations=key_obs,
        recommended_actions=actions,
        generated_at=datetime.utcnow(),
    )
