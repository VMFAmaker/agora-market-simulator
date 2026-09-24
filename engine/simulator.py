"""
MARKET SIMULATOR. Made-up markets for stress testing.

These are controlled on purpose. Each scenario is one clear kind of market, so if
a strategy fails on it we know why. They come out in exactly the same shape as a
real market, so the tester cannot tell the difference.

  normal     a steady rise with everyday noise
  crash      rises, then a sharp 45% fall over a month, then a slow recovery
  volatile   choppy, high volatility, the odd shock
  bear       a long, slow grind down (a lost decade)
  sideways   no trend at all, the price wanders in a range
  flash      a calm market with a sudden 20% one day drop that half recovers

The full agent model (agora.py) is also here as agent_market(), for study. It is
lively but can run away on some seeds, so the stress test uses the scenarios above.

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math
import random

from market_data import Bar, Market

SCENARIOS = ["normal", "crash", "volatile", "bear", "sideways", "flash"]

ABOUT = {
    "normal": "A steady rise with everyday noise.",
    "crash": "A rise, then a sharp 45% fall over a month, then a slow recovery.",
    "volatile": "Choppy and nervous, high volatility with the odd shock.",
    "bear": "A long slow grind down, about 12% a year.",
    "sideways": "No trend at all, the price wanders inside a range.",
    "flash": "Calm, then a sudden 20% one day drop that half recovers.",
}


def synthetic(scenario="normal", seed=1, n=1000):
    """A controlled daily market, about four years long by default."""
    rng = random.Random(seed)
    g = lambda: rng.gauss(0, 1)
    drift, vol = 0.0005, 0.011
    crash_at, crash_len, depth = -1, 0, 0.0
    if scenario == "crash":
        crash_at, crash_len, depth, vol = int(n * 0.55), 22, 0.45, 0.012
    elif scenario == "volatile":
        drift, vol = 0.0002, 0.028
    elif scenario == "bear":
        drift, vol = -0.0005, 0.013
    elif scenario == "sideways":
        drift, vol = 0.0, 0.012
    elif scenario == "flash":
        drift, vol = 0.0004, 0.009
    price, prev, bars = 100.0, 100.0, []
    anchor = 100.0
    for i in range(n):
        r = drift + vol * g()
        if scenario == "volatile" and rng.random() < 0.03:
            r += 0.05 * g()                                   # occasional shock
        if scenario == "sideways":
            r += 0.02 * math.log(anchor / price)              # pulled back towards the middle
        if crash_at > 0 and crash_at <= i < crash_at + crash_len:
            r += math.log(1 - depth) / crash_len              # the fall, spread over several days
        if scenario == "flash" and i == int(n * 0.6):
            r += math.log(0.80)                               # the one day drop
        if scenario == "flash" and int(n * 0.6) < i <= int(n * 0.6) + 10:
            r += math.log(1.10) / 10                          # half of it comes back
        open_ = prev * math.exp(vol * 0.3 * g())              # a small overnight gap
        price *= math.exp(r)
        wig = abs(g()) * vol * 0.5
        high = max(open_, price) * (1 + wig)
        low = min(open_, price) * (1 - wig)
        volume = int(2_000_000 * math.exp(0.3 * g()) * (1 + 20 * abs(r)))   # busier on big days
        bars.append(Bar("D%05d" % (i + 1), round(open_, 4), round(high, 4), round(low, 4),
                        round(price, 4), volume))
        prev = price
    return Market("SIM-" + scenario.upper(), "Synthetic " + scenario, bars, interval="1d",
                  kind="simulated", periods_per_year=252)


def agent_market(scenario="normal", seed=42):
    """The full agent model as a market, one bar per simulated minute, for study."""
    import agora
    if scenario == "crash":
        cfg = agora.Config(seed=seed, n_leveraged=16, shock_time=1500.0, shock_size=-0.10)
    elif scenario == "volatile":
        cfg = agora.Config(seed=seed, n_meanrev=8, n_breakout=8, n_news=8, n_whale=4, n_panic=7)
    else:
        cfg = agora.Config(seed=seed)
    rows = agora.Simulation(cfg).run()["candles"]
    bars = [Bar("M%05d" % i, r["o"], r["h"], r["l"], r["c"], r.get("v", 0)) for i, r in enumerate(rows)]
    return Market("AGX-" + scenario.upper(), "Agent market " + scenario, bars, interval="1m",
                  kind="agent", periods_per_year=None)
