"""Tests for backend services (pure unit tests – no network calls)."""
import sys
import os
import asyncio
from datetime import datetime

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import pytest

from models import IntelligenceSnapshot
from services.screener import compute_indicators, _bb_position, _macd_signal_str, screen_stocks
from models import ScreenerFilter, TechnicalIndicators
from models import BacktestSummary
from services.paper_scheduler import _format_cycle_outcome, _initial_next_run_time
from services.data_fetcher import (
    _get_cached_frame,
    _history_cache_ttl,
    _history_cache_path,
    _parse_alpha_vantage_history,
    _set_cached_frame,
    _cache,
    fetch_multiple,
    build_analyst_signals,
    build_event_signals,
    build_fundamental_signals,
    build_intelligence_snapshot,
    get_tickers,
    build_options_signals,
    build_sentiment_signals,
    merge_news_sources,
    merge_provider_info,
)
from services.paper_trading_service import (
    _adaptive_score,
    _default_weights,
    _derive_market_regime,
    _goal_targets,
    _snapshot_key,
    _update_learning_weights,
)
from services.signal_engine import (
    PlanningContext,
    _backtest_signal,
    _build_trade_plan,
    _compute_target_and_stop,
    generate_signals,
    _passes_buy_quality_gate,
    _passes_trade_quality_gate,
    _score_stock,
    _simulate_trade_path,
)


def _make_ohlcv(n: int = 60) -> pd.DataFrame:
    """Create synthetic OHLCV data with a gentle upward trend."""
    rng = np.random.default_rng(42)
    prices = 100 + np.cumsum(rng.normal(0.3, 1.5, n))
    return pd.DataFrame(
        {
            "Open": prices * 0.99,
            "High": prices * 1.01,
            "Low": prices * 0.98,
            "Close": prices,
            "Volume": rng.integers(100_000, 1_000_000, n).astype(float),
        }
    )


def _make_trending_ohlcv(n: int = 140, direction: str = "up") -> pd.DataFrame:
    trend = np.linspace(100, 145, n) if direction == "up" else np.linspace(145, 100, n)
    pullback = np.sin(np.linspace(0, 7, n)) * 1.5
    close = trend + pullback
    if direction == "down":
        close = trend - pullback
    volume = np.linspace(250_000, 700_000, n)
    return pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.015,
            "Low": close * 0.985,
            "Close": close,
            "Volume": volume,
        }
    )


class TestComputeIndicators:
    def test_returns_technicalindicators(self):
        df = _make_ohlcv(60)
        ind = compute_indicators(df)
        assert isinstance(ind, TechnicalIndicators)

    def test_rsi_in_range(self):
        df = _make_ohlcv(60)
        ind = compute_indicators(df)
        assert ind.rsi is not None
        assert 0 <= ind.rsi <= 100

    def test_macd_fields_present(self):
        df = _make_ohlcv(60)
        ind = compute_indicators(df)
        assert ind.macd is not None
        assert ind.macd_signal is not None
        assert ind.macd_hist is not None

    def test_bollinger_bands_ordered(self):
        df = _make_ohlcv(60)
        ind = compute_indicators(df)
        assert ind.bb_lower is not None
        assert ind.bb_upper is not None
        assert ind.bb_lower <= ind.bb_middle <= ind.bb_upper

    def test_sma_present(self):
        df = _make_ohlcv(60)
        ind = compute_indicators(df)
        assert ind.sma_20 is not None
        assert ind.sma_50 is not None

    def test_empty_df_returns_empty_indicators(self):
        ind = compute_indicators(pd.DataFrame())
        assert ind.rsi is None
        assert ind.macd is None

    def test_short_df_returns_empty_indicators(self):
        df = _make_ohlcv(10)
        ind = compute_indicators(df)
        assert ind.rsi is None


class TestBbPosition:
    def _indicators(self, price, lower, upper):
        return TechnicalIndicators(
            rsi=50.0,
            macd=0.0,
            macd_signal=0.0,
            macd_hist=0.0,
            bb_upper=upper,
            bb_middle=(lower + upper) / 2,
            bb_lower=lower,
            sma_20=None,
            sma_50=None,
            ema_9=None,
            volume_avg=None,
        )

    def test_above_upper(self):
        ind = self._indicators(110, 90, 100)
        assert _bb_position(110, ind) == "above_upper"

    def test_below_lower(self):
        ind = self._indicators(85, 90, 100)
        assert _bb_position(85, ind) == "below_lower"

    def test_middle(self):
        ind = self._indicators(95, 90, 100)
        assert _bb_position(95, ind) == "middle"

    def test_none_price(self):
        ind = self._indicators(95, 90, 100)
        assert _bb_position(None, ind) is None


class TestMacdSignal:
    def _ind(self, macd, signal):
        return TechnicalIndicators(
            rsi=None, macd=macd, macd_signal=signal, macd_hist=None,
            bb_upper=None, bb_middle=None, bb_lower=None,
            sma_20=None, sma_50=None, ema_9=None, volume_avg=None,
        )

    def test_bullish(self):
        assert _macd_signal_str(self._ind(0.5, 0.2)) == "bullish"

    def test_bearish(self):
        assert _macd_signal_str(self._ind(0.2, 0.5)) == "bearish"

    def test_none_when_missing(self):
        ind = TechnicalIndicators(
            rsi=None, macd=None, macd_signal=None, macd_hist=None,
            bb_upper=None, bb_middle=None, bb_lower=None,
            sma_20=None, sma_50=None, ema_9=None, volume_avg=None,
        )
        assert _macd_signal_str(ind) is None


class TestScreenerFilter:
    def test_default_values(self):
        f = ScreenerFilter()
        assert f.rsi_min is None
        assert f.rsi_max is None
        assert f.sort_by == "symbol"
        assert f.sort_order == "asc"
        assert f.limit == 50

    def test_custom_values(self):
        f = ScreenerFilter(rsi_min=30, rsi_max=70, macd_signal="bullish", limit=10)
        assert f.rsi_min == 30
        assert f.rsi_max == 70
        assert f.macd_signal == "bullish"
        assert f.limit == 10

    def test_screen_stocks_uses_technical_fallback(self, monkeypatch):
        async def fake_fetch_multiple(symbols, period="6mo"):
            return {}

        monkeypatch.setattr("services.screener.get_tickers", lambda: ["MSFT"])
        monkeypatch.setattr("services.screener.get_cached_history", lambda symbol, period="6mo": _make_ohlcv(60))
        monkeypatch.setattr("services.screener.fetch_multiple", fake_fetch_multiple)

        results = asyncio.run(screen_stocks(ScreenerFilter(limit=10)))

        assert len(results) == 1
        assert results[0].symbol == "MSFT"
        assert results[0].name == "MSFT"
        assert results[0].market_cap is None


class TestSignalEngine:
    def test_score_stock_prefers_buy_for_uptrend(self):
        signal_type, confidence, rationale, strategy_score = _score_stock(_make_trending_ohlcv())
        assert signal_type == "BUY"
        assert confidence >= 0.55
        assert strategy_score >= 0.5
        assert rationale

    def test_compute_target_and_stop_for_buy(self):
        df = _make_trending_ohlcv()
        price = float(df["Close"].iloc[-1])
        target, stop = _compute_target_and_stop(price, "BUY", df)
        assert target > price
        assert stop < price

    def test_simulate_trade_path_hits_target(self):
        future_df = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 103.0],
                "High": [102.0, 111.0, 112.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [101.0, 109.0, 110.0],
                "Volume": [100_000.0, 120_000.0, 110_000.0],
            }
        )
        trade_return, hold_days, exit_reason = _simulate_trade_path(
            future_df=future_df,
            signal_type="BUY",
            entry_price=100.0,
            target_price=110.0,
            stop_loss=95.0,
            max_hold_days=5,
        )
        assert trade_return == 10.0
        assert hold_days == 2
        assert exit_reason == "target"

    def test_simulate_trade_path_hits_target_for_sell(self):
        future_df = pd.DataFrame(
            {
                "Open": [100.0, 99.0, 96.0],
                "High": [101.0, 100.0, 97.0],
                "Low": [98.0, 94.0, 92.0],
                "Close": [99.0, 95.0, 93.0],
                "Volume": [100_000.0, 120_000.0, 110_000.0],
            }
        )
        trade_return, hold_days, exit_reason = _simulate_trade_path(
            future_df=future_df,
            signal_type="SELL",
            entry_price=100.0,
            target_price=95.0,
            stop_loss=105.0,
            max_hold_days=5,
        )
        assert trade_return == 5.0
        assert hold_days == 2
        assert exit_reason == "target"

    def test_build_trade_plan_respects_capital_and_risk(self):
        context = PlanningContext(
            account_size=5000.0,
            daily_profit_target=20.0,
            max_positions=5,
            risk_per_trade_pct=0.01,
            min_hold_days=3,
            max_hold_days=15,
        )
        plan = _build_trade_plan(
            price=100.0,
            target_price=110.0,
            stop_loss=95.0,
            signal_type="BUY",
            backtest=BacktestSummary(trades=8, wins=5, losses=3, win_rate=0.62, avg_return_pct=3.4, expected_value_pct=3.4, avg_hold_days=5.0),
            context=context,
        )
        assert plan is not None
        assert plan.recommended_shares > 0
        assert plan.position_size_usd <= 1000.0
        assert plan.risk_amount_usd <= 50.0
        assert plan.projected_daily_profit_usd > 0

    def test_build_trade_plan_supports_sell(self):
        context = PlanningContext(
            account_size=5000.0,
            daily_profit_target=20.0,
            max_positions=5,
            risk_per_trade_pct=0.01,
            min_hold_days=3,
            max_hold_days=15,
        )
        plan = _build_trade_plan(
            price=100.0,
            target_price=90.0,
            stop_loss=105.0,
            signal_type="SELL",
            backtest=BacktestSummary(trades=8, wins=5, losses=3, win_rate=0.62, avg_return_pct=3.4, expected_value_pct=3.4, avg_hold_days=5.0),
            context=context,
        )
        assert plan is not None
        assert plan.recommended_shares > 0
        assert plan.reward_risk_ratio == 2.0
        assert plan.projected_daily_profit_usd > 0

    def test_backtest_signal_returns_summary(self):
        summary = _backtest_signal(_make_trending_ohlcv(), "BUY", max_hold_days=10)
        assert summary.trades > 0
        assert summary.win_rate is not None
        assert summary.avg_hold_days is not None

    def test_buy_quality_gate_rejects_weak_reward_risk(self):
        context = PlanningContext(
            account_size=5000.0,
            daily_profit_target=20.0,
            max_positions=5,
            risk_per_trade_pct=0.01,
            min_hold_days=3,
            max_hold_days=15,
        )
        plan = _build_trade_plan(
            price=100.0,
            target_price=106.0,
            stop_loss=95.0,
            signal_type="BUY",
            backtest=BacktestSummary(
                trades=8,
                wins=5,
                losses=3,
                win_rate=0.62,
                avg_return_pct=3.4,
                expected_value_pct=3.4,
                avg_hold_days=5.0,
            ),
            context=context,
        )
        assert plan is not None
        assert not _passes_buy_quality_gate(
            confidence=0.68,
            strategy_score=0.63,
            backtest=BacktestSummary(
                trades=8,
                wins=5,
                losses=3,
                win_rate=0.62,
                avg_return_pct=3.4,
                expected_value_pct=3.4,
                avg_hold_days=5.0,
            ),
            trade_plan=plan,
            daily_profit_target=context.daily_profit_target,
        )

    def test_trade_quality_gate_accepts_strong_sell_setup(self):
        context = PlanningContext(
            account_size=5000.0,
            daily_profit_target=20.0,
            max_positions=5,
            risk_per_trade_pct=0.01,
            min_hold_days=3,
            max_hold_days=15,
        )
        plan = _build_trade_plan(
            price=100.0,
            target_price=90.0,
            stop_loss=105.0,
            signal_type="SELL",
            backtest=BacktestSummary(
                trades=8,
                wins=5,
                losses=3,
                win_rate=0.62,
                avg_return_pct=3.4,
                expected_value_pct=3.4,
                avg_hold_days=5.0,
            ),
            context=context,
        )
        assert plan is not None
        assert _passes_trade_quality_gate(
            signal_type="SELL",
            confidence=0.68,
            strategy_score=0.63,
            backtest=BacktestSummary(
                trades=8,
                wins=5,
                losses=3,
                win_rate=0.62,
                avg_return_pct=3.4,
                expected_value_pct=3.4,
                avg_hold_days=5.0,
            ),
            trade_plan=plan,
            daily_profit_target=context.daily_profit_target,
        )

    def test_score_stock_uses_intelligence_snapshot(self):
        intelligence = build_intelligence_snapshot(
            info={
                "revenueGrowth": 0.18,
                "earningsGrowth": 0.22,
                "forwardPE": 24,
                "profitMargins": 0.19,
                "returnOnEquity": 0.21,
                "recommendationKey": "buy",
                "numberOfAnalystOpinions": 28,
                "targetMedianPrice": 165,
                "heldPercentInsiders": 0.08,
                "heldPercentInstitutions": 0.74,
            },
            news_items=[
                {"title": "Company beats estimates with strong growth outlook"},
                {"title": "Analysts upgrade shares after record profit"},
            ],
            options_summary={
                "call_open_interest": 15000,
                "put_open_interest": 8000,
                "put_call_ratio": 0.53,
                "implied_volatility": 0.29,
            },
            calendar={},
            current_price=140.0,
        )
        signal_type, confidence, rationale, strategy_score = _score_stock(
            _make_trending_ohlcv(),
            intelligence=intelligence,
        )
        assert signal_type == "BUY"
        assert confidence >= 0.6
        assert strategy_score >= 0.58
        assert any("Analyst" in item or "Fundamentals" in item for item in rationale)


class TestPaperTradingLearning:
    def test_derive_market_regime_bullish_for_uptrend(self):
        assert _derive_market_regime(_make_trending_ohlcv()) == "bullish"

    def test_default_weights_normalize_to_one(self):
        weights = _default_weights()
        assert round(sum(weights.values()), 4) == 1.0

    def test_adaptive_score_uses_feature_weights(self):
        features = {
            "technical_quality": 0.8,
            "confidence": 0.6,
            "win_rate": 0.7,
            "expected_value": 0.5,
            "profit_fit": 0.4,
        }
        score = _adaptive_score(features, _default_weights())
        assert 0.0 < score <= 1.0
        assert score > 0.6

    def test_learning_weights_shift_toward_profitable_features(self):
        current = _default_weights()
        snapshots = [
            {"technical_quality": 0.9, "confidence": 0.8, "win_rate": 0.7, "expected_value": 0.8, "profit_fit": 0.6},
            {"technical_quality": 0.8, "confidence": 0.7, "win_rate": 0.6, "expected_value": 0.7, "profit_fit": 0.5},
            {"technical_quality": 0.3, "confidence": 0.4, "win_rate": 0.2, "expected_value": 0.2, "profit_fit": 0.3},
            {"technical_quality": 0.2, "confidence": 0.3, "win_rate": 0.1, "expected_value": 0.1, "profit_fit": 0.2},
        ]
        updated = _update_learning_weights(current, snapshots, [5.0, 3.0, -2.0, -4.0], learning_rate=0.2)
        assert round(sum(updated.values()), 4) == 1.0
        assert updated["technical_quality"] > updated["profit_fit"]
        assert updated["expected_value"] > updated["profit_fit"]

    def test_goal_targets_scale_with_account_size(self):
        goals = _goal_targets(10000.0)
        assert goals["daily"] == 40.0
        assert goals["weekly"] == 400.0
        assert goals["monthly"] == 1600.0

    def test_snapshot_key_matches_snapshot_storage_format(self):
        assert _snapshot_key(datetime(2026, 5, 21).date()) == "2026-05-21T00:00:00"

    def test_format_cycle_outcome_summarises_auto_decisions(self):
        outcome = _format_cycle_outcome(datetime(2026, 5, 12), buys_count=2, sells_count=1)
        assert outcome == "2026-05-12: 2 buys, 1 sells"

    def test_initial_next_run_time_defers_when_not_immediate(self):
        before = datetime.utcnow()
        next_run = _initial_next_run_time(run_immediately=False, interval_minutes=15)
        after = datetime.utcnow()
        assert next_run >= before + pd.Timedelta(minutes=15)
        assert next_run <= after + pd.Timedelta(minutes=15)

    def test_daily_history_cache_ttl_is_longer_than_intraday(self):
        assert _history_cache_ttl("1d") > _history_cache_ttl("1m")

    def test_history_cache_persists_across_memory_reset(self, monkeypatch, tmp_path):
        monkeypatch.setattr("services.data_fetcher.settings.history_cache_dir", str(tmp_path))
        cache_key = "TEST_6mo_1d"
        frame = _make_ohlcv(5)

        _cache.clear()
        _set_cached_frame(cache_key, frame)
        assert _history_cache_path(cache_key).exists()

        _cache.clear()
        reloaded = _get_cached_frame(cache_key)

        assert reloaded is not None
        pd.testing.assert_frame_equal(reloaded, frame)

    def test_parse_alpha_vantage_history_returns_dataframe(self):
        payload = {
            "Time Series (Daily)": {
                "2026-05-14": {
                    "1. open": "100.0",
                    "2. high": "101.0",
                    "3. low": "99.0",
                    "4. close": "100.5",
                    "5. volume": "123456",
                },
                "2026-05-13": {
                    "1. open": "98.0",
                    "2. high": "100.0",
                    "3. low": "97.5",
                    "4. close": "99.5",
                    "5. volume": "111111",
                },
            }
        }

        frame = _parse_alpha_vantage_history(payload, period="1mo")

        assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert len(frame) == 2
        assert float(frame["Close"].iloc[-1]) == 100.5

    def test_get_tickers_includes_defensive_symbols(self, monkeypatch):
        monkeypatch.setattr("services.data_fetcher.settings.default_tickers", "MSFT,NVDA,MSFT")
        monkeypatch.setattr("services.data_fetcher.settings.defensive_tickers", "SH,PSQ")
        assert get_tickers() == ["MSFT", "NVDA", "SH", "PSQ"]

    def test_fetch_multiple_times_out_slow_symbols(self, monkeypatch):
        async def slow_fetch_history_async(symbol: str, period: str = "6mo"):
            await asyncio.sleep(0.7)
            return _make_ohlcv(30)

        monkeypatch.setattr("services.data_fetcher.fetch_history_async", slow_fetch_history_async)
        monkeypatch.setattr("services.data_fetcher.settings.history_fetch_timeout_seconds", 0.5)
        monkeypatch.setattr("services.data_fetcher.settings.history_fetch_concurrency", 2)

        result = asyncio.run(fetch_multiple(["MSFT"], period="3mo"))

        assert "MSFT" in result
        assert result["MSFT"].empty

    def test_generate_signals_uses_technical_fallback(self, monkeypatch):
        async def fake_fetch_multiple(symbols, period="3mo"):
            return {"MSFT": _make_trending_ohlcv(direction="up")}

        monkeypatch.setattr("services.signal_engine.fetch_multiple", fake_fetch_multiple)
        monkeypatch.setattr("services.signal_engine.get_tickers", lambda: ["MSFT"])
        monkeypatch.setattr(
            "services.signal_engine._score_stock",
            lambda df, intelligence=None: ("BUY", 0.72, ["Strong trend"], 0.81),
        )
        monkeypatch.setattr(
            "services.signal_engine._backtest_signal",
            lambda df, signal_type, max_hold_days: BacktestSummary(
                trades=5,
                wins=3,
                losses=2,
                win_rate=0.6,
                avg_return_pct=2.4,
                expected_value_pct=2.4,
                avg_hold_days=5,
            ),
        )

        result = asyncio.run(generate_signals(timeframe="weekly"))

        assert len(result["buy_signals"]) == 1
        signal = result["buy_signals"][0]
        assert signal.symbol == "MSFT"
        assert signal.name == "MSFT"
        assert signal.intelligence is None


class TestMultiSourceSignals:
    def test_build_fundamental_signals_scores_strong_profile(self):
        signals = build_fundamental_signals(
            {
                "revenueGrowth": 0.18,
                "earningsGrowth": 0.24,
                "forwardPE": 22,
                "profitMargins": 0.21,
                "returnOnEquity": 0.19,
            }
        )
        assert signals.score > 0.6

    def test_build_analyst_signals_scores_positive_upside(self):
        signals = build_analyst_signals(
            {
                "recommendationKey": "buy",
                "numberOfAnalystOpinions": 24,
                "targetMedianPrice": 132,
            },
            current_price=110.0,
        )
        assert signals.score > 0.6
        assert signals.target_upside_pct is not None

    def test_build_event_signals_penalizes_near_earnings(self):
        near_event = pd.Timestamp.utcnow() + pd.Timedelta(days=2)
        signals = build_event_signals({"earningsTimestampStart": near_event.timestamp()}, {})
        assert signals.score < 0.4
        assert signals.event_risk == "high"

    def test_build_sentiment_signals_detects_positive_bias(self):
        signals = build_sentiment_signals(
            [
                {"title": "Stock beats expectations with record profit"},
                {"title": "Broker upgrade cites strong growth momentum"},
            ]
        )
        assert signals.score > 0.6
        assert signals.sentiment_bias == "positive"

    def test_build_options_signals_detects_constructive_positioning(self):
        signals = build_options_signals(
            {
                "call_open_interest": 18000,
                "put_open_interest": 9000,
                "put_call_ratio": 0.5,
                "implied_volatility": 0.28,
            }
        )
        assert signals.score > 0.6

    def test_build_intelligence_snapshot_combines_sources(self):
        snapshot = build_intelligence_snapshot(
            info={
                "revenueGrowth": 0.12,
                "earningsGrowth": 0.16,
                "forwardPE": 25,
                "profitMargins": 0.17,
                "returnOnEquity": 0.2,
                "recommendationKey": "buy",
                "numberOfAnalystOpinions": 18,
                "targetMedianPrice": 121,
                "heldPercentInsiders": 0.06,
                "heldPercentInstitutions": 0.72,
            },
            news_items=[{"title": "Company beats estimates and analysts upgrade stock"}],
            options_summary={
                "call_open_interest": 10000,
                "put_open_interest": 7000,
                "put_call_ratio": 0.7,
                "implied_volatility": 0.31,
            },
            calendar={},
            current_price=100.0,
        )
        assert isinstance(snapshot, IntelligenceSnapshot)
        assert snapshot.composite_score > 0.55
        assert snapshot.source_count >= 3

    def test_merge_provider_info_prefers_provider_metrics(self):
        merged = merge_provider_info(
            yahoo_info={"longName": "Apple Inc.", "heldPercentInstitutions": 0.7},
            fmp_profile={"companyName": "Apple Inc.", "mktCap": 3100000000000},
            fmp_quote={"price": 187.45},
            fmp_price_target={"targetConsensus": 210.0},
            finnhub_basic={
                "revenueGrowthTTMYoy": 0.14,
                "epsGrowthTTMYoy": 0.18,
                "peTTM": 28.4,
                "netMarginTTM": 0.22,
                "roeTTM": 0.31,
            },
            finnhub_recommendation={"buy": 24, "hold": 6, "sell": 1, "strongBuy": 8, "strongSell": 0},
            finnhub_insider={"avg_mspr": 5.0},
        )
        assert merged["marketCap"] == 3100000000000
        assert merged["revenueGrowth"] == 0.14
        assert merged["recommendationKey"] == "buy"
        assert merged["targetMedianPrice"] == 210.0
        assert merged["numberOfAnalystOpinions"] == 39

    def test_merge_news_sources_dedupes_titles(self):
        merged = merge_news_sources(
            yahoo_news=[{"title": "Apple beats estimates"}],
            fmp_news=[{"title": "Apple beats estimates", "text": "duplicate"}],
            finnhub_news=[{"headline": "Apple launches new service"}],
        )
        titles = [item.get("title") or item.get("headline") for item in merged]
        assert len(merged) == 2
        assert "Apple beats estimates" in titles
        assert "Apple launches new service" in titles
