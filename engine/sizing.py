"""
PORTFOLIO ENGINE. Position sizing, how much to buy when a strategy says BUY.

The strategy only says "buy". One of these rules turns that into a number of
shares. After that, the portfolio applies its limits (the most it will hold in
one asset, the leverage it allows, whole shares only).

  FixedPercent(0.10)        put 10% of the account into each new position
  FixedAmount(10_000)       put the same 10,000 into each new position
  VolatilityTarget(0.01)    size so a typical bad move (2 x ATR) costs 1% of the account
  FixedPercent(1.0)         all in, the classic simple backtest

Coding done with the help of AI, because coding is not the author's strong area.
"""
import indicators as ind


class FixedPercent:
    def __init__(self, pct=1.0):
        self.pct = pct

    @property
    def name(self):
        return f"{self.pct:.0%} of the account"

    def quantity(self, price, equity, history):
        return self.pct * equity / price


class FixedAmount:
    def __init__(self, amount=10_000.0):
        self.amount = amount

    @property
    def name(self):
        return f"{self.amount:,.0f} per position"

    def quantity(self, price, equity, history):
        return min(self.amount, equity) / price


class VolatilityTarget:
    """Risk the same slice of the account on every trade, whatever the asset."""

    def __init__(self, risk=0.01, atr_mult=2.0, atr_bars=14):
        self.risk, self.atr_mult, self.atr_bars = risk, atr_mult, atr_bars

    @property
    def name(self):
        return f"risk {self.risk:.1%} of the account per trade"

    def quantity(self, price, equity, history):
        move = ind.atr(history, self.atr_bars)
        if not move:
            return 0.0
        return self.risk * equity / (self.atr_mult * move)


def make(kind="percent", value=1.0):
    """Build a sizing rule from simple settings (used by the tester and the page)."""
    if kind == "amount":
        return FixedAmount(value)
    if kind == "volatility":
        return VolatilityTarget(value)
    return FixedPercent(value)
