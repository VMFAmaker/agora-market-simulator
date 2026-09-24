"""
STRATEGY TESTER. The numbers that describe a result.

    return      total return, CAGR (the steady yearly rate that gives the same end)
    risk        volatility, worst drawdown (peak to trough), longest time underwater
    quality     Sharpe (return per unit of volatility, no risk free rate), Sortino
                (only counts the bad volatility), Calmar (CAGR / worst drawdown)
    trading     round trips, win rate, profit factor (money won / money lost),
                average trade, time in the market, turnover
    costs       commission, spread, slippage and market impact, in money and as a
                share of the starting account
    benchmark   the index over the same days, excess return (CAGR difference),
                beta, alpha, tracking error and information ratio

Coding done with the help of AI, because coding is not the author's strong area.
"""
import math


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def returns(values):
    return [values[i] / values[i - 1] - 1 if values[i - 1] > 0 else 0.0 for i in range(1, len(values))]


def drawdown(values):
    """Worst fall from a peak, and the longest stretch spent below a peak (in bars)."""
    peak, worst, under, longest = -1e18, 0.0, 0, 0
    for v in values:
        if v >= peak:
            peak, under = v, 0
        else:
            under += 1
            longest = max(longest, under)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst, longest


def align(times, bench_times, bench_values):
    """The benchmark's value on each of our times, carrying the last known value forward."""
    out, j, last = [], 0, None
    for t in times:
        while j < len(bench_times) and bench_times[j] <= t:
            last = bench_values[j]
            j += 1
        out.append(last)
    first = next((x for x in out if x is not None), None)
    return [x if x is not None else first for x in out]


def summarise(result, benchmark=None):
    """All the numbers for one result. benchmark is a Market (or None)."""
    eq, ppy = result["equity"], result.get("periods_per_year") or 252
    if len(eq) < 2:
        return {}
    start, end = eq[0], eq[-1]
    rets = returns(eq)
    n_years = len(rets) / ppy
    total = end / start - 1 if start else 0.0
    cagr = (end / start) ** (1 / n_years) - 1 if (start > 0 and end > 0 and n_years > 0) else -1.0
    vol = _stdev(rets) * math.sqrt(ppy)
    sharpe = (_mean(rets) / _stdev(rets) * math.sqrt(ppy)) if _stdev(rets) > 0 else 0.0
    downside = [min(0.0, r) for r in rets]
    dd_dev = math.sqrt(sum(d * d for d in downside) / len(downside)) if downside else 0.0
    sortino = (_mean(rets) / dd_dev * math.sqrt(ppy)) if dd_dev > 0 else 0.0
    max_dd, underwater = drawdown(eq)
    # round trips, with any position still open valued at its last price
    trips, opens = result["trips"], result.get("open_trips", [])
    pnls = [t["pnl"] for t in trips] + [t["pnl_marked"] for t in opens]
    trip_rets = [t["return"] for t in trips] + [t["return"] for t in opens]
    held = [t["bars"] for t in trips] + [t["bars"] for t in opens]
    wins = [x for x in pnls if x > 0]
    won = sum(wins)
    lost = -sum(x for x in pnls if x <= 0)
    in_market = sum(1 for g in result["gross"] if g > 0) / len(result["gross"])
    exposure = _mean([g / e for g, e in zip(result["gross"], eq) if e > 0])
    traded = sum(f["value"] for f in result["fills"])
    fees = result["fees"]
    cost_total = sum(fees.values())
    m = {
        "start": result["times"][0], "end": result["times"][-1], "years": n_years,
        "start_value": start, "end_value": end, "total_return": total, "cagr": cagr,
        "volatility": vol, "sharpe": sharpe, "sortino": sortino,
        "max_drawdown": max_dd, "longest_underwater_bars": underwater,
        "calmar": cagr / abs(max_dd) if max_dd < 0 else 0.0,
        "trades": len(trips), "open_trades": len(opens),
        "win_rate": len(wins) / len(pnls) if pnls else 0.0,
        "profit_factor": won / lost if lost > 0 else (float("inf") if won > 0 else 0.0),
        "avg_trade": _mean(trip_rets),
        "avg_bars_held": _mean(held),
        "time_in_market": in_market, "avg_exposure": exposure,
        "turnover": (traded / _mean(eq) / n_years) if n_years > 0 else 0.0,
        "costs": cost_total, "costs_pct": cost_total / result["start_cash"],
        "commission": fees["commission"], "spread": fees["spread"], "slippage": fees["slippage"],
        "impact": fees["impact"], "dividends": result.get("dividends_total", 0.0),
        "blown_up": result.get("blown", False),
    }
    if benchmark is not None:
        m.update(compare(result, benchmark))
    return m


def compare(result, benchmark):
    """How the strategy did against an index over exactly the same days."""
    eq, ppy = result["equity"], result.get("periods_per_year") or 252
    bench = align(result["times"], benchmark.times, [b.close for b in benchmark.bars])
    if not bench or bench[0] is None:
        return {}
    rs, rb = returns(eq), returns(bench)
    n_years = len(rs) / ppy
    b_total = bench[-1] / bench[0] - 1
    b_cagr = (bench[-1] / bench[0]) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    s_cagr = (eq[-1] / eq[0]) ** (1 / n_years) - 1 if (n_years > 0 and eq[-1] > 0) else -1.0
    mb = _mean(rb)
    var_b = _mean([(x - mb) ** 2 for x in rb])
    cov = _mean([(a - _mean(rs)) * (b - mb) for a, b in zip(rs, rb)])
    beta = cov / var_b if var_b > 0 else 0.0
    alpha = (_mean(rs) - beta * mb) * ppy
    active = [a - b for a, b in zip(rs, rb)]
    te = _stdev(active) * math.sqrt(ppy)
    sd_s, sd_b = _stdev(rs), _stdev(rb)
    return {
        "benchmark": benchmark.name, "benchmark_symbol": benchmark.symbol,
        "benchmark_return": b_total, "benchmark_cagr": b_cagr,
        "excess_return": (eq[-1] / eq[0] - 1) - b_total, "excess_cagr": s_cagr - b_cagr,
        "beta": beta, "alpha": alpha, "tracking_error": te,
        "information_ratio": (_mean(active) * ppy / te) if te > 0 else 0.0,
        "correlation": (cov / (sd_s * sd_b)) if sd_s > 0 and sd_b > 0 else 0.0,
        "benchmark_curve": bench,
    }
