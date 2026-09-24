"""
STRATEGY ENGINE. The trading rules.

Every strategy follows the same four steps, and only these:

    initialize()        set up, once, before the first bar
    on_market_data()    called by the engine each time a bar CLOSES
    generate_signal()   read the market, say BUY, SELL or HOLD, and why
    manage_position()   turn that view into a wish ("I want to be long")

A strategy never decides HOW MUCH to buy, at what PRICE it gets filled, or what it
costs. That is on purpose. The chain is

    market data -> indicator -> SIGNAL -> portfolio decision (size) -> ORDER
                -> execution model (price, fees, slippage) -> position

so "RSI below 30" produces a signal, not a trade. The portfolio sizes it, and the
execution model decides what really happens at the next bar's open.

Every strategy also takes two optional risk settings, stop_loss and take_profit
(fractions, 0.05 is 5%, 0 means off). They travel with the order and are watched
by the engine bar by bar.

Coding done with the help of AI, because coding is not the author's strong area.
"""
import indicators as ind


class Signal:
    """What a strategy thinks, plus a short reason for the trade log."""
    __slots__ = ("action", "reason")

    def __init__(self, action, reason=""):
        self.action, self.reason = action, reason

    def __repr__(self):
        return f"Signal({self.action}, {self.reason!r})"


def BUY(reason=""):
    return Signal("BUY", reason)


def SELL(reason=""):
    return Signal("SELL", reason)


HOLD = Signal("HOLD")


class Strategy:
    """The base every rule builds on."""
    key = "base"
    name = "Strategy"
    about = ""
    # (setting, label, default, lowest, highest, step)
    settings = []
    # values tried when the tester optimises this strategy
    grid = {}

    def __init__(self, **params):
        self.params = {s[0]: s[2] for s in self.settings}
        self.params.setdefault("stop_loss", 0.0)
        self.params.setdefault("take_profit", 0.0)
        self.params.update(params)

    @property
    def p(self):
        return self.params

    def label(self):
        shown = [f"{k} {v}" for k, v in self.params.items()
                 if k not in ("stop_loss", "take_profit") or v]
        return self.name + (" (" + ", ".join(shown) + ")" if shown else "")

    # ---- the four steps ----
    def initialize(self, ctx):
        pass

    def on_market_data(self, ctx):
        signal = self.generate_signal(ctx.history)
        self.manage_position(ctx, signal)

    def generate_signal(self, history):
        return HOLD

    def manage_position(self, ctx, signal):
        """The usual way to act on a signal: long on BUY, flat (or short) on SELL."""
        held = ctx.position
        risk = {"stop_loss": self.p["stop_loss"], "take_profit": self.p["take_profit"]}
        if signal.action == "BUY":
            if held < 0:
                ctx.close(signal.reason)
            if held <= 0:
                ctx.buy(signal.reason, **risk)
        elif signal.action == "SELL":
            if held > 0:
                ctx.close(signal.reason)
            if ctx.allow_short and held >= 0:
                ctx.short(signal.reason, **risk)


class BuyHold(Strategy):
    key, name = "bh", "Buy and hold"
    about = "Buy on the first bar and never sell. The yardstick every rule has to beat."

    def generate_signal(self, h):
        return BUY("buy and hold")


class SMACross(Strategy):
    key, name = "sma", "Moving average cross"
    about = "Long while the fast average is above the slow one, out when it drops below."
    settings = [("fast", "fast average", 20, 2, 200, 1), ("slow", "slow average", 50, 5, 400, 5)]
    grid = {"fast": [10, 20, 30, 50], "slow": [50, 100, 150, 200]}

    def generate_signal(self, h):
        fast, slow = ind.sma(h.closes, int(self.p["fast"])), ind.sma(h.closes, int(self.p["slow"]))
        if fast is None or slow is None:
            return HOLD
        if fast > slow:
            return BUY(f"fast average {fast:.2f} above slow {slow:.2f}")
        return SELL(f"fast average {fast:.2f} below slow {slow:.2f}")


class RSIReversion(Strategy):
    key, name = "rsi", "RSI mean reversion"
    about = "Buy when RSI says oversold, sell when it says overbought."
    settings = [("period", "RSI period", 14, 2, 50, 1), ("low", "buy below", 30, 5, 50, 1),
                ("high", "sell above", 70, 50, 95, 1)]
    grid = {"period": [7, 14], "low": [25, 30, 35], "high": [65, 70, 75]}

    def generate_signal(self, h):
        value = ind.rsi(h.closes, int(self.p["period"]))
        if value is None:
            return HOLD
        if value < self.p["low"]:
            return BUY(f"RSI {value:.1f} below {self.p['low']}")
        if value > self.p["high"]:
            return SELL(f"RSI {value:.1f} above {self.p['high']}")
        return HOLD


class Momentum(Strategy):
    key, name = "mom", "Momentum"
    about = "Buy when the price is up strongly over the lookback, sell when that turns negative."
    settings = [("lookback", "lookback bars", 60, 5, 300, 5), ("threshold", "buy above", 0.05, 0.0, 0.5, 0.01)]
    grid = {"lookback": [20, 60, 120, 250], "threshold": [0.0, 0.05, 0.10]}

    def generate_signal(self, h):
        move = ind.change(h.closes, int(self.p["lookback"]))
        if move is None:
            return HOLD
        if move > self.p["threshold"]:
            return BUY(f"up {move:.1%} over {int(self.p['lookback'])} bars")
        if move < 0:
            return SELL(f"down {move:.1%} over {int(self.p['lookback'])} bars")
        return HOLD


class MeanReversion(Strategy):
    key, name = "mr", "Mean reversion"
    about = "Buy when the price falls well below its average, sell once it gets back."
    settings = [("window", "average of", 20, 5, 200, 1), ("band", "buy below by", 0.05, 0.005, 0.3, 0.005)]
    grid = {"window": [10, 20, 50], "band": [0.03, 0.05, 0.08]}

    def generate_signal(self, h):
        avg = ind.sma(h.closes, int(self.p["window"]))
        if avg is None:
            return HOLD
        price = h.close()
        if price < avg * (1 - self.p["band"]):
            return BUY(f"price {price:.2f} is {1 - price / avg:.1%} below its average")
        if price >= avg:
            return SELL(f"price back to its average {avg:.2f}")
        return HOLD


class Breakout(Strategy):
    key, name = "brk", "Breakout"
    about = "Buy a new high of the channel, sell a new low of half the channel."
    settings = [("window", "channel bars", 40, 5, 250, 5)]
    grid = {"window": [20, 40, 60, 100]}

    def generate_signal(self, h):
        n = int(self.p["window"])
        top, bottom = ind.highest(h.closes, n, skip=1), ind.lowest(h.closes, max(2, n // 2), skip=1)
        if top is None or bottom is None:
            return HOLD
        price = h.close()
        if price > top:
            return BUY(f"new {n} bar high {price:.2f}")
        if price < bottom:
            return SELL(f"new {max(2, n // 2)} bar low {price:.2f}")
        return HOLD


class BuyTheDip(Strategy):
    key, name = "dip", "Buy the dip"
    about = "Buy after a fall from the recent peak, and let the take profit (or stop) close it."
    settings = [("drop", "buy after a fall of", 0.10, 0.02, 0.5, 0.01),
                ("lookback", "peak over bars", 60, 10, 300, 5)]
    grid = {"drop": [0.05, 0.10, 0.15, 0.20], "take_profit": [0.10, 0.20, 0.30]}

    def __init__(self, **params):
        params.setdefault("take_profit", 0.12)
        super().__init__(**params)

    def generate_signal(self, h):
        peak = ind.highest(h.closes, int(self.p["lookback"]))
        if peak is None:
            return HOLD
        price = h.close()
        if price <= peak * (1 - self.p["drop"]):
            return BUY(f"{1 - price / peak:.1%} below the {int(self.p['lookback'])} bar peak")
        return HOLD                      # the exit is the take profit, a position rule


ALL = [BuyHold, SMACross, RSIReversion, Momentum, MeanReversion, Breakout, BuyTheDip]
BY_KEY = {cls.key: cls for cls in ALL}
