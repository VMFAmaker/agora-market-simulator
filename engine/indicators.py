"""
STRATEGY ENGINE. Indicators, the building blocks of a signal.

Every function takes the history a strategy is allowed to see, and looks only
backwards from the latest closed bar. None means "not enough history yet".

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math


def sma(values, n):
    """Simple moving average of the last n values."""
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) / n


def change(values, n):
    """Percentage change over the last n bars, as a fraction (0.05 is +5%)."""
    if len(values) <= n:
        return None
    return values[-1] / values[-1 - n] - 1


def rsi(values, n=14):
    """
    Relative strength index over the last n price changes, 0 to 100. Uses simple
    averages of the ups and downs (Cutler's version), so it only depends on the
    last n bars and is easy to check by hand. Below 30 is often called oversold.
    """
    if len(values) <= n:
        return None
    ups = downs = 0.0
    for i in range(len(values) - n, len(values)):
        move = values[i] - values[i - 1]
        if move > 0:
            ups += move
        else:
            downs -= move
    if downs == 0:
        return 100.0
    return 100 - 100 / (1 + ups / downs)


def highest(values, n, skip=0):
    """The highest of the n values before the latest 'skip' ones."""
    if len(values) < n + skip:
        return None
    end = len(values) - skip
    return max(values[end - n:end])


def lowest(values, n, skip=0):
    if len(values) < n + skip:
        return None
    end = len(values) - skip
    return min(values[end - n:end])


def atr(history, n=14):
    """Average true range, the typical size of one bar's move, in price."""
    if len(history) <= n:
        return None
    c, h, l = history.closes, history.highs, history.lows
    total = 0.0
    for i in range(len(c) - n, len(c)):
        total += max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return total / n


def volatility(values, n=20):
    """Standard deviation of the last n bar to bar returns (as a fraction)."""
    if len(values) <= n:
        return None
    rets = [math.log(values[i] / values[i - 1]) for i in range(len(values) - n, len(values))]
    mean = sum(rets) / n
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / n)
