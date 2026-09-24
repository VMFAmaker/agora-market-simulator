"""
STRATEGY TESTER. Strategy -> Experiment -> Results -> Robustness.

An Experiment holds every choice in one place:

    step 1  the strategy and its settings (plus stop loss, take profit, sizing)
    step 2  the market, its benchmark, the data frequency and the period
    step 3  the method, and the execution assumptions

and run(experiment) returns the results. The methods:

    backtest        the whole period in one go. Labelled clearly as a HISTORICAL
                    backtest, because doing well on the past proves nothing about
                    the future.
    out_of_sample   pick the best settings on the first part (training), freeze
                    them, then test on the part the optimiser never saw.
    walk_forward    do that again and again, rolling forward. Train on three
                    years, test on the next one, move on a year, repeat, and join
                    all the test years together. The fairest test here.
    stress          run it on the synthetic markets (crash, bear, chop, ...).

and the robustness checks that go with any of them:

    cost_sensitivity    the same test at 0, 0.01, 0.05, 0.10 and 0.25% slippage
    fill_sensitivity    next open (honest) against same close (optimistic)
    parameter_map       every setting in the grid over the whole period, to see
                        whether the result is a broad plateau or one lucky peak

    from tester import Experiment, run
    res = run(Experiment("sma", symbols=["MSFT"], method="walk_forward"))

Coding done with the help of AI, because coding is not the author's strong area.
"""
import copy
import itertools

import metrics
import simulator
from backtest import Config
from backtest import run as run_backtest
from market_data import load
from strategies import BY_KEY, BuyHold

METHOD_LABEL = {
    "backtest": "Historical backtest",
    "out_of_sample": "Out-of-sample test",
    "walk_forward": "Walk-forward test",
    "stress": "Stress test on synthetic markets",
}
METHOD_WARNING = {
    "backtest": "This is how the rule would have done on data it was tuned on. It does not prove future profit.",
    "out_of_sample": "Settings were chosen on the training years only, then frozen and tested on years the optimiser never saw.",
    "walk_forward": "Settings were re-chosen every year using only the years before it. Only the unseen test years count.",
    "stress": "Synthetic markets, each built to be one clear kind of market. They say how a rule copes, not what it will earn.",
}


class Experiment:
    def __init__(self, strategy="sma", params=None, symbols=("MSFT",), benchmark="auto", interval="1d",
                 start=None, end=None, config=None, method="backtest", split=0.7,
                 train_years=3, test_years=1, objective="sharpe", train_bars=None, test_bars=None,
                 scenarios=tuple(simulator.SCENARIOS), seeds=(1, 2, 3)):
        self.strategy = BY_KEY[strategy] if isinstance(strategy, str) else strategy
        self.params = dict(params or {})
        self.symbols = [symbols] if isinstance(symbols, str) else list(symbols)
        self.benchmark, self.interval = benchmark, interval
        self.start, self.end = start, end
        self.config = config or Config()
        self.method, self.split = method, split
        self.train_years, self.test_years, self.objective = train_years, test_years, objective
        self.train_bars, self.test_bars = train_bars, test_bars        # window sizes in bars, for intraday data
        self.scenarios, self.seeds = scenarios, seeds

    def describe(self):
        return {"strategy": self.strategy.name, "params": self.params, "symbols": self.symbols,
                "benchmark": self.benchmark, "interval": self.interval, "start": self.start,
                "end": self.end, "method": METHOD_LABEL[self.method], "config": self.config.describe()}


# ---------------- helpers ----------------
def markets_for(exp):
    markets = [load(s, exp.interval) for s in exp.symbols]
    bench_sym = exp.benchmark
    if bench_sym == "auto":
        bench_sym = markets[0].benchmark if len(markets) == 1 else "^GSPC"
    bench = load(bench_sym, "1d") if bench_sym and exp.interval == "1d" else None
    return markets, bench


def _with(config, **changes):
    c = copy.copy(config)
    for k, v in changes.items():
        setattr(c, k, v)
    return c


def _valid(strategy, params):
    if "fast" in params and "slow" in params and params["fast"] >= params["slow"]:
        return False
    if "low" in params and "high" in params and params["low"] >= params["high"]:
        return False
    return True


def grid_of(strategy, base):
    """Every combination of the strategy's grid, on top of the base settings."""
    keys = list(strategy.grid)
    combos = []
    for values in itertools.product(*[strategy.grid[k] for k in keys]):
        p = dict(base)
        p.update(dict(zip(keys, values)))
        if _valid(strategy, p):
            combos.append(p)
    return combos or [dict(base)]


def score(m, objective):
    if not m:
        return -1e9
    if objective == "cagr":
        return m["cagr"]
    if objective == "calmar":
        return m["calmar"]
    return m["sharpe"]


def one(exp, markets, params, start, end, bench=None, config=None):
    """One backtest over [start, end], and its numbers."""
    cfg = _with(config or exp.config, start=start, end=end)
    r = run_backtest(markets, exp.strategy, params, cfg)
    return r, metrics.summarise(r, bench)


def optimise(exp, markets, start, end):
    """Try every setting in the grid on [start, end]. Best first."""
    table = []
    for p in grid_of(exp.strategy, exp.params):
        _, m = one(exp, markets, p, start, end)
        table.append({"params": p, "score": score(m, exp.objective), "cagr": m.get("cagr"),
                      "sharpe": m.get("sharpe"), "max_drawdown": m.get("max_drawdown"),
                      "trades": m.get("trades")})
    table.sort(key=lambda row: row["score"], reverse=True)
    return table[0]["params"], table


def _times(market, start, end):
    return [b.time for b in market.bars if (start is None or b.time >= start) and (end is None or b.time[:len(end)] <= end)]


def _pack(result, m, bench=None):
    """Keep what the page and the report need, and drop the heavy bits."""
    out = {"metrics": {k: v for k, v in m.items() if k != "benchmark_curve"},
           "times": result["times"], "equity": result["equity"], "gross": result["gross"],
           "fills": result["fills"], "trips": result["trips"], "orders": result["orders"],
           "dividends": result["dividends"], "fees": result["fees"], "params": result["params"]}
    if bench is not None and "benchmark_curve" in m:
        out["benchmark_curve"] = m["benchmark_curve"]
    return out


# ---------------- the methods ----------------
def backtest(exp):
    markets, bench = markets_for(exp)
    r, m = one(exp, markets, exp.params, exp.start, exp.end, bench)
    hold_r, hold_m = (r, m) if exp.strategy is BuyHold else _hold(exp, markets, exp.start, exp.end, bench)
    return {"method": "backtest", "label": METHOD_LABEL["backtest"], "warning": METHOD_WARNING["backtest"],
            "experiment": exp.describe(), "main": _pack(r, m, bench),
            "buy_hold": {"metrics": hold_m, "equity": hold_r["equity"]}}


def _hold(exp, markets, start, end, bench):
    cfg = _with(exp.config, start=start, end=end)
    r = run_backtest(markets, BuyHold, {}, cfg)
    return r, metrics.summarise(r, bench)


def out_of_sample(exp):
    markets, bench = markets_for(exp)
    times = _times(markets[0], exp.start, exp.end)
    cut = exp.split if isinstance(exp.split, str) else times[int(len(times) * exp.split)]
    train_end = max(t for t in times if t < cut)
    best, table = optimise(exp, markets, times[0], train_end)
    train_r, train_m = one(exp, markets, best, times[0], train_end, bench)
    test_r, test_m = one(exp, markets, best, cut, times[-1], bench)
    hold_r, hold_m = _hold(exp, markets, cut, times[-1], bench)
    return {"method": "out_of_sample", "label": METHOD_LABEL["out_of_sample"],
            "warning": METHOD_WARNING["out_of_sample"], "experiment": exp.describe(),
            "train": {"start": times[0], "end": train_end, "metrics": train_m},
            "test": {"start": cut, "end": times[-1]}, "chosen": best, "grid": table[:10],
            "main": _pack(test_r, test_m, bench),
            "buy_hold": {"metrics": hold_m, "equity": hold_r["equity"]},
            "degradation": {"sharpe": test_m.get("sharpe", 0) - train_m.get("sharpe", 0),
                            "cagr": test_m.get("cagr", 0) - train_m.get("cagr", 0)}}


def walk_forward(exp):
    markets, bench = markets_for(exp)
    ppy = markets[0].periods_per_year or 252
    times = _times(markets[0], exp.start, exp.end)
    train_n = exp.train_bars or int(exp.train_years * ppy)
    test_n = exp.test_bars or int(exp.test_years * ppy)
    folds, stitched, all_fills, all_trips, all_orders, all_divs = [], {"times": [], "equity": [], "gross": []}, [], [], [], []
    all_open = []
    fees = {"commission": 0.0, "spread": 0.0, "slippage": 0.0, "impact": 0.0}
    cash, a = exp.config.cash, 0
    while a + train_n < len(times):
        tr_a, tr_b = times[a], times[a + train_n - 1]
        te_a = times[a + train_n]
        te_b = times[min(len(times), a + train_n + test_n) - 1]
        if min(len(times), a + train_n + test_n) - (a + train_n) < 20:
            break                                                  # too short to mean anything
        best, _ = optimise(exp, markets, tr_a, tr_b)
        _, is_m = one(exp, markets, best, tr_a, tr_b)
        cfg = _with(exp.config, cash=cash)
        r, m = one(exp, markets, best, te_a, te_b, bench, cfg)
        folds.append({"train": [tr_a, tr_b], "test": [te_a, te_b], "params": best,
                      "train_cagr": is_m.get("cagr"), "train_sharpe": is_m.get("sharpe"),
                      "test_return": m.get("total_return"), "test_sharpe": m.get("sharpe"),
                      "test_max_drawdown": m.get("max_drawdown"), "trades": m.get("trades"),
                      "benchmark_return": m.get("benchmark_return")})
        for k in ("times", "equity", "gross"):
            stitched[k] += r[k]
        all_fills += r["fills"]; all_trips += r["trips"]; all_orders += r["orders"]; all_divs += r["dividends"]
        all_open += r["open_trips"]
        for k in fees:
            fees[k] += r["fees"][k]
        cash = r["equity"][-1]
        a += test_n
    if not folds:
        raise ValueError("not enough data for one training window and one test window")
    joined = {**stitched, "fills": all_fills, "trips": all_trips, "open_trips": all_open, "orders": all_orders, "dividends": all_divs,
              "fees": fees, "periods_per_year": ppy, "start_cash": exp.config.cash,
              "dividends_total": sum(d["amount"] for d in all_divs), "params": folds[-1]["params"]}
    m = metrics.summarise(joined, bench)
    hold_r, hold_m = _hold(_with_cash(exp, exp.config.cash), markets, folds[0]["test"][0], folds[-1]["test"][1], bench)
    train_cagrs = [f["train_cagr"] for f in folds if f["train_cagr"] is not None]
    avg_is = sum(train_cagrs) / len(train_cagrs) if train_cagrs else 0.0
    settings = [tuple(sorted(f["params"].items())) for f in folds]
    return {"method": "walk_forward", "label": METHOD_LABEL["walk_forward"], "warning": METHOD_WARNING["walk_forward"],
            "experiment": exp.describe(), "folds": folds, "main": _pack(joined, m, bench),
            "buy_hold": {"metrics": hold_m, "equity": hold_r["equity"]},
            "efficiency": (m["cagr"] / avg_is) if avg_is > 0 else None,
            "stability": {"folds": len(folds), "different_settings": len(set(settings))}}


def _with_cash(exp, cash):
    e = copy.copy(exp)
    e.config = _with(exp.config, cash=cash)
    return e


def stress(exp):
    rows = []
    for scen in exp.scenarios:
        results, holds = [], []
        for seed in exp.seeds:
            mk = simulator.synthetic(scen, seed)
            cfg = _with(exp.config, start=None, end=None)
            m = metrics.summarise(run_backtest([mk], exp.strategy, exp.params, cfg))
            h = metrics.summarise(run_backtest([mk], BuyHold, {}, cfg))
            results.append(m); holds.append(h)
        avg = lambda key, xs: sum(x[key] for x in xs) / len(xs)
        rows.append({"scenario": scen, "about": simulator.ABOUT[scen],
                     "return": avg("total_return", results), "worst_return": min(x["total_return"] for x in results),
                     "max_drawdown": avg("max_drawdown", results), "sharpe": avg("sharpe", results),
                     "trades": avg("trades", results), "buy_hold_return": avg("total_return", holds),
                     "buy_hold_drawdown": avg("max_drawdown", holds)})
    example = simulator.synthetic("crash", exp.seeds[0])
    r = run_backtest([example], exp.strategy, exp.params, _with(exp.config, start=None, end=None))
    return {"method": "stress", "label": METHOD_LABEL["stress"], "warning": METHOD_WARNING["stress"],
            "experiment": exp.describe(), "scenarios": rows,
            "main": _pack(r, metrics.summarise(r))}


# ---------------- robustness ----------------
def cost_sensitivity(exp, levels=(0.0, 1.0, 5.0, 10.0, 25.0)):
    markets, bench = markets_for(exp)
    rows = []
    for bps in levels:
        ex = copy.copy(exp.config.execution)
        ex.slippage_bps = bps
        _, m = one(exp, markets, exp.params, exp.start, exp.end, bench, _with(exp.config, execution=ex))
        rows.append({"slippage_bps": bps, "cagr": m["cagr"], "sharpe": m["sharpe"],
                     "excess_cagr": m.get("excess_cagr"), "costs_pct": m["costs_pct"], "trades": m["trades"]})
    return rows


def fill_sensitivity(exp):
    markets, bench = markets_for(exp)
    rows = []
    for mode in ("next_open", "close"):
        ex = copy.copy(exp.config.execution)
        ex.fill_at = mode
        _, m = one(exp, markets, exp.params, exp.start, exp.end, bench, _with(exp.config, execution=ex))
        rows.append({"fill_at": mode, "cagr": m["cagr"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"]})
    return rows


def parameter_map(exp):
    markets, bench = markets_for(exp)
    rows = []
    for p in grid_of(exp.strategy, exp.params):
        _, m = one(exp, markets, p, exp.start, exp.end, bench)
        rows.append({"params": p, "cagr": m["cagr"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"]})
    return rows


def run(exp, robustness=True):
    method = {"backtest": backtest, "out_of_sample": out_of_sample,
              "walk_forward": walk_forward, "stress": stress}[exp.method]
    res = method(exp)
    if robustness and exp.method != "stress":
        res["robustness"] = {"costs": cost_sensitivity(exp), "fills": fill_sensitivity(exp)}
    return res
