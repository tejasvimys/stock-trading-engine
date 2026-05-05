"""
Unit tests for the Stock Trading Engine.
"""

import threading
import time
import unittest

from stock_trading_engine import (
    BUY,
    MAX_TICKERS,
    SELL,
    Order,
    OrderBook,
    StockTradingEngine,
)


# ---------------------------------------------------------------------------
# OrderBook tests
# ---------------------------------------------------------------------------


class TestOrderBookNoMatch(unittest.TestCase):
    """Orders that should NOT match because prices don't cross."""

    def _make_order(self, oid, side, qty, price):
        return Order(order_id=oid, ticker_index=0, side=side, quantity=qty, price=price)

    def test_buy_rests_when_no_sells(self):
        book = OrderBook()
        buy = self._make_order(1, BUY, 10, 100.0)
        book.match(buy)
        self.assertEqual(len(book.buys), 1)
        self.assertEqual(len(book.sells), 0)

    def test_sell_rests_when_no_buys(self):
        book = OrderBook()
        sell = self._make_order(1, SELL, 10, 100.0)
        book.match(sell)
        self.assertEqual(len(book.buys), 0)
        self.assertEqual(len(book.sells), 1)

    def test_buy_below_sell_does_not_match(self):
        book = OrderBook()
        sell = self._make_order(1, SELL, 10, 105.0)
        book.match(sell)
        buy = self._make_order(2, BUY, 10, 100.0)
        book.match(buy)
        # both should be resting
        self.assertEqual(len(book.buys), 1)
        self.assertEqual(len(book.sells), 1)


class TestOrderBookFullMatch(unittest.TestCase):
    """Buy price >= sell price → complete fill."""

    def _make_order(self, oid, side, qty, price):
        return Order(order_id=oid, ticker_index=0, side=side, quantity=qty, price=price)

    def test_equal_price_full_fill(self):
        trades = []
        book = OrderBook()
        sell = self._make_order(1, SELL, 10, 100.0)
        book.match(sell)
        buy = self._make_order(2, BUY, 10, 100.0)
        book.match(buy, on_trade=lambda b, s, q, p: trades.append((q, p)))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0], (10, 100.0))
        self.assertEqual(len(book.buys), 0)
        self.assertEqual(len(book.sells), 0)
        self.assertTrue(buy.is_filled())

    def test_buy_above_sell_fills_at_sell_price(self):
        trades = []
        book = OrderBook()
        sell = self._make_order(1, SELL, 5, 98.0)
        book.match(sell)
        buy = self._make_order(2, BUY, 5, 102.0)
        book.match(buy, on_trade=lambda b, s, q, p: trades.append((q, p)))
        # trade executes at the resting sell price
        self.assertEqual(trades[0][1], 98.0)
        self.assertTrue(buy.is_filled())

    def test_sell_below_buy_fills_at_buy_price(self):
        trades = []
        book = OrderBook()
        buy = self._make_order(1, BUY, 5, 105.0)
        book.match(buy)
        sell = self._make_order(2, SELL, 5, 101.0)
        book.match(sell, on_trade=lambda b, s, q, p: trades.append((q, p)))
        # trade executes at the resting buy price
        self.assertEqual(trades[0][1], 105.0)
        self.assertTrue(sell.is_filled())


class TestOrderBookPartialMatch(unittest.TestCase):
    """Partial fills leave residual quantity resting."""

    def _make_order(self, oid, side, qty, price):
        return Order(order_id=oid, ticker_index=0, side=side, quantity=qty, price=price)

    def test_buy_larger_than_sell(self):
        trades = []
        book = OrderBook()
        sell = self._make_order(1, SELL, 3, 100.0)
        book.match(sell)
        buy = self._make_order(2, BUY, 10, 100.0)
        book.match(buy, on_trade=lambda b, s, q, p: trades.append((q, p)))
        self.assertEqual(trades[0][0], 3)          # 3 shares filled
        self.assertEqual(buy.quantity, 7)           # 7 shares remain
        self.assertEqual(len(book.buys), 1)         # residual rests
        self.assertEqual(len(book.sells), 0)

    def test_sell_larger_than_buy(self):
        trades = []
        book = OrderBook()
        buy = self._make_order(1, BUY, 3, 100.0)
        book.match(buy)
        sell = self._make_order(2, SELL, 10, 100.0)
        book.match(sell, on_trade=lambda b, s, q, p: trades.append((q, p)))
        self.assertEqual(trades[0][0], 3)
        self.assertEqual(sell.quantity, 7)
        self.assertEqual(len(book.buys), 0)
        self.assertEqual(len(book.sells), 1)


class TestOrderBookSorting(unittest.TestCase):
    """Best bid/ask is always at index 0."""

    def _make_order(self, oid, side, qty, price):
        return Order(order_id=oid, ticker_index=0, side=side, quantity=qty, price=price)

    def test_buy_side_sorted_descending(self):
        book = OrderBook()
        for price in [99.0, 101.0, 100.0]:
            book.match(self._make_order(price, BUY, 1, price))
        prices = [o.price for o in book.buys]
        self.assertEqual(prices, [101.0, 100.0, 99.0])

    def test_sell_side_sorted_ascending(self):
        book = OrderBook()
        for price in [101.0, 99.0, 100.0]:
            book.match(self._make_order(price, SELL, 1, price))
        prices = [o.price for o in book.sells]
        self.assertEqual(prices, [99.0, 100.0, 101.0])


class TestOrderBookMultipleMatches(unittest.TestCase):
    """A single large order sweeps through several resting orders."""

    def _make_order(self, oid, side, qty, price):
        return Order(order_id=oid, ticker_index=0, side=side, quantity=qty, price=price)

    def test_buy_sweeps_multiple_sells(self):
        trades = []
        book = OrderBook()
        for p in [100.0, 101.0, 102.0]:
            book.match(self._make_order(int(p), SELL, 2, p))
        big_buy = self._make_order(99, BUY, 6, 110.0)
        book.match(big_buy, on_trade=lambda b, s, q, p: trades.append((q, p)))
        self.assertEqual(len(trades), 3)
        self.assertTrue(big_buy.is_filled())
        self.assertEqual(len(book.sells), 0)

    def test_sell_sweeps_multiple_buys(self):
        trades = []
        book = OrderBook()
        for p in [102.0, 101.0, 100.0]:
            book.match(self._make_order(int(p), BUY, 2, p))
        big_sell = self._make_order(99, SELL, 6, 90.0)
        book.match(big_sell, on_trade=lambda b, s, q, p: trades.append((q, p)))
        self.assertEqual(len(trades), 3)
        self.assertTrue(big_sell.is_filled())
        self.assertEqual(len(book.buys), 0)


# ---------------------------------------------------------------------------
# StockTradingEngine tests
# ---------------------------------------------------------------------------


class TestEngineBasic(unittest.TestCase):
    def setUp(self):
        self.trades = []
        self.engine = StockTradingEngine(
            tickers=["AAPL", "GOOG", "MSFT"],
            on_trade=lambda b, s, q, p: self.trades.append(
                {"buy": b.order_id, "sell": s.order_id, "qty": q, "price": p}
            ),
        )

    def test_add_buy_order_rests(self):
        order = self.engine.add_order(BUY, "AAPL", 10, 150.0)
        self.assertFalse(order.is_filled())
        self.assertEqual(self.engine.best_bid("AAPL"), 150.0)

    def test_add_sell_order_rests(self):
        order = self.engine.add_order(SELL, "AAPL", 10, 155.0)
        self.assertFalse(order.is_filled())
        self.assertEqual(self.engine.best_ask("AAPL"), 155.0)

    def test_matching_trade_fires_callback(self):
        self.engine.add_order(SELL, "AAPL", 5, 150.0)
        self.engine.add_order(BUY, "AAPL", 5, 150.0)
        self.assertEqual(len(self.trades), 1)
        self.assertEqual(self.trades[0]["qty"], 5)

    def test_independent_ticker_books(self):
        self.engine.add_order(SELL, "AAPL", 10, 100.0)
        self.engine.add_order(BUY, "GOOG", 10, 200.0)
        # no cross-ticker matching
        self.assertEqual(len(self.trades), 0)
        self.assertEqual(self.engine.best_ask("AAPL"), 100.0)
        self.assertEqual(self.engine.best_bid("GOOG"), 200.0)

    def test_best_bid_none_when_empty(self):
        self.assertIsNone(self.engine.best_bid("MSFT"))

    def test_best_ask_none_when_empty(self):
        self.assertIsNone(self.engine.best_ask("MSFT"))

    def test_unknown_ticker_raises(self):
        with self.assertRaises(ValueError):
            self.engine.add_order(BUY, "UNKNOWN", 1, 100.0)

    def test_invalid_side_raises(self):
        with self.assertRaises(ValueError):
            self.engine.add_order("HOLD", "AAPL", 1, 100.0)

    def test_zero_quantity_raises(self):
        with self.assertRaises(ValueError):
            self.engine.add_order(BUY, "AAPL", 0, 100.0)

    def test_negative_price_raises(self):
        with self.assertRaises(ValueError):
            self.engine.add_order(BUY, "AAPL", 1, -1.0)

    def test_order_ids_are_unique(self):
        ids = {self.engine.add_order(BUY, "AAPL", 1, 10.0 + i).order_id for i in range(20)}
        self.assertEqual(len(ids), 20)

    def test_case_insensitive_side(self):
        """'buy' should be treated the same as 'BUY'."""
        order = self.engine.add_order("buy", "AAPL", 5, 100.0)
        self.assertEqual(order.side, BUY)


class TestEngineConcurrency(unittest.TestCase):
    """Stress-test thread safety: no races, no deadlocks."""

    def test_concurrent_orders_no_race(self):
        trades = []
        lock = threading.Lock()
        engine = StockTradingEngine(
            tickers=["TICK"],
            on_trade=lambda b, s, q, p: (lock.acquire(), trades.append(q), lock.release()),
        )

        errors = []

        def submit_orders(side, count):
            for i in range(count):
                try:
                    engine.add_order(side, "TICK", 1, 100.0)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        threads = [
            threading.Thread(target=submit_orders, args=(BUY, 50)),
            threading.Thread(target=submit_orders, args=(SELL, 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertFalse(errors, f"Thread errors: {errors}")
        # Total filled quantity must never exceed what was submitted.
        total_filled = sum(trades)
        self.assertLessEqual(total_filled, 50)

    def test_different_tickers_do_not_block_each_other(self):
        """Orders on different tickers should run truly concurrently."""
        engine = StockTradingEngine(tickers=["A", "B"])
        barrier = threading.Barrier(2)
        timings = {}

        def submit(ticker):
            barrier.wait()
            start = time.monotonic()
            for _ in range(200):
                engine.add_order(BUY, ticker, 1, 100.0)
            timings[ticker] = time.monotonic() - start

        threads = [threading.Thread(target=submit, args=(t,)) for t in ("A", "B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Both tickers completed (no deadlock).
        self.assertIn("A", timings)
        self.assertIn("B", timings)


class TestEngineMaxTickers(unittest.TestCase):
    def test_max_tickers_accepted(self):
        tickers = [f"T{i}" for i in range(MAX_TICKERS)]
        engine = StockTradingEngine(tickers=tickers)
        # Should be able to place orders on first and last tickers.
        engine.add_order(BUY, "T0", 1, 1.0)
        engine.add_order(BUY, f"T{MAX_TICKERS - 1}", 1, 1.0)

    def test_too_many_tickers_raises(self):
        tickers = [f"T{i}" for i in range(MAX_TICKERS + 1)]
        with self.assertRaises(ValueError):
            StockTradingEngine(tickers=tickers)


if __name__ == "__main__":
    unittest.main()
