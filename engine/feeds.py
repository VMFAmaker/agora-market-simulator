"""
Market feeds.

A feed is just a source of price bars in one common shape. A strategy reads a
feed and never needs to know where the bars came from. Same strategy, real
company, real index, or a made-up market. They all arrive as the same bars.

    from feeds import historical, simulated
    apple = historical("AAPL")          # real daily prices
    crash = simulated("crash")          # a controlled synthetic market

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import math
import os
import random

import universe as U

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DAILY = os.path.join(ROOT, "data", "daily")


class Feed:
    """A market's bars, plus a little about the market. Nothing more."""
    def __init__(self, name, bars, benchmark=None, dates=None, periods_per_year=252, kind="historical"):
        self.name = name
        self.bars = bars
        self.closes = [b["c"] for b in bars]
        self.dates = dates if dates is not None else [b.get("d") for b in bars]
        self.benchmark = benchmark
        self.periods_per_year = periods_per_year
        self.kind = kind

    def __len__(self):
        return len(self.closes)


def historical(symbol):
    """Load a real market from the data downloaded by fetch_data.py."""
    with open(os.path.join(DAILY, U.safe_name(symbol) + ".json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return Feed(d["name"], d["bars"], benchmark=d.get("benchmark"), periods_per_year=252, kind="historical")


def simulated(scenario="normal", seed=None, n=750):
    """
    A controlled, made-up daily market for stress testing. Bounded on purpose, so
    a strategy's result on it is meaningful. Three regimes:
      normal    a steady market with everyday noise
      crash     rises, then a sharp fall, then a slow recovery
      volatile  choppy, high volatility, the odd shock
    """
    rng = random.Random(seed)
    g = lambda: rng.gauss(0, 1)
    if scenario == "crash":
        drift, vol, crash_at, crash_len, depth = 0.0005, 0.012, int(n * 0.55), 25, 0.45
    elif scenario == "volatile":
        drift, vol, crash_at, crash_len, depth = 0.0002, 0.028, -1, 0, 0
    else:
        drift, vol, crash_at, crash_len, depth = 0.0005, 0.011, -1, 0, 0
    price, prev, bars = 100.0, 100.0, []
    for i in range(n):
        r = drift + vol * g()
        if scenario == "volatile" and rng.random() < 0.03:
            r += 0.05 * g()                         # occasional shock
        if crash_at > 0 and crash_at <= i < crash_at + crash_len:
            r += math.log(1 - depth) / crash_len    # the fall, spread over several days
        price *= math.exp(r)
        wig = abs(g()) * vol * 0.4
        bars.append({"d": None, "o": round(prev, 2), "h": round(max(prev, price) * (1 + wig), 2),
                     "l": round(min(prev, price) * (1 - wig), 2), "c": round(price, 2), "v": 0})
        prev = price
    return Feed("Synthetic " + scenario, bars, benchmark=None,
                dates=list(range(n)), periods_per_year=252, kind="simulated")


def agent_market(scenario="normal", seed=None):
    """The full agent model as a feed, for study. Lively but can be wild, so the
    stress test uses simulated() instead. One minute per bar."""
    import agora
    seed = seed if seed is not None else 42
    if scenario == "crash":
        cfg = agora.Config(seed=seed, n_leveraged=16, shock_time=1500.0, shock_size=-0.10)
    elif scenario == "volatile":
        cfg = agora.Config(seed=seed, n_meanrev=8, n_breakout=8, n_news=8, n_whale=4, n_panic=7)
    else:
        cfg = agora.Config(seed=seed)
    bars = agora.Simulation(cfg).run()["candles"]
    return Feed("Agent " + scenario, bars, benchmark=None,
                dates=[b["t"] for b in bars], periods_per_year=None, kind="agent")
