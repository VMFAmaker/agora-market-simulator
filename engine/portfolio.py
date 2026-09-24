"""
PORTFOLIO ENGINE. The account, the way a broker keeps it.

A trade is not just "+100". The account holds

  cash                  money not in any position
  positions             e.g. AAPL 20 shares, MSFT -10 shares (a short)
  average entry price   what each position cost, per share, on average
  market value          shares x latest price
  unrealised P&L        what open positions have made or lost so far
  realised P&L          what closed trades actually made or lost
  equity                cash + market value of everything, what the account is worth
  exposure              gross (longs + shorts) and net (longs - shorts), per unit of equity
  leverage              gross exposure / equity. 1.0 means no borrowing.

Shorting works like a broker: selling shares you do not own puts the money in
cash, and the position is negative. If equity falls below the maintenance margin
(25% of gross exposure) the account gets a margin call and everything is closed.

Coding done with the help of AI, because coding is not the author's strong area.
"""


class Position:
    def __init__(self):
        self.qty = 0.0            # positive long, negative short
        self.avg_price = 0.0
        self.realised = 0.0       # profit from closed shares, before fees
        self.stop = None          # protective exit prices, if any
        self.target = None

    def __repr__(self):
        return f"Position({self.qty:g} @ {self.avg_price:.2f})"


class Portfolio:
    def __init__(self, cash=100_000.0, max_leverage=1.0, maintenance=0.25):
        self.start_cash = cash
        self.cash = cash
        self.positions = {}
        self.prices = {}          # latest known price per symbol
        self.max_leverage, self.maintenance = max_leverage, maintenance
        self.fees = {"commission": 0.0, "spread": 0.0, "slippage": 0.0, "impact": 0.0}
        self.dividends = 0.0

    def position(self, symbol):
        if symbol not in self.positions:
            self.positions[symbol] = Position()
        return self.positions[symbol]

    def qty(self, symbol):
        p = self.positions.get(symbol)
        return p.qty if p else 0.0

    # ---- valuing the account ----
    def market_value(self, symbol=None):
        if symbol is not None:
            return self.qty(symbol) * self.prices.get(symbol, 0.0)
        return sum(p.qty * self.prices.get(s, 0.0) for s, p in self.positions.items())

    @property
    def equity(self):
        return self.cash + self.market_value()

    @property
    def gross(self):
        return sum(abs(p.qty) * self.prices.get(s, 0.0) for s, p in self.positions.items())

    @property
    def net(self):
        return self.market_value()

    @property
    def leverage(self):
        eq = self.equity
        return self.gross / eq if eq > 0 else float("inf")

    def unrealised(self, symbol=None):
        items = [(symbol, self.positions.get(symbol))] if symbol else self.positions.items()
        return sum(p.qty * (self.prices.get(s, 0.0) - p.avg_price) for s, p in items if p and p.qty)

    @property
    def realised(self):
        return sum(p.realised for p in self.positions.values())

    def buying_power(self):
        """How much more exposure the account may take on."""
        return max(0.0, self.max_leverage * self.equity - self.gross)

    def margin_call(self):
        return self.gross > 0 and self.equity < self.maintenance * self.gross

    # ---- changing the account ----
    def mark(self, symbol, price):
        self.prices[symbol] = price

    def apply_fill(self, symbol, qty, price, costs):
        """qty is signed: positive buys, negative sells. Returns realised profit on this fill."""
        p = self.position(symbol)
        self.cash -= qty * price + costs["commission"]
        self.fees["commission"] += costs["commission"]
        self.fees["spread"] += costs["spread_cost"]
        self.fees["slippage"] += costs["slippage_cost"]
        self.fees["impact"] += costs["impact_cost"]
        realised = 0.0
        if p.qty == 0 or (p.qty > 0) == (qty > 0):                   # opening or adding
            total = p.qty + qty
            p.avg_price = (p.qty * p.avg_price + qty * price) / total
            p.qty = total
        else:                                                         # reducing, closing or flipping
            closing = min(abs(qty), abs(p.qty))
            direction = 1 if p.qty > 0 else -1
            realised = closing * (price - p.avg_price) * direction
            p.realised += realised
            left = p.qty + qty
            if abs(left) < 1e-9:
                p.qty, p.avg_price, p.stop, p.target = 0.0, 0.0, None, None
            elif (left > 0) != (p.qty > 0):                           # flipped to the other side
                p.qty, p.avg_price, p.stop, p.target = left, price, None, None
            else:
                p.qty = left
        self.prices[symbol] = price if symbol not in self.prices else self.prices[symbol]
        return realised

    def pay_dividend(self, symbol, per_share):
        """Longs receive the dividend, shorts have to pay it. Returns the cash moved."""
        amount = self.qty(symbol) * per_share
        self.cash += amount
        self.dividends += amount
        return amount

    def snapshot(self):
        return {"cash": self.cash, "equity": self.equity, "gross": self.gross, "net": self.net,
                "positions": {s: {"qty": p.qty, "avg_price": p.avg_price, "price": self.prices.get(s),
                                  "unrealised": p.qty * (self.prices.get(s, 0) - p.avg_price),
                                  "realised": p.realised}
                              for s, p in self.positions.items() if p.qty}}
