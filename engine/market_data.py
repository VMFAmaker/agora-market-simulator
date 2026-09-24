"""
MARKET DATA. One strict shape for every market, and the time frontier.

A market is a list of bars. Each bar is OHLCV (open, high, low, close, volume) with
a time. Real company, real index, synthetic crash, they all arrive like this, so a
strategy can never tell (and never needs to know) where its prices came from.

WHICH PRICE DO WE USE? (this matters, it is a classic way for a backtest to cheat)
  * raw price           what the screen showed on the day. Changes by 4x on a 4:1
                        split, which a strategy would read as a crash. Not used.
  * split adjusted      raw price scaled so splits disappear. Percentage moves are
                        exactly the real ones. THIS IS WHAT STRATEGIES TRADE ON.
  * total return        split AND dividend adjusted ("adj close"). It rewrites past
                        prices using dividends that were only paid later, so using it
                        for decisions leaks the future. Kept only as a check.
  Dividends are paid into the account as cash on the day the share goes
  ex-dividend, so the account still earns the full total return honestly.

THE TIME FRONTIER
  History is what a strategy is allowed to see. The engine adds one bar at a time,
  and only once that bar has CLOSED. A bar that has not arrived yet is simply not
  in the object, so there is no way to peek at it, even by mistake.

    from market_data import load
    apple = load("AAPL")                  # ten years of daily bars
    apple_1m = load("AAPL", "1m")         # the recent 1 minute demo

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os

import universe as U

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


class Bar:
    """One bar. 'time' is when the bar STARTS, in the exchange's own time."""
    __slots__ = ("time", "open", "high", "low", "close", "volume", "adj_close")

    def __init__(self, time, open, high, low, close, volume=0.0, adj_close=None):
        self.time, self.open, self.high, self.low, self.close = time, open, high, low, close
        self.volume, self.adj_close = volume, adj_close

    def __repr__(self):
        return f"Bar({self.time} O {self.open} H {self.high} L {self.low} C {self.close} V {self.volume})"


class Market:
    """One market's bars and corporate actions. Real or synthetic, same shape."""

    def __init__(self, symbol, name, bars, interval="1d", currency="USD", benchmark=None,
                 is_index=False, dividends=None, splits=None, kind="historical",
                 periods_per_year=252, timezone="UTC", fractional=False):
        self.symbol, self.name, self.bars, self.interval = symbol, name, bars, interval
        self.fractional = fractional      # True where you can hold part of a unit (crypto, an index fund)
        self.currency, self.benchmark, self.is_index = currency, benchmark, is_index
        self.kind, self.periods_per_year, self.timezone = kind, periods_per_year, timezone
        # dividend per share keyed by the ex-dividend date (split adjusted, like the prices)
        self.dividends = {d["d"]: d["amount"] for d in (dividends or [])}
        self.splits = splits or []

    def __len__(self):
        return len(self.bars)

    @property
    def times(self):
        return [b.time for b in self.bars]

    def index_of(self, time):
        """Position of the first bar at or after this time (dates compare as text)."""
        lo, hi = 0, len(self.bars)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.bars[mid].time < time:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def raw_close(self, i):
        """The price actually quoted on the day, undoing later splits (for display)."""
        day, factor = self.bars[i].time[:10], 1.0
        for s in self.splits:
            if s["d"] > day:
                factor *= s["ratio"]
        return self.bars[i].close * factor


class History:
    """
    What a strategy may see. The engine calls add() once a bar has closed, and
    that is the only way bars get in. Everything here looks backwards from 'now'.
    """

    def __init__(self, symbol, interval="1d"):
        self.symbol, self.interval = symbol, interval
        self.bars, self.closes, self.highs, self.lows, self.volumes = [], [], [], [], []

    def add(self, bar):
        if self.bars and bar.time <= self.bars[-1].time:
            raise ValueError("bars must arrive in time order, " + bar.time + " came after " + self.bars[-1].time)
        self.bars.append(bar)
        self.closes.append(bar.close)
        self.highs.append(bar.high)
        self.lows.append(bar.low)
        self.volumes.append(bar.volume)

    def __len__(self):
        return len(self.bars)

    @property
    def now(self):
        """The time of the latest closed bar."""
        return self.bars[-1].time

    @property
    def bar(self):
        return self.bars[-1]

    def close(self, ago=0):
        """The close 'ago' bars back. 0 is the latest. Asking for the future is an error."""
        if ago < 0:
            raise LookAheadError("asked for a close " + str(-ago) + " bars in the future")
        return self.closes[-1 - ago]

    def last(self, n, field="close"):
        """The last n values (fewer if history is short)."""
        seq = {"close": self.closes, "high": self.highs, "low": self.lows, "volume": self.volumes}[field]
        return seq[-n:]


class LookAheadError(Exception):
    """Raised when code asks for information that did not exist yet."""


def _bars(rows):
    return [Bar(r["d"], r["o"], r["h"], r["l"], r["c"], r.get("v", 0), r.get("a")) for r in rows]


def _bars_per_day(rows):
    counts = {}
    for r in rows:
        counts[r["d"][:10]] = counts.get(r["d"][:10], 0) + 1
    per = sorted(counts.values())
    return per[len(per) // 2] if per else 1


def load(symbol, interval="1d"):
    """Load a real market saved by fetch_data.py."""
    safe = U.safe_name(symbol)
    if interval == "1d":
        path = os.path.join(DATA, "daily", safe + ".json")
    else:
        path = os.path.join(DATA, "intraday", safe + "_" + interval + ".json")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    daily = _load_daily_meta(symbol) if interval != "1d" else d
    days = d.get("days_per_year", 252)
    ppy = days if interval == "1d" else days * _bars_per_day(d["bars"])
    return Market(symbol, daily.get("name", symbol), _bars(d["bars"]), interval=interval,
                  currency=daily.get("currency", "USD"), benchmark=daily.get("benchmark"),
                  is_index=daily.get("is_index", False),
                  dividends=daily.get("dividends") if interval == "1d" else None,
                  splits=daily.get("splits"), periods_per_year=ppy,
                  timezone=d.get("timezone", "UTC"),
                  fractional=daily.get("group") == "Crypto" or daily.get("is_index", False))


def _load_daily_meta(symbol):
    with open(os.path.join(DATA, "daily", U.safe_name(symbol) + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    d.pop("bars", None)
    return d


def between(market, start=None, end=None):
    """Index range [a, b) of the bars from start to end (inclusive dates)."""
    a = market.index_of(start) if start else 0
    b = market.index_of(end + "~") if end else len(market.bars)   # "~" sorts after any time on that day
    return a, b
