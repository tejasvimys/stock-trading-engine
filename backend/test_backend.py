"""Tests for backend services (pure unit tests – no network calls)."""
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
import pytest

from services.screener import compute_indicators, _bb_position, _macd_signal_str
from models import ScreenerFilter, TechnicalIndicators


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
