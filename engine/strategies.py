"""
Trading strategies.

Every strategy follows the same tiny contract: given the list of closing prices,
return a list of positions, one per bar, where 1 means "hold the market" and 0
means "in cash". A strategy never sees dates, names, or whether the data is real.
That is what lets the tester run any strategy on any feed.

Defaults here suit DAILY data. Coding done with the help of AI.
"""


def _sma(prices, window):
    out, total = [None] * len(prices), 0.0
    for i, p in enumerate(prices):
        total += p
        if i >= window:
            total -= prices[i - window]
        out[i] = total / window if i >= window - 1 else None
    return out


class Strategy:
    name = "strategy"
    def positions(self, closes):
        raise NotImplementedError


class BuyHold(Strategy):
    name = "Buy and hold"
    def positions(self, closes):
        return [1] * len(closes)


class SMACross(Strategy):
    """Hold while a fast average is above a slow one."""
    def __init__(self, fast=20, slow=50):
        self.fast, self.slow = fast, slow
        self.name = f"MA cross {fast}/{slow}"
    def positions(self, closes):
        f, s = _sma(closes, self.fast), _sma(closes, self.slow)
        return [1 if (f[i] is not None and s[i] is not None and f[i] >= s[i]) else 0
                for i in range(len(closes))]


class Momentum(Strategy):
    """Buy strength, sell weakness, over a lookback window."""
    def __init__(self, window=20, threshold=0.05):
        self.window, self.thr = window, threshold
        self.name = f"Momentum {window}d {int(threshold*100)}%"
    def positions(self, closes):
        pos, state = [0] * len(closes), 0
        for i in range(len(closes)):
            if i >= self.window:
                r = closes[i] / closes[i - self.window] - 1
                if state == 0 and r > self.thr:
                    state = 1
                elif state == 1 and r < -self.thr * 0.5:
                    state = 0
            pos[i] = state
        return pos


class MeanReversion(Strategy):
    """Buy when the price is well below its average, sell when it climbs back."""
    def __init__(self, window=20, band=0.05):
        self.window, self.band = window, band
        self.name = f"Mean reversion {window}d {int(band*100)}%"
    def positions(self, closes):
        m, pos, state = _sma(closes, self.window), [0] * len(closes), 0
        for i in range(len(closes)):
            if m[i] is not None:
                if state == 0 and closes[i] < m[i] * (1 - self.band):
                    state = 1
                elif state == 1 and closes[i] >= m[i]:
                    state = 0
            pos[i] = state
        return pos


class Breakout(Strategy):
    """Buy on a break above the recent high, sell on a break below the recent low."""
    def __init__(self, window=40):
        self.window = window
        self.name = f"Breakout {window}d"
    def positions(self, closes):
        pos, state = [0] * len(closes), 0
        for i in range(len(closes)):
            if i >= self.window:
                hi = max(closes[i - self.window:i])
                lo = min(closes[i - self.window:i])
                if state == 0 and closes[i] > hi:
                    state = 1
                elif state == 1 and closes[i] < lo:
                    state = 0
            pos[i] = state
        return pos


class BuyTheDip(Strategy):
    """Buy after a fall from the recent peak, take profit after a rise."""
    def __init__(self, drop=0.10, rise=0.12):
        self.drop, self.rise = drop, rise
        self.name = f"Buy the dip -{int(drop*100)}%/+{int(rise*100)}%"
    def positions(self, closes):
        pos, state, peak, entry = [0] * len(closes), 0, closes[0], 0.0
        for i, p in enumerate(closes):
            peak = max(peak, p)
            if state == 0 and p < peak * (1 - self.drop):
                state, entry = 1, p
            elif state == 1 and p > entry * (1 + self.rise):
                state, peak = 0, p
            pos[i] = state
        return pos


# a ready-made set to loop over
ALL = [BuyHold(), SMACross(), Momentum(), MeanReversion(), Breakout(), BuyTheDip()]
