"""
Stock Trading Engine
====================
A lock-based, array-indexed order-matching engine that supports up to
MAX_TICKERS different stock symbols.

Design decisions
----------------
* Orders are stored in plain Python lists (arrays) so that ticker look-up is
  O(1) without using any hash-map or tree structure.
* Each ticker has its own ``threading.Lock`` so that concurrent ``add_order``
  calls on *different* tickers do not block each other.
* Within a single ticker the buy-side is kept sorted descending by price and
  the sell-side ascending by price so that the best bid/ask is always at
  index 0.  Matching is therefore O(k) where k is the number of trades
  executed, and insertion is O(n) per order book.
* A trade callback (``on_trade``) is invoked for every full or partial fill so
  callers can react to executions (logging, position tracking, …).
"""

import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# Maximum number of distinct ticker symbols supported.
MAX_TICKERS = 1024

# Order side constants.
BUY = "BUY"
SELL = "SELL"


@dataclass
class Order:
    """Represents a single limit order placed by a trader."""

    order_id: int
    ticker_index: int          # integer index into the engine's ticker table
    side: str                  # BUY or SELL
    quantity: int              # remaining (unfilled) quantity
    price: float               # limit price

    def is_filled(self) -> bool:
        return self.quantity <= 0


class OrderBook:
    """
    Maintains the resting buy and sell orders for one ticker symbol.

    Buys are stored sorted descending by price (best bid first).
    Sells are stored sorted ascending by price (best ask first).
    """

    def __init__(self) -> None:
        self.buys: List[Order] = []
        self.sells: List[Order] = []

    # ------------------------------------------------------------------
    # Insertion helpers
    # ------------------------------------------------------------------

    def _insert_buy(self, order: Order) -> None:
        """Insert into buys list keeping descending price order (O(n))."""
        idx = len(self.buys)
        for i, o in enumerate(self.buys):
            if order.price > o.price:
                idx = i
                break
        self.buys.insert(idx, order)

    def _insert_sell(self, order: Order) -> None:
        """Insert into sells list keeping ascending price order (O(n))."""
        idx = len(self.sells)
        for i, o in enumerate(self.sells):
            if order.price < o.price:
                idx = i
                break
        self.sells.insert(idx, order)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match(
        self,
        incoming: Order,
        on_trade: Optional[Callable[[Order, Order, int, float], None]] = None,
    ) -> None:
        """
        Try to match *incoming* against resting orders on the opposite side.

        ``on_trade(buy_order, sell_order, qty, price)`` is called for each fill.
        After matching, any remaining quantity of *incoming* is added to the
        resting book.
        """
        if incoming.side == BUY:
            self._match_buy(incoming, on_trade)
            if not incoming.is_filled():
                self._insert_buy(incoming)
        else:
            self._match_sell(incoming, on_trade)
            if not incoming.is_filled():
                self._insert_sell(incoming)

    def _match_buy(
        self,
        buy: Order,
        on_trade: Optional[Callable[[Order, Order, int, float], None]],
    ) -> None:
        """Match a buy order against resting sell orders."""
        while self.sells and not buy.is_filled():
            best_sell = self.sells[0]
            if buy.price < best_sell.price:
                break  # no match possible
            trade_qty = min(buy.quantity, best_sell.quantity)
            trade_price = best_sell.price  # passive (resting) order sets price
            buy.quantity -= trade_qty
            best_sell.quantity -= trade_qty
            if on_trade:
                on_trade(buy, best_sell, trade_qty, trade_price)
            if best_sell.is_filled():
                self.sells.pop(0)

    def _match_sell(
        self,
        sell: Order,
        on_trade: Optional[Callable[[Order, Order, int, float], None]],
    ) -> None:
        """Match a sell order against resting buy orders."""
        while self.buys and not sell.is_filled():
            best_buy = self.buys[0]
            if sell.price > best_buy.price:
                break  # no match possible
            trade_qty = min(sell.quantity, best_buy.quantity)
            trade_price = best_buy.price  # passive (resting) order sets price
            sell.quantity -= trade_qty
            best_buy.quantity -= trade_qty
            if on_trade:
                on_trade(best_buy, sell, trade_qty, trade_price)
            if best_buy.is_filled():
                self.buys.pop(0)


class StockTradingEngine:
    """
    Central engine that routes orders to the correct ``OrderBook``.

    Parameters
    ----------
    tickers:
        An ordered sequence of ticker symbols (e.g. ``["AAPL", "GOOG"]``).
        The position in the list is used as the integer index into internal
        arrays, so look-up is O(1).  At most ``MAX_TICKERS`` symbols are
        supported.
    on_trade:
        Optional callback invoked on every (partial) fill with signature
        ``on_trade(buy_order, sell_order, quantity, price)``.
    """

    def __init__(
        self,
        tickers: List[str],
        on_trade: Optional[Callable[[Order, Order, int, float], None]] = None,
    ) -> None:
        if len(tickers) > MAX_TICKERS:
            raise ValueError(
                f"Engine supports at most {MAX_TICKERS} tickers, "
                f"got {len(tickers)}"
            )
        # --- ticker ↔ index mapping stored in plain arrays ---------------
        # _ticker_names[i] = symbol string for ticker index i
        # _ticker_index[i] = integer index for the i-th symbol
        #   (we avoid dicts: we use a fixed-size list and linear scan for
        #    the symbol→index direction, which is only used at order entry)
        self._ticker_names: List[Optional[str]] = [None] * MAX_TICKERS
        for i, sym in enumerate(tickers):
            self._ticker_names[i] = sym

        self._num_tickers: int = len(tickers)

        # One OrderBook and one Lock per ticker slot.
        self._books: List[Optional[OrderBook]] = [None] * MAX_TICKERS
        self._locks: List[Optional[threading.Lock]] = [None] * MAX_TICKERS
        for i in range(self._num_tickers):
            self._books[i] = OrderBook()
            self._locks[i] = threading.Lock()

        self._on_trade = on_trade
        self._order_counter = 0
        self._counter_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_order(
        self,
        order_type: str,
        ticker: str,
        quantity: int,
        price: float,
    ) -> Order:
        """
        Submit a new limit order and immediately attempt to match it.

        Parameters
        ----------
        order_type:
            ``"BUY"`` or ``"SELL"`` (case-insensitive).
        ticker:
            The stock symbol string (must be one of the symbols passed to
            the constructor).
        quantity:
            Number of shares.  Must be a positive integer.
        price:
            Limit price.  Must be a positive number.

        Returns
        -------
        Order
            The newly created order (possibly partially or fully filled).

        Raises
        ------
        ValueError
            If the ticker is unknown, the side is invalid, or quantity/price
            are non-positive.
        """
        side = order_type.upper()
        if side not in (BUY, SELL):
            raise ValueError(f"order_type must be BUY or SELL, got {order_type!r}")
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")

        ticker_idx = self._find_ticker_index(ticker)
        if ticker_idx is None:
            raise ValueError(f"Unknown ticker: {ticker!r}")

        with self._counter_lock:
            self._order_counter += 1
            order_id = self._order_counter

        order = Order(
            order_id=order_id,
            ticker_index=ticker_idx,
            side=side,
            quantity=quantity,
            price=price,
        )

        with self._locks[ticker_idx]:
            self._books[ticker_idx].match(order, self._on_trade)

        return order

    def best_bid(self, ticker: str) -> Optional[float]:
        """Return the highest resting buy price for *ticker*, or ``None``."""
        idx = self._find_ticker_index(ticker)
        if idx is None:
            raise ValueError(f"Unknown ticker: {ticker!r}")
        with self._locks[idx]:
            buys = self._books[idx].buys
            return buys[0].price if buys else None

    def best_ask(self, ticker: str) -> Optional[float]:
        """Return the lowest resting sell price for *ticker*, or ``None``."""
        idx = self._find_ticker_index(ticker)
        if idx is None:
            raise ValueError(f"Unknown ticker: {ticker!r}")
        with self._locks[idx]:
            sells = self._books[idx].sells
            return sells[0].price if sells else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_ticker_index(self, ticker: str) -> Optional[int]:
        """
        Linear scan of the ticker name array to find the integer index.
        O(n) where n ≤ MAX_TICKERS, but avoids any hash-map structure.
        """
        for i in range(self._num_tickers):
            if self._ticker_names[i] == ticker:
                return i
        return None
