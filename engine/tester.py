"""
The strategy tester.

Runs a strategy on a feed (real or simulated, it does not matter), works out how
it did, compares it to its benchmark index, and stress tests it on synthetic
markets. Trades pay a small cost, so results are not flattering by accident.

    backtest(feed, strategy)      -> equity curve, trades, metrics
    benchmark_compare(...)        -> benchmark return, excess return, beta, alpha
    stress_test(strategy)         -> how it holds up on normal / crash / volatile

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math

import feeds


def backtest(feed, strategy, cost_bps=5, start=100000.0):
    closes = feed.closes
    pos = strategy.positions(closes)
    cost = cost_bps / 10000.0                       # a trade pays this fraction (spread plus fee)
    cash, shares, entry, wins, trips = start, 0.0, 0.0, 0, 0
    equity, trades = [], []
    for i, p in enumerate(closes):
        if pos[i] == 1 and shares == 0:             # buy
            fill = p * (1 + cost)
            shares, cash, entry = cash / fill, 0.0, fill
            trades.append(("buy", i, p))
        elif pos[i] == 0 and shares > 0:            # sell
            fill = p * (1 - cost)
            cash, shares, trips = shares * fill, 0.0, trips + 1
            wins += 1 if fill > entry else 0
            trades.append(("sell", i, p))
        equity.append(cash + shares * p)
    return {"equity": equity, "positions": pos, "trades": trades,
            "metrics": _metrics(equity, pos, trips, wins, feed.periods_per_year)}


def _max_drawdown(equity):
    peak, worst = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        if peak > 0:
            worst = min(worst, e / peak - 1)
    return worst


def _metrics(equity, pos, trips, wins, ppy):
    n = len(equity)
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, n) if equity[i - 1] > 0]
    out = {"total_return": equity[-1] / equity[0] - 1,
           "max_drawdown": _max_drawdown(equity),
           "trades": trips,
           "win_rate": wins / trips if trips else 0.0,
           "time_in_market": sum(pos) / n}
    if ppy:                                          # annualised figures need a periods-per-year
        years = n / ppy
        out["cagr"] = (equity[-1] / equity[0]) ** (1 / years) - 1 if years > 0 and equity[-1] > 0 else float("nan")
        mean = sum(rets) / len(rets) if rets else 0.0
        sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) if rets else 0.0
        out["volatility"] = sd * math.sqrt(ppy)
        out["sharpe"] = (mean / sd) * math.sqrt(ppy) if sd > 0 else 0.0
    return out


def benchmark_compare(feed, result):
    """Compare the strategy to buying and holding its benchmark index."""
    if not feed.benchmark:
        return None
    bench = feeds.historical(feed.benchmark)
    bd = dict(zip(bench.dates, bench.closes))
    dates = feed.dates
    common = [d for d in dates if d in bd]
    if len(common) < 10:
        return None
    bench_total = bd[common[-1]] / bd[common[0]] - 1
    years = len(common) / (feed.periods_per_year or 252)
    bench_cagr = (bd[common[-1]] / bd[common[0]]) ** (1 / years) - 1 if years > 0 else float("nan")
    eq_by_date = dict(zip(dates, result["equity"]))
    sret, bret = [], []
    for i in range(1, len(common)):
        d0, d1 = common[i - 1], common[i]
        if d0 in eq_by_date and d1 in eq_by_date and eq_by_date[d0] > 0:
            sret.append(eq_by_date[d1] / eq_by_date[d0] - 1)
            bret.append(bd[d1] / bd[d0] - 1)
    beta = alpha = float("nan")
    if len(bret) > 2:
        mb, ms = sum(bret) / len(bret), sum(sret) / len(sret)
        var = sum((x - mb) ** 2 for x in bret) / len(bret)
        cov = sum((bret[i] - mb) * (sret[i] - ms) for i in range(len(bret))) / len(bret)
        if var > 0:
            beta = cov / var
            alpha = (ms - beta * mb) * (feed.periods_per_year or 252)
    return {"benchmark": bench.name, "benchmark_return": bench_total, "benchmark_cagr": bench_cagr,
            "excess_return": result["metrics"]["total_return"] - bench_total,
            "excess_cagr": result["metrics"].get("cagr", float("nan")) - bench_cagr,
            "beta": beta, "alpha": alpha}


def stress_test(strategy, scenarios=("normal", "crash", "volatile"), seed=1):
    """Run the same strategy on synthetic markets to see how it copes."""
    out = {}
    for sc in scenarios:
        f = feeds.simulated(sc, seed=seed)
        r = backtest(f, strategy)
        out[sc] = {"strategy_return": r["metrics"]["total_return"],
                   "max_drawdown": r["metrics"]["max_drawdown"],
                   "buy_hold_return": f.closes[-1] / f.closes[0] - 1}
    return out
