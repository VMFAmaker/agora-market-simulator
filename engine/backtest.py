"""
THE BACKTEST ENGINE. Runs a strategy through time, one bar at a time, in order.

For every bar, in this exact order:

    1. dividends     anyone holding at the last close is paid (shorts pay it)
    2. the open      orders sent at the last close are filled here, by the
                     execution model, at the open price plus costs
    3. the bar       protective stops and take profits are checked against the
                     bar's high and low (a gap through a stop fills at the open)
    4. the close     the account is marked at the closing price
    5. the frontier  only NOW is the bar added to the strategy's history
    6. the decision  the strategy reads its history and may send orders, which
                     wait for the next bar's open (step 2 of the next bar)

So at 10:35 a strategy knows 10:35's close and nothing after it, and whatever it
decides cannot be filled before 10:36. That is the protection against look-ahead
bias. The engine is also tested for it: cutting off the future never changes the
past (see tests/test_engine.py).

    from backtest import Config, run
    from market_data import load
    from strategies import SMACross
    result = run([load("MSFT")], SMACross, {"fast": 20, "slow": 50}, Config())

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math

from execution import Execution
from market_data import History
from portfolio import Portfolio
from sizing import FixedPercent


class Config:
    """Everything about the account and the rules of the test, apart from the strategy."""

    def __init__(self, cash=100_000.0, sizing=None, execution=None, allow_short=False,
                 max_leverage=1.0, max_position=1.0, dividends=True, whole_shares=True,
                 start=None, end=None, warmup=300):
        self.cash = cash
        self.sizing = sizing or FixedPercent(1.0)
        self.execution = execution or Execution()
        self.allow_short, self.max_leverage, self.max_position = allow_short, max_leverage, max_position
        self.dividends, self.whole_shares = dividends, whole_shares
        self.start, self.end, self.warmup = start, end, warmup

    def describe(self):
        return {"cash": self.cash, "sizing": self.sizing.name, "execution": self.execution.describe(),
                "allow_short": self.allow_short, "max_leverage": self.max_leverage,
                "max_position": self.max_position, "dividends": self.dividends,
                "start": self.start, "end": self.end}


class Context:
    """What a strategy can see and do while it makes one decision."""

    def __init__(self, engine, symbol, history):
        self._engine, self.symbol, self.history = engine, symbol, history
        self.trading = False

    @property
    def position(self):
        return self._engine.portfolio.qty(self.symbol)

    @property
    def entry_price(self):
        p = self._engine.portfolio.positions.get(self.symbol)
        return p.avg_price if p and p.qty else None

    @property
    def allow_short(self):
        return self._engine.config.allow_short

    @property
    def equity(self):
        return self._engine.portfolio.equity

    def buy(self, reason="", stop_loss=0.0, take_profit=0.0):
        self._engine.submit_entry(self.symbol, +1, reason, stop_loss, take_profit)

    def short(self, reason="", stop_loss=0.0, take_profit=0.0):
        self._engine.submit_entry(self.symbol, -1, reason, stop_loss, take_profit)

    def close(self, reason=""):
        self._engine.submit_exit(self.symbol, reason, "exit")


class Engine:
    def __init__(self, markets, strategy_cls, params, config):
        self.markets = {m.symbol: m for m in markets}
        self.config = config
        self.portfolio = Portfolio(config.cash, config.max_leverage)
        self.histories = {s: History(s, m.interval) for s, m in self.markets.items()}
        self.strategies = {s: strategy_cls(**(params or {})) for s in self.markets}
        self.contexts = {s: Context(self, s, self.histories[s]) for s in self.markets}
        self.pending = {s: [] for s in self.markets}
        self.orders, self.fills, self.trips, self.dividends = [], [], [], []
        self.open_trips = {}
        self.now = None
        self.trading = False
        self.blown = False
        self._next_id = 1

    # ---------------- orders ----------------
    def _fractional(self, symbol):
        m = self.markets[symbol]
        return (not self.config.whole_shares) or m.fractional

    def _round(self, symbol, qty):
        return qty if self._fractional(symbol) else math.floor(qty + 1e-9)

    def _new_order(self, symbol, side, qty, purpose, reason, stop_loss=0.0, take_profit=0.0):
        order = {"id": self._next_id, "time": self.now, "symbol": symbol, "side": "buy" if side > 0 else "sell",
                 "qty": qty, "purpose": purpose, "reason": reason, "stop_loss": stop_loss,
                 "take_profit": take_profit, "status": "pending", "note": ""}
        self._next_id += 1
        self.orders.append(order)
        return order

    def submit_entry(self, symbol, side, reason, stop_loss, take_profit):
        """The strategy wants a position. The portfolio decides how big."""
        if not self.trading:
            return
        hist, pf = self.histories[symbol], self.portfolio
        price, equity = hist.close(), pf.equity
        qty = self.config.sizing.quantity(price, equity, hist)
        qty = min(qty, self.config.max_position * equity / price)             # most in one asset
        others = pf.gross - abs(pf.qty(symbol)) * price                         # exposure elsewhere
        qty = min(qty, max(0.0, self.config.max_leverage * equity - others) / price)
        qty = self._round(symbol, qty)
        order = self._new_order(symbol, side, qty, "entry", reason, stop_loss, take_profit)
        if qty <= 0:
            order["status"], order["note"] = "rejected", "too small, or no buying power left"
            return
        self._queue(order)

    def submit_exit(self, symbol, reason, purpose):
        qty = self.portfolio.qty(symbol)
        if not self.trading or qty == 0:
            return
        order = self._new_order(symbol, -1 if qty > 0 else +1, abs(qty), purpose, reason)
        self._queue(order)

    def _queue(self, order):
        if self.config.execution.fill_at == "close":
            hist = self.histories[order["symbol"]]
            self._execute(order, hist.close(), hist)                          # optimistic, same close
        else:
            self.pending[order["symbol"]].append(order)                       # waits for the next open

    # ---------------- fills ----------------
    def _execute(self, order, reference, hist):
        symbol, pf, ex = order["symbol"], self.portfolio, self.config.execution
        side = 1 if order["side"] == "buy" else -1
        held = pf.qty(symbol)
        qty = order["qty"]
        if order["purpose"] != "entry":
            if held == 0 or (held > 0) == (side > 0):
                order["status"], order["note"] = "cancelled", "nothing left to close"
                return
            qty = min(qty, abs(held))
        else:
            # check again at the real price, the gap overnight may have changed things
            others = pf.gross - abs(held) * pf.prices.get(symbol, reference)
            room = max(0.0, self.config.max_leverage * pf.equity - others - ex.commission_min)
            est = reference * (1 + ex.spread_bps / 20_000 + ex.slippage_bps / 10_000 + ex.commission_pct)
            qty = self._round(symbol, min(qty, room / est))
        qty, note = ex.cap_quantity(qty, hist)
        qty = self._round(symbol, qty) if order["purpose"] == "entry" else qty
        if qty <= 0:
            order["status"], order["note"] = "rejected", note or "no buying power left at the open"
            return
        f = ex.fill(side, qty, reference, hist)
        before = held
        realised = pf.apply_fill(symbol, side * qty, f["price"], f)
        order["status"] = "partial" if qty < order["qty"] - 1e-9 else "filled"
        order["note"] = note
        fill = {"order": order["id"], "time": self.now, "symbol": symbol, "side": order["side"],
                "qty": qty, "purpose": order["purpose"], "reason": order["reason"],
                "expected": f["expected"], "price": f["price"], "commission": f["commission"],
                "spread_cost": f["spread_cost"], "slippage_cost": f["slippage_cost"],
                "impact_cost": f["impact_cost"], "participation": f["participation"],
                "value": qty * f["price"], "realised": realised, "note": note}
        self.fills.append(fill)
        after = pf.qty(symbol)
        if order["purpose"] == "entry" and after != 0 and (order["stop_loss"] or order["take_profit"]):
            pos = pf.position(symbol)
            d = 1 if after > 0 else -1
            pos.stop = f["price"] * (1 - d * order["stop_loss"]) if order["stop_loss"] else None
            pos.target = f["price"] * (1 + d * order["take_profit"]) if order["take_profit"] else None
        self._track_trip(symbol, before, after, fill)

    def _track_trip(self, symbol, before, after, fill):
        """A round trip runs from flat, into a position, and back to flat."""
        trip = self.open_trips.get(symbol)
        if trip:
            trip["pnl"] += fill["realised"] - fill["commission"]
            trip["costs"] += fill["commission"] + fill["spread_cost"] + fill["slippage_cost"] + fill["impact_cost"]
        if trip and (after == 0 or (after > 0) != (before > 0)):
            trip.update({"exit_time": self.now, "exit_price": fill["price"], "exit_reason": fill["reason"],
                         "exit_kind": fill["purpose"], "bars": trip["bars"]})
            trip["return"] = trip["pnl"] / trip["cost_basis"] if trip["cost_basis"] else 0.0
            self.trips.append(trip)
            del self.open_trips[symbol]
            trip = None
        if after != 0 and trip is None:
            self.open_trips[symbol] = {
                "symbol": symbol, "side": "long" if after > 0 else "short", "entry_time": self.now,
                "entry_price": fill["price"], "entry_reason": fill["reason"], "qty": abs(after),
                "cost_basis": abs(after) * fill["price"], "bars": 0,
                "pnl": -fill["commission"] if before == 0 else 0.0,
                "costs": fill["commission"] + fill["spread_cost"] + fill["slippage_cost"] + fill["impact_cost"]}

    def _check_exits(self, symbol, bar, hist):
        """Stops and take profits, watched during the bar."""
        pos = self.portfolio.positions.get(symbol)
        if not pos or pos.qty == 0 or (pos.stop is None and pos.target is None):
            return
        long = pos.qty > 0
        hit, level, why = False, None, ""
        if pos.stop is not None:
            if (long and bar.open <= pos.stop) or (not long and bar.open >= pos.stop):
                hit, level, why = True, bar.open, "stop loss, gapped through at the open"
            elif (long and bar.low <= pos.stop) or (not long and bar.high >= pos.stop):
                hit, level, why = True, pos.stop, "stop loss hit"
            kind = "stop"
        if not hit and pos.target is not None:
            if (long and bar.open >= pos.target) or (not long and bar.open <= pos.target):
                hit, level, why = True, bar.open, "take profit, gapped past at the open"
            elif (long and bar.high >= pos.target) or (not long and bar.low <= pos.target):
                hit, level, why = True, pos.target, "take profit hit"
            kind = "target"
        if hit:
            order = self._new_order(symbol, -1 if long else +1, abs(pos.qty), kind, why)
            self._execute(order, level, hist)

    # ---------------- the loop ----------------
    def run(self):
        cfg = self.config
        # where each market starts (keeping some bars before the start for warm up) and ends
        cursors, ends = {}, {}
        for s, m in self.markets.items():
            a = m.index_of(cfg.start) if cfg.start else 0
            cursors[s] = max(0, a - cfg.warmup) if cfg.start else 0
            ends[s] = m.index_of(cfg.end + "~") if cfg.end else len(m.bars)
        times = sorted({m.bars[i].time for s, m in self.markets.items() for i in range(cursors[s], ends[s])})
        record = {"times": [], "equity": [], "cash": [], "gross": [], "net": [],
                  "qty": {s: [] for s in self.markets}, "price": {s: [] for s in self.markets}}
        started = False
        for s in self.markets:
            self.strategies[s].initialize(self.contexts[s])

        for t in times:
            self.now = t
            self.trading = (cfg.start is None or t >= cfg.start) and not self.blown
            updated = []
            for s, m in self.markets.items():
                i = cursors[s]
                if i >= ends[s] or m.bars[i].time != t:
                    continue
                bar, hist = m.bars[i], self.histories[s]
                cursors[s] = i + 1
                if self.trading and cfg.dividends and bar.time in m.dividends and self.portfolio.qty(s):
                    amount = self.portfolio.pay_dividend(s, m.dividends[bar.time])
                    self.dividends.append({"time": t, "symbol": s, "per_share": m.dividends[bar.time],
                                           "amount": amount})
                    if s in self.open_trips:
                        self.open_trips[s]["pnl"] += amount
                for order in self.pending[s]:
                    self._execute(order, bar.open, hist)                      # 2. the open
                self.pending[s] = []
                self._check_exits(s, bar, hist)                               # 3. during the bar
                self.portfolio.mark(s, bar.close)                             # 4. the close
                hist.add(bar)                                                 # 5. the frontier moves
                if s in self.open_trips:
                    self.open_trips[s]["bars"] += 1
                updated.append(s)

            if self.trading and self.portfolio.equity <= 0:
                self._blow_up()
            elif self.trading and self.portfolio.margin_call():
                for s in self.markets:
                    self.submit_exit(s, "margin call, equity below maintenance", "margin")

            for s in updated:                                                 # 6. the decisions
                ctx = self.contexts[s]
                ctx.trading = self.trading
                self.strategies[s].on_market_data(ctx)

            if self.trading or started:
                started = True
                record["times"].append(t)
                record["equity"].append(max(0.0, self.portfolio.equity))
                record["cash"].append(self.portfolio.cash)
                record["gross"].append(self.portfolio.gross)
                record["net"].append(self.portfolio.net)
                for s in self.markets:
                    record["qty"][s].append(self.portfolio.qty(s))
                    record["price"][s].append(self.portfolio.prices.get(s))
        return self._results(record)

    def _blow_up(self):
        """Equity is gone. Close everything at the last price and stop trading."""
        self.blown = True
        for s, p in self.portfolio.positions.items():
            if p.qty:
                price = self.portfolio.prices[s]
                self.portfolio.cash += p.qty * price
                p.qty = 0.0
        self.trading = False

    def _results(self, record):
        first = next(iter(self.markets.values()))
        pf = self.portfolio
        open_trips = []                                                   # open positions, valued at the last price
        for s, trip in self.open_trips.items():
            p = pf.positions.get(s)
            t = dict(trip)
            t["unrealised"] = p.qty * (pf.prices[s] - p.avg_price) if p and p.qty else 0.0
            t["pnl_marked"] = t["pnl"] + t["unrealised"]
            t["return"] = t["pnl_marked"] / t["cost_basis"] if t["cost_basis"] else 0.0
            t["open"] = True
            open_trips.append(t)
        return {
            "symbols": list(self.markets), "strategy": self.strategies[first.symbol].label(),
            "params": dict(self.strategies[first.symbol].params), "config": self.config.describe(),
            "periods_per_year": first.periods_per_year, "interval": first.interval,
            "start_cash": self.config.cash, **record,
            "orders": self.orders, "fills": self.fills, "trips": self.trips,
            "open_trips": open_trips, "dividends": self.dividends,
            "fees": dict(pf.fees), "dividends_total": pf.dividends, "blown": self.blown,
            "final": pf.snapshot(), "realised": pf.realised, "unrealised": pf.unrealised(),
        }


def run(markets, strategy_cls, params=None, config=None):
    """Run one backtest. markets is a list (one market, or several for a portfolio)."""
    return Engine(markets, strategy_cls, params, config or Config()).run()
