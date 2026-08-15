"""
AGORA - a simple agent based stock market simulator (all in one file).

The idea: instead of drawing a price from a formula, we create a crowd of little
software "traders", each following one simple rule, and let them buy and sell from
each other on an order book. The price is just whatever they last traded at. Out of
all these simple rules, realistic looking market behaviour appears on its own.

This file has, in order:
  1. Config        - all the numbers you can change, in one place
  2. Order / Book  - the order book and how buy and sell orders get matched
  3. Environment   - the "true value" of the company, which drifts and jumps on news
  4. Account       - each trader's cash and shares
  5. The traders   - noise, market maker, momentum, value, and a few more
  6. Simulation    - runs the clock, lets traders act, and records the price
  7. Analysis      - turns the recorded prices into candles and quality checks

The code is written to be read, not to be clever. It leans on numpy for speed in a
couple of places but otherwise tries to stay plain.

Coding done with the help of AI, because coding is not my strong area.
"""

import heapq
import math
from collections import deque
from dataclasses import dataclass

import numpy as np


# ======================================================================
# 1. CONFIG  -  every setting the simulation uses
# ======================================================================
@dataclass
class Config:
    # --- how long to run. one "minute" of sim time is one candle.
    seed: int = 42
    duration: float = 3000.0        # total minutes (about 50 hours of trading)
    warmup: float = 300.0           # throw the first bit away so the book can settle
    strat_sample: float = 10.0      # log each trader group's profit this often

    # --- the market plumbing
    tick: float = 0.01              # smallest price step
    init_price: float = 100.0       # starting price
    max_inventory: int = 4000       # biggest position a normal trader may hold

    # --- the company's "true value" (a random walk with occasional news jumps)
    v_vol: float = 0.008            # how much it drifts each step
    jump_rate: float = 0.003        # how often news hits
    jump_size: float = 0.020        # how big a news jump is

    # --- fees. takers (who hit the market) pay, makers (who wait) get a rebate.
    taker_fee: float = 0.00020
    maker_rebate: float = 0.00010

    # --- how many of each trader type
    n_noise: int = 70
    n_maker: int = 6
    n_momentum: int = 16
    n_value: int = 24
    n_leveraged: int = 0            # borrowed-money trend traders (crash scenarios)
    n_meanrev: int = 0
    n_breakout: int = 0
    n_news: int = 0
    n_whale: int = 0
    n_panic: int = 0

    # --- noise trader (random buying and selling)
    noise_rate: float = 0.9
    noise_p_market: float = 0.30
    noise_offset_lambda: float = 260.0
    noise_size_mu: float = 0.6
    noise_size_sigma: float = 0.75

    # --- market maker (quotes both sides, leans against its inventory)
    maker_rate: float = 3.5
    maker_size: int = 8
    maker_inv_cap: int = 800
    maker_half_vol_mult: float = 0.6
    maker_half_min: float = 0.0006
    maker_half_max: float = 0.020
    maker_inv_skew: float = 1.5

    # --- momentum trader (buys what is rising)
    mom_rate: float = 0.5
    mom_window: float = 45.0
    mom_theta: float = 0.0012
    mom_base_size: int = 4
    mom_max_size: int = 20

    # --- value investor (buys cheap, sells dear, versus true value)
    value_rate: float = 0.5
    value_noise: float = 0.012
    value_aggr: float = 550.0
    value_max_size: int = 140
    value_market_gap: float = 0.020

    # --- leverage and forced selling
    leverage: float = 4.0
    maint_margin: float = 0.25
    lev_rate: float = 0.7
    lev_init_cash: float = 250_000.0
    lev_max_inventory: int = 30000

    # --- one off shock, used to kick off the crash scenario
    shock_time: float = 0.0
    shock_size: float = 0.0

    # --- circuit breaker (halts trading on a big fast move)
    breaker_pct: float = 0.0
    breaker_window: float = 30.0
    breaker_halt: float = 50.0
    breaker_cooldown: float = 90.0

    # --- the extra trader types (only used in the full market scenario)
    mr_rate: float = 0.45
    mr_window: float = 60.0
    mr_band: float = 0.010
    mr_aggr: float = 700.0
    mr_max_size: int = 30

    bo_rate: float = 0.4
    bo_window: float = 55.0
    bo_eps: float = 0.002
    bo_size: int = 14

    news_rate: float = 1.0
    news_threshold: float = 0.004
    news_aggr: float = 900.0
    news_max_size: int = 40

    whale_rate: float = 0.5
    whale_parent_min: int = 400
    whale_parent_max: int = 1400
    whale_slice: int = 20
    whale_pause: float = 120.0

    panic_rate: float = 0.7
    panic_window: float = 40.0
    panic_trigger: float = 0.06
    panic_size: int = 30

    # --- starting money and shares for a normal trader
    init_cash: float = 5_000_000.0
    init_inventory: int = 400


# ======================================================================
# 2. ORDERS AND THE ORDER BOOK
# ======================================================================
BUY, SELL, LIMIT, MARKET = "buy", "sell", "limit", "market"
_next_id = [0]


class Order:
    """One buy or sell instruction sitting on (or hitting) the book."""
    __slots__ = ("id", "owner", "side", "kind", "price", "left")

    def __init__(self, owner, side, kind, price, size):
        _next_id[0] += 1
        self.id = _next_id[0]
        self.owner = owner        # which trader sent it
        self.side = side          # "buy" or "sell"
        self.kind = kind          # "limit" (wait at a price) or "market" (take now)
        self.price = price        # None for a market order
        self.left = size          # shares still to fill


class OrderBook:
    """
    The order book. Buy orders (bids) rest on one side, sell orders (asks) on the
    other. Best price wins, and among equal prices the one that arrived first fills
    first. A market order eats the other side until it is full.
    """

    def __init__(self, cfg, on_trade):
        self.cfg = cfg
        self.on_trade = on_trade          # called every time a trade happens
        self.bids = {}                    # price -> queue of buy orders
        self.asks = {}                    # price -> queue of sell orders
        self.resting = {}                 # order id -> order, for cancelling
        self.time = 0.0
        self.last_price = cfg.init_price

    def best_bid(self):
        return max(self.bids) if self.bids else None

    def best_ask(self):
        return min(self.asks) if self.asks else None

    def mid(self):
        b, a = self.best_bid(), self.best_ask()
        if b is not None and a is not None:
            return 0.5 * (b + a)
        if b is not None:
            return b
        if a is not None:
            return a
        return self.last_price

    def spread(self):
        b, a = self.best_bid(), self.best_ask()
        return (a - b) if (b is not None and a is not None) else None

    def round_price(self, p):
        return round(round(p / self.cfg.tick) * self.cfg.tick, 2)

    def submit(self, order):
        self._match(order)
        if order.kind == LIMIT and order.left > 0:
            book = self.bids if order.side == BUY else self.asks
            book.setdefault(order.price, deque()).append(order)
            self.resting[order.id] = order

    def cancel(self, order_id):
        o = self.resting.pop(order_id, None)
        if o is None:
            return
        book = self.bids if o.side == BUY else self.asks
        q = book.get(o.price)
        if q is not None:
            try:
                q.remove(o)
            except ValueError:
                pass
            if not q:
                del book[o.price]

    def _match(self, order):
        other = self.asks if order.side == BUY else self.bids
        while order.left > 0 and other:
            best = min(other) if order.side == BUY else max(other)
            if order.kind == LIMIT:                     # a limit order only crosses so far
                if order.side == BUY and best > order.price:
                    break
                if order.side == SELL and best < order.price:
                    break
            queue = other[best]
            while queue and order.left > 0:
                resting = queue[0]
                traded = min(order.left, resting.left)
                order.left -= traded
                resting.left -= traded
                self.last_price = best
                if order.side == BUY:
                    self.on_trade(best, traded, order.owner, resting.owner, BUY)
                else:
                    self.on_trade(best, traded, resting.owner, order.owner, SELL)
                if resting.left == 0:
                    queue.popleft()
                    self.resting.pop(resting.id, None)
            if not queue:
                del other[best]


# ======================================================================
# 3. THE ENVIRONMENT  -  the company's hidden "true value"
# ======================================================================
class Environment:
    """
    A hidden fair value that wanders like a random walk and occasionally jumps on
    news. Value investors chase it, everyone else ignores it.
    """

    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.rng = rng
        self.value = cfg.init_price
        self.t = 0.0

    def advance(self, t):
        dt = t - self.t
        if dt <= 0:
            return
        c = self.cfg
        move = -0.5 * c.v_vol ** 2 * dt + c.v_vol * math.sqrt(dt) * self.rng.normal()
        jumps = self.rng.poisson(c.jump_rate * dt)
        if jumps:
            move += c.jump_size * math.sqrt(jumps) * self.rng.normal()
        self.value *= math.exp(move)
        self.t = t


# ======================================================================
# 4. ACCOUNT  -  one trader's money and shares
# ======================================================================
class Account:
    __slots__ = ("cash", "shares", "fees", "start_cash", "start_shares")

    def __init__(self, cash, shares):
        self.cash = cash
        self.shares = shares
        self.fees = 0.0
        self.start_cash = cash
        self.start_shares = shares

    def fill(self, side, price, size, fee):
        if side == BUY:
            self.cash -= price * size
            self.shares += size
        else:
            self.cash += price * size
            self.shares -= size
        self.cash -= fee
        self.fees += fee

    def equity(self, price):
        return self.cash + self.shares * price

    def profit(self, price):
        return self.equity(price) - (self.start_cash + self.start_shares * price)


# ======================================================================
# 5. THE TRADERS
# Each trader has a `decide` method. It looks at the market and returns a short
# list of actions: ("order", Order) to place one, or ("cancel", id) to pull one.
# `mkt` is the simulation itself, used only to read recent price history.
# ======================================================================
class Trader:
    kind = "trader"

    def __init__(self, tid, account, cfg, rng, rate):
        self.id = tid
        self.account = account
        self.cfg = cfg
        self.rng = rng
        self.rate = rate

    def next_time(self, t):
        # each trader wakes at random moments; on average `rate` times per minute
        return t + float(self.rng.exponential(1.0 / self.rate))

    def decide(self, t, book, env, mkt):
        return []

    # small shared helpers
    def order(self, side, kind, price, size):
        return ("order", Order(self.id, side, kind, price, size))

    def can_buy(self, price, size):
        return (self.account.shares + size <= self.cfg.max_inventory
                and self.account.cash >= price * size)

    def can_sell(self, size):
        return self.account.shares - size >= -self.cfg.max_inventory


class NoiseTrader(Trader):
    """Random retail flow. Flips a coin, sometimes takes the market, sometimes rests
    a limit order a little away from the price. Provides the background noise."""
    kind = "noise"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        buy = self.rng.random() < 0.5
        size = int(self.rng.lognormal(c.noise_size_mu, c.noise_size_sigma)) + 1
        if self.rng.random() < c.noise_p_market:
            if buy and book.best_ask() is not None and self.can_buy(book.mid(), size):
                return [self.order(BUY, MARKET, None, size)]
            if not buy and book.best_bid() is not None and self.can_sell(size):
                return [self.order(SELL, MARKET, None, size)]
            return []
        offset = float(self.rng.exponential(1.0 / c.noise_offset_lambda))
        if buy:
            price = book.round_price((book.best_ask() or book.mid()) * (1 - offset))
            if price > 0 and self.can_buy(price, size):
                return [self.order(BUY, LIMIT, price, size)]
        else:
            price = book.round_price((book.best_bid() or book.mid()) * (1 + offset))
            if self.can_sell(size):
                return [self.order(SELL, LIMIT, price, size)]
        return []


class MarketMaker(Trader):
    """Quotes a buy and a sell around the price to earn the spread, and shifts its
    quotes to lean against whatever inventory it is stuck with."""
    kind = "maker"

    def __init__(self, *a):
        super().__init__(*a)
        self.active = []

    def decide(self, t, book, env, mkt):
        c = self.cfg
        actions = [("cancel", oid) for oid in self.active]     # pull old quotes
        self.active = []
        mid = book.mid()
        rel_vol = mkt.recent_vol()
        half_frac = min(max(c.maker_half_vol_mult * rel_vol, c.maker_half_min), c.maker_half_max)
        half = mid * half_frac
        skew = (self.account.shares / c.maker_inv_cap) * half * c.maker_inv_skew
        centre = mid - skew
        bid = book.round_price(centre - half)
        ask = book.round_price(centre + half)
        if ask - bid < c.tick:
            ask = book.round_price(bid + c.tick)
        if bid > 0 and self.can_buy(bid, c.maker_size):
            o = self.order(BUY, LIMIT, bid, c.maker_size)
            self.active.append(o[1].id)
            actions.append(o)
        if self.can_sell(c.maker_size):
            o = self.order(SELL, LIMIT, ask, c.maker_size)
            self.active.append(o[1].id)
            actions.append(o)
        return actions


class MomentumTrader(Trader):
    """Buys when the price has been rising, sells when falling. Makes trends run."""
    kind = "momentum"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        mid = book.mid()
        past = mkt.price_at(t - c.mom_window)
        if past <= 0:
            return []
        move = math.log(mid / past)
        if abs(move) <= c.mom_theta:
            return []
        size = max(1, int(min(c.mom_max_size, c.mom_base_size * abs(move) / c.mom_theta)))
        if move > 0 and book.best_ask() is not None and self.can_buy(mid, size):
            return [self.order(BUY, MARKET, None, size)]
        if move < 0 and book.best_bid() is not None and self.can_sell(size):
            return [self.order(SELL, MARKET, None, size)]
        return []


class ValueInvestor(Trader):
    """Has a noisy guess of fair value. Leans to buy when the price is below it and
    sell when above, patiently, only crossing the spread when badly mispriced."""
    kind = "value"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        mid = book.mid()
        guess = env.value * math.exp(c.value_noise * float(self.rng.normal()))
        gap = (mid - guess) / guess
        if abs(gap) < 1e-4:
            return []
        size = max(1, int(min(c.value_max_size, c.value_aggr * abs(gap))))
        cross = abs(gap) > c.value_market_gap
        if gap < 0:                                     # too cheap, buy
            if cross and book.best_ask() is not None and self.can_buy(book.best_ask(), size):
                return [self.order(BUY, MARKET, None, size)]
            ask = book.best_ask()
            price = book.round_price(min(ask - c.tick if ask is not None else mid, guess))
            if price > 0 and self.can_buy(price, size):
                return [self.order(BUY, LIMIT, price, size)]
        else:                                           # too dear, sell
            if cross and book.best_bid() is not None and self.can_sell(size):
                return [self.order(SELL, MARKET, None, size)]
            bid = book.best_bid()
            price = book.round_price(max(bid + c.tick if bid is not None else mid, guess))
            if self.can_sell(size):
                return [self.order(SELL, LIMIT, price, size)]
        return []


class LeveragedTrend(MomentumTrader):
    """A momentum trader on borrowed money and thin capital. When the trend turns,
    its equity can fall below the margin line and it gets force sold, which is what
    turns a fall into a cascade."""
    kind = "leveraged"

    def __init__(self, *a):
        super().__init__(*a)
        self.busted = False
        self.mid = self.cfg.init_price

    def decide(self, t, book, env, mkt):
        if self.busted:
            return []
        self.mid = book.mid()
        return super().decide(t, book, env, mkt)

    def buying_power(self):
        eq = self.account.cash + self.account.shares * self.mid
        return self.cfg.leverage * max(eq, 0.0)

    def can_buy(self, price, size):
        return (abs(self.account.shares + size) * self.mid <= self.buying_power()
                and self.account.shares + size <= self.cfg.lev_max_inventory)

    def can_sell(self, size):
        return (abs(self.account.shares - size) * self.mid <= self.buying_power()
                and self.account.shares - size >= -self.cfg.lev_max_inventory)


class MeanReversion(Trader):
    """Fades stretches. Buys when the price is well below its recent average, sells
    when it climbs back."""
    kind = "meanrev"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        mid = book.mid()
        avg = mkt.recent_mean(c.mr_window)
        if avg <= 0:
            return []
        z = (mid - avg) / avg
        if abs(z) < c.mr_band:
            return []
        size = max(1, int(min(c.mr_max_size, c.mr_aggr * abs(z))))
        if z > 0 and book.best_bid() is not None and self.can_sell(size):
            return [self.order(SELL, MARKET, None, size)]
        if z < 0 and book.best_ask() is not None and self.can_buy(mid, size):
            return [self.order(BUY, MARKET, None, size)]
        return []


class BreakoutTrader(Trader):
    """Buys when the price breaks above its recent high, sells when it breaks below
    its recent low."""
    kind = "breakout"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        mid = book.mid()
        hi = mkt.recent_high(c.bo_window, skip=3.0)
        lo = mkt.recent_low(c.bo_window, skip=3.0)
        if mid > hi * (1 + c.bo_eps) and book.best_ask() is not None and self.can_buy(mid, c.bo_size):
            return [self.order(BUY, MARKET, None, c.bo_size)]
        if mid < lo * (1 - c.bo_eps) and book.best_bid() is not None and self.can_sell(c.bo_size):
            return [self.order(SELL, MARKET, None, c.bo_size)]
        return []


class NewsTrader(Trader):
    """Reacts fast to a jump in the true value, before the value investors do."""
    kind = "news"

    def __init__(self, *a):
        super().__init__(*a)
        self.last_value = self.cfg.init_price

    def decide(self, t, book, env, mkt):
        c = self.cfg
        change = (env.value - self.last_value) / self.last_value if self.last_value > 0 else 0.0
        self.last_value = env.value
        if abs(change) < c.news_threshold:
            return []
        mid = book.mid()
        size = max(1, int(min(c.news_max_size, c.news_aggr * abs(change))))
        if change > 0 and book.best_ask() is not None and self.can_buy(mid, size):
            return [self.order(BUY, MARKET, None, size)]
        if change < 0 and book.best_bid() is not None and self.can_sell(size):
            return [self.order(SELL, MARKET, None, size)]
        return []


class Whale(Trader):
    """A big player working one large order into the market in small slices, so as
    not to move the price too much at once. Then it rests and does another."""
    kind = "whale"

    def __init__(self, *a):
        super().__init__(*a)
        self.left = 0
        self.side = BUY
        self.resume = 0.0

    def decide(self, t, book, env, mkt):
        c = self.cfg
        if self.left <= 0:
            if t < self.resume:
                return []
            self.side = BUY if self.rng.random() < 0.5 else SELL
            self.left = int(self.rng.integers(c.whale_parent_min, c.whale_parent_max))
        size = min(c.whale_slice, self.left)
        if self.side == BUY and book.best_ask() is not None and self.can_buy(book.mid(), size):
            self.left -= size
            if self.left <= 0:
                self.resume = t + c.whale_pause
            return [self.order(BUY, MARKET, None, size)]
        if self.side == SELL and book.best_bid() is not None and self.can_sell(size):
            self.left -= size
            if self.left <= 0:
                self.resume = t + c.whale_pause
            return [self.order(SELL, MARKET, None, size)]
        return []


class PanicHerd(Trader):
    """Sells hard when the price has dropped a lot from its recent peak, adding fuel
    to a sell off. A stand in for a nervous crowd."""
    kind = "panic"

    def decide(self, t, book, env, mkt):
        c = self.cfg
        mid = book.mid()
        peak = mkt.recent_high(c.panic_window)
        if peak <= 0:
            return []
        if (mid - peak) / peak < -c.panic_trigger and book.best_bid() is not None and self.can_sell(c.panic_size):
            return [self.order(SELL, MARKET, None, c.panic_size)]
        return []


# a name -> (class, how many, wake rate) table used to build the crowd
TRADER_TYPES = [
    (NoiseTrader, "n_noise", "noise_rate"),
    (MarketMaker, "n_maker", "maker_rate"),
    (MomentumTrader, "n_momentum", "mom_rate"),
    (ValueInvestor, "n_value", "value_rate"),
    (LeveragedTrend, "n_leveraged", "lev_rate"),
    (MeanReversion, "n_meanrev", "mr_rate"),
    (BreakoutTrader, "n_breakout", "bo_rate"),
    (NewsTrader, "n_news", "news_rate"),
    (Whale, "n_whale", "whale_rate"),
    (PanicHerd, "n_panic", "panic_rate"),
]


# ======================================================================
# 6. THE SIMULATION  -  runs the clock and records everything
# ======================================================================
class Simulation:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config()
        self.rng = np.random.default_rng(self.cfg.seed)
        self.book = OrderBook(self.cfg, self._trade_happened)
        self.env = Environment(self.cfg, self.rng)

        # recorded history
        self.mid_t, self.mid_v = [], []          # sampled mid price over time
        self.trade_t, self.trade_p, self.trade_s = [], [], []   # every trade
        self.spreads = []
        self.liquidations = []                   # (time, size) of forced sells
        self.halts = []                          # (start, end) of trading halts
        self.n_trades = 0

        # circuit breaker state
        self.halted = False
        self.halt_until = 0.0
        self.brk_ref = self.cfg.init_price
        self.brk_ref_t = 0.0
        self.brk_cooldown = 0.0
        self.shocked = False

        # build the crowd of traders and seed the book with some starting orders
        self.accounts = {0: Account(0.0, 0)}     # id 0 is the starting liquidity
        self.traders = []
        self.leveraged = []
        self.by_kind = {}
        self._build_traders()
        self._seed_book()

        # per group profit curves over time
        self.strat_t = []
        self.strat = {k: [] for k in self.by_kind}
        self.last_strat = -1e18

    def _build_traders(self):
        c = self.cfg
        tid = 1
        for cls, count_field, rate_field in TRADER_TYPES:
            n = getattr(c, count_field)
            rate = getattr(c, rate_field)
            for _ in range(n):
                if cls is LeveragedTrend:
                    acc = Account(c.lev_init_cash, 0)
                else:
                    acc = Account(c.init_cash, c.init_inventory)
                self.accounts[tid] = acc
                trader = cls(tid, acc, c, self.rng, rate)
                self.traders.append(trader)
                self.by_kind.setdefault(trader.kind, []).append(trader)
                if cls is LeveragedTrend:
                    self.leveraged.append(trader)
                tid += 1

    def _seed_book(self):
        c = self.cfg
        self.book.time = 0.0
        for i in range(1, 16):
            self.book.submit(Order(0, BUY, LIMIT, round(c.init_price - i * 0.03, 2), 8))
            self.book.submit(Order(0, SELL, LIMIT, round(c.init_price + i * 0.03, 2), 8))

    # ---- called by the order book every time two orders trade ----
    def _trade_happened(self, price, size, buyer, seller, taker_side):
        c = self.cfg
        cash = price * size
        taker_fee = c.taker_fee * cash
        maker_rebate = -c.maker_rebate * cash
        buy_fee, sell_fee = ((taker_fee, maker_rebate) if taker_side == BUY
                             else (maker_rebate, taker_fee))
        self.accounts[buyer].fill(BUY, price, size, buy_fee)
        self.accounts[seller].fill(SELL, price, size, sell_fee)
        self.trade_t.append(self.book.time)
        self.trade_p.append(price)
        self.trade_s.append(size)
        self.n_trades += 1

    # ---- history the traders read ----
    def price_at(self, t):
        if not self.mid_t:
            return self.cfg.init_price
        i = np.searchsorted(self.mid_t, t, side="right") - 1
        return self.mid_v[max(0, i)]

    def recent_vol(self, lookback=60):
        if len(self.mid_v) < 5:
            return self.cfg.v_vol
        r = np.diff(np.log(self.mid_v[-lookback:]))
        s = float(np.std(r))
        return s if s > 1e-9 else self.cfg.v_vol

    def _window(self, window, skip=0.0):
        if not self.mid_t:
            return None
        n = max(1, int(window / 0.2))
        seg = self.mid_v[-n:]
        d = int(skip / 0.2)
        if d > 0 and len(seg) > d + 1:
            seg = seg[:-d]
        return seg

    def recent_mean(self, window):
        s = self._window(window)
        return float(np.mean(s)) if s else self.cfg.init_price

    def recent_high(self, window, skip=0.0):
        s = self._window(window, skip)
        return float(np.max(s)) if s else self.cfg.init_price

    def recent_low(self, window, skip=0.0):
        s = self._window(window, skip)
        return float(np.min(s)) if s else self.cfg.init_price

    # ---- the circuit breaker ----
    def _update_breaker(self, t):
        c = self.cfg
        if not c.breaker_pct:
            return
        if self.halted:
            if t >= self.halt_until:
                self.halted = False
                if self.halts:
                    self.halts[-1] = (self.halts[-1][0], t)
                self.brk_ref = self.book.mid()
                self.brk_ref_t = t
                self.brk_cooldown = t + c.breaker_cooldown
            return
        mid = self.book.mid()
        if t - self.brk_ref_t >= c.breaker_window:
            self.brk_ref = mid
            self.brk_ref_t = t
        if t >= self.brk_cooldown and self.brk_ref > 0 and abs(mid / self.brk_ref - 1) > c.breaker_pct:
            self.halted = True
            self.halt_until = t + c.breaker_halt
            self.halts.append((t, t))

    # ---- forced selling of blown-up leveraged traders ----
    def _check_margin(self, t):
        m = self.cfg.maint_margin
        changed = True
        guard = 0
        while changed and guard < 60:
            changed = False
            guard += 1
            mid = self.book.mid()
            for tr in self.leveraged:
                if tr.busted or tr.account.shares == 0:
                    continue
                position = abs(tr.account.shares) * mid
                equity = tr.account.cash + tr.account.shares * mid
                if position > 0 and equity < m * position:
                    side = SELL if tr.account.shares > 0 else BUY
                    self.book.submit(Order(tr.id, side, MARKET, None, abs(tr.account.shares)))
                    tr.busted = True
                    self.liquidations.append((t, abs(tr.account.shares)))
                    changed = True

    # ---- the main loop ----
    def run(self):
        c = self.cfg
        heap = []
        seq = 0
        for tr in self.traders:
            heapq.heappush(heap, (tr.next_time(0.0), seq, tr))
            seq += 1

        last_sample = -1.0
        while heap:
            t, _, tr = heapq.heappop(heap)
            if t > c.duration:
                break
            self.env.advance(t)
            self.book.time = t
            if not self.shocked and c.shock_size and c.shock_time and t >= c.shock_time:
                self.env.value *= math.exp(c.shock_size)
                self.shocked = True
            self._update_breaker(t)

            if not self.halted:
                for what, payload in tr.decide(t, self.book, self.env, self):
                    if what == "cancel":
                        self.book.cancel(payload)
                    else:
                        self.book.submit(payload)
                if self.leveraged:
                    self._check_margin(t)

            # take a snapshot of the mid price every so often
            if t - last_sample >= 0.2:
                self.mid_t.append(t)
                self.mid_v.append(self.book.mid())
                sp = self.book.spread()
                if sp is not None and t >= c.warmup:
                    self.spreads.append(sp)
                last_sample = t
            # log each trader group's running profit
            if t >= c.warmup and t - self.last_strat >= c.strat_sample:
                mid = self.book.mid()
                self.strat_t.append(round(t, 1))
                for k, group in self.by_kind.items():
                    self.strat[k].append(round(sum(a.account.profit(mid) for a in group), 0))
                self.last_strat = t

            heapq.heappush(heap, (tr.next_time(t), seq, tr))
            seq += 1

        if self.halted and self.halts:
            self.halts[-1] = (self.halts[-1][0], c.duration)
        return self._results()

    # ================================================================
    # 7. ANALYSIS  -  turn the recorded prices into candles and checks
    # ================================================================
    def candles(self, bar=1.0):
        c = self.cfg
        edges = np.arange(c.warmup, c.duration + bar * 0.5, bar)
        mt = np.asarray(self.mid_t)
        mv = np.asarray(self.mid_v)
        tt = np.asarray(self.trade_t)
        ts = np.asarray(self.trade_s, dtype=float)
        vol = np.histogram(tt, bins=edges, weights=ts)[0] if len(tt) else np.zeros(len(edges) - 1)
        if self.liquidations:
            lt = np.array([x[0] for x in self.liquidations], dtype=float)
            ls = np.array([x[1] for x in self.liquidations], dtype=float)
            liq = np.histogram(lt, bins=edges, weights=ls)[0]
        else:
            liq = np.zeros(len(edges) - 1)
        idx = np.searchsorted(mt, edges)
        before = mv[mt < c.warmup]
        last_close = float(before[-1]) if len(before) else c.init_price
        out = []
        for k in range(len(edges) - 1):
            a, b = idx[k], idx[k + 1]
            if b > a:
                seg = mv[a:b]
                o, h, l, cl = float(seg[0]), float(seg.max()), float(seg.min()), float(seg[-1])
                last_close = cl
            else:
                o = h = l = cl = last_close
            mid_t = 0.5 * (edges[k] + edges[k + 1])
            halt = 1 if any(s <= mid_t < e for s, e in self.halts) else 0
            out.append({"t": round(mid_t, 1), "o": round(o, 2), "h": round(h, 2),
                        "l": round(l, 2), "c": round(cl, 2),
                        "v": int(vol[k]), "liq": int(liq[k]), "halt": halt})
        return out

    def _returns(self, step=4.0):
        # a coarser return series. fat tails and clustering live at short horizons,
        # so we measure them here rather than on the display candles.
        if len(self.mid_t) < 20:
            return np.array([])
        grid = np.arange(self.cfg.warmup, self.cfg.duration, step)
        idx = np.clip(np.searchsorted(self.mid_t, grid, side="right") - 1, 0, len(self.mid_v) - 1)
        r = np.diff(np.log(np.asarray(self.mid_v)[idx]))
        return r[np.isfinite(r)]

    def stylised_facts(self):
        # do the returns look like a real market?
        r = self._returns()
        if len(r) < 20 or np.std(r) < 1e-12:
            return {"kurtosis": None, "vol_clustering": None, "return_autocorr": None,
                    "pass_fat_tails": False, "pass_vol_clustering": False}
        z = (r - r.mean()) / r.std()
        kurt = float(np.mean(z ** 4))                     # 3 for a normal, higher = fat tails
        ac_ret = _autocorr(r, 1)
        ac_abs = float(np.mean([_autocorr(np.abs(r), k) for k in range(1, 6)]))
        return {"kurtosis": round(kurt, 2), "vol_clustering": round(ac_abs, 3),
                "return_autocorr": round(ac_ret, 3),
                "pass_fat_tails": kurt > 3.5, "pass_vol_clustering": ac_abs > 0.03}

    def _results(self):
        c = self.cfg
        candles = self.candles()
        closes = [x["c"] for x in candles]
        arr = np.array(closes) if closes else np.array([c.init_price])
        peak = np.maximum.accumulate(arr)
        max_dd = float(((arr - peak) / peak).min()) * 100
        mid = self.book.mid()
        agents = []
        for k, group in self.by_kind.items():
            pnl = float(np.sum([a.account.profit(mid) for a in group]))
            agents.append({"kind": k, "pnl": round(pnl, 0), "count": len(group)})
        return {
            "candles": candles,
            "strategy": {"t": self.strat_t, "series": self.strat},
            "facts": self.stylised_facts(),
            "summary": {
                "init": round(closes[0], 2) if closes else c.init_price,
                "final": round(closes[-1], 2) if closes else c.init_price,
                "pct": round((closes[-1] / closes[0] - 1) * 100, 2) if closes else 0.0,
                "high": round(max(x["h"] for x in candles), 2),
                "low": round(min(x["l"] for x in candles), 2),
                "volume": int(sum(x["v"] for x in candles)),
                "n_trades": self.n_trades,
                "avg_spread": round(float(np.mean(self.spreads)), 3) if self.spreads else None,
                "max_drawdown": round(max_dd, 2),
                "n_liquidations": len(self.liquidations),
                "n_halts": len(self.halts),
            },
            "agents": agents,
            "config": {
                "seed": c.seed, "taker_fee": c.taker_fee,
                "n_noise": c.n_noise, "n_maker": c.n_maker, "n_momentum": c.n_momentum,
                "n_value": c.n_value, "n_leveraged": c.n_leveraged, "leverage": c.leverage,
                "n_meanrev": c.n_meanrev, "n_breakout": c.n_breakout, "n_news": c.n_news,
                "n_whale": c.n_whale, "n_panic": c.n_panic, "breaker_pct": c.breaker_pct,
            },
        }


def _autocorr(x, lag):
    x = np.asarray(x, dtype=float)
    if len(x) <= lag:
        return 0.0
    x = x - x.mean()
    denom = np.sum(x * x)
    return float(np.sum(x[:-lag] * x[lag:]) / denom) if denom > 1e-12 else 0.0
