"""
RESEARCH REPORT. Run the whole study and write the results.

Every strategy, on a basket of twelve real companies, through every method the
tester has. Everything is compared with the S&P 500 Total Return index (the
market with dividends put back in), because the strategies collect dividends too.

    1. backtest         the plain historical test, the number most people quote
    2. walk_forward     settings re-chosen every year on past data only, the fair test
    3. out_of_sample    tuned on 2016 to 2023, judged on 2023 to 2026
    4. costs            the same backtest at five levels of slippage
    5. fills            next open (honest) against same close (optimistic)
    6. stress           the six synthetic markets, three runs each
    7. portfolio        one rule across all twelve companies at once
    8. example          moving average cross on Microsoft in full detail

Saves output/research_results.json and draws the charts in charts/.

    python run_research.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os
import statistics
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import execution
import metrics
import simulator
import sizing
import tester
from backtest import Config, run as run_backtest
from market_data import load
from strategies import ALL, BuyHold, Momentum, SMACross

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "output")
CHARTS = os.path.join(ROOT, "charts")

BASKET = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "JPM", "WMT", "KO", "BA", "XOM", "JNJ"]
BENCH = "^SP500TR"
SLIPPAGE = [0.0, 1.0, 5.0, 10.0, 25.0]
NAVY, TEAL, GREY, RED, BLUE, GOLD = "#1b2a4a", "#0f8b8d", "#9aa5b1", "#c0392b", "#3b6fb6", "#d4a017"


def mean(xs):
    xs = [x for x in xs if x is not None and x == x]
    return sum(xs) / len(xs) if xs else None


def median(xs):
    xs = [x for x in xs if x is not None and x == x]
    return statistics.median(xs) if xs else None


def clean(x):
    """Plain JSON has no infinity (a profit factor with no losing trades), so write null."""
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


def experiment(strategy, symbol, method="backtest", **kw):
    return tester.Experiment(strategy, symbols=[symbol], benchmark=BENCH, method=method, **kw)


def style(ax, title):
    ax.set_title(title, loc="left", fontsize=12, color=NAVY, fontweight="bold", pad=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#cccccc")
    ax.spines["bottom"].set_color("#cccccc")
    ax.tick_params(colors="#444444", labelsize=9)
    ax.grid(axis="y", color="#eeeeee")
    ax.set_axisbelow(True)


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(CHARTS, exist_ok=True)
    names = {cls.key: cls.name for cls in ALL}
    res = {"built": date.today().isoformat(), "basket": BASKET, "benchmark": "S&P 500 Total Return",
           "settings": Config().describe()}

    # ---- 1, 2, 3 and 5: backtest, walk-forward, out-of-sample and fill timing, per company ----
    print(f"Testing {len(ALL)} strategies on {len(BASKET)} companies, four ways each ...")
    bt, wf, oos, fills = {}, {}, {}, {}
    for cls in ALL:
        k = cls.key
        rows_bt, rows_wf, rows_oos, rows_fill = [], [], [], []
        for sym in BASKET:
            b = tester.backtest(experiment(k, sym))
            m = b["main"]["metrics"]
            rows_bt.append({"symbol": sym, "cagr": m["cagr"], "sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
                            "excess_cagr": m["excess_cagr"], "win_rate": m["win_rate"], "trades": m["trades"],
                            "costs_pct": m["costs_pct"], "hold_cagr": b["buy_hold"]["metrics"]["cagr"]})
            w = tester.walk_forward(experiment(k, sym, "walk_forward"))
            wm, hm = w["main"]["metrics"], w["buy_hold"]["metrics"]
            # the best backtest you could publish with hindsight: every setting tried on the
            # very same years the walk-forward traded, and the best one kept
            span = experiment(k, sym, start=w["folds"][0]["test"][0], end=w["folds"][-1]["test"][1])
            best = max(tester.parameter_map(span), key=lambda r: r["sharpe"])
            rows_wf.append({"symbol": sym, "cagr": wm["cagr"], "sharpe": wm["sharpe"], "max_drawdown": wm["max_drawdown"],
                            "excess_cagr": wm["excess_cagr"], "hold_cagr": hm["cagr"], "efficiency": w["efficiency"],
                            "hindsight_cagr": best["cagr"], "hindsight_sharpe": best["sharpe"],
                            "settings_changes": w["stability"]["different_settings"] - 1})
            if cls is not BuyHold:
                o = tester.out_of_sample(experiment(k, sym, "out_of_sample"))
                rows_oos.append({"symbol": sym, "train_sharpe": o["train"]["metrics"]["sharpe"],
                                 "test_sharpe": o["main"]["metrics"]["sharpe"],
                                 "train_cagr": o["train"]["metrics"]["cagr"], "test_cagr": o["main"]["metrics"]["cagr"]})
            f = tester.fill_sensitivity(experiment(k, sym))
            rows_fill.append({"symbol": sym, "next_open": f[0]["cagr"], "close": f[1]["cagr"]})
        name = names[k]
        bt[name] = {"cagr": mean([r["cagr"] for r in rows_bt]), "sharpe": mean([r["sharpe"] for r in rows_bt]),
                    "max_drawdown": mean([r["max_drawdown"] for r in rows_bt]),
                    "excess_cagr": mean([r["excess_cagr"] for r in rows_bt]), "win_rate": mean([r["win_rate"] for r in rows_bt]),
                    "trades": mean([r["trades"] for r in rows_bt]), "costs_pct": mean([r["costs_pct"] for r in rows_bt]),
                    "per_company": rows_bt}
        wf[name] = {"cagr": mean([r["cagr"] for r in rows_wf]), "sharpe": mean([r["sharpe"] for r in rows_wf]),
                    "max_drawdown": mean([r["max_drawdown"] for r in rows_wf]),
                    "excess_cagr": mean([r["excess_cagr"] for r in rows_wf]), "hold_cagr": mean([r["hold_cagr"] for r in rows_wf]),
                    "efficiency": median([r["efficiency"] for r in rows_wf]),
                    "hindsight_cagr": mean([r["hindsight_cagr"] for r in rows_wf]),
                    "hindsight_sharpe": mean([r["hindsight_sharpe"] for r in rows_wf]),
                    "beat_hold": sum(1 for r in rows_wf if r["cagr"] > r["hold_cagr"]),
                    "beat_index": sum(1 for r in rows_wf if r["excess_cagr"] > 0), "per_company": rows_wf}
        if rows_oos:
            oos[name] = {"train_sharpe": mean([r["train_sharpe"] for r in rows_oos]),
                         "test_sharpe": mean([r["test_sharpe"] for r in rows_oos]),
                         "train_cagr": mean([r["train_cagr"] for r in rows_oos]),
                         "test_cagr": mean([r["test_cagr"] for r in rows_oos]),
                         "held_up": sum(1 for r in rows_oos if r["test_sharpe"] >= 0.7 * r["train_sharpe"]),
                         "per_company": rows_oos}
        fills[name] = {"next_open": mean([r["next_open"] for r in rows_fill]), "close": mean([r["close"] for r in rows_fill])}
        print(f"  {name:22} best with hindsight {wf[name]['hindsight_cagr']:+6.1%} a year, walk-forward {wf[name]['cagr']:+6.1%}, "
              f"buy and hold over the same years {wf[name]['hold_cagr']:+6.1%}")
    res.update({"backtest": bt, "walk_forward": wf, "out_of_sample": oos, "fills": fills})

    # ---- 4: costs ----
    print("Cost sensitivity ...")
    costs = {}
    for cls in ALL:
        per_level = {}
        for bps in SLIPPAGE:
            vals = []
            for sym in BASKET:
                rows = tester.cost_sensitivity(experiment(cls.key, sym), levels=(bps,))
                vals.append(rows[0]["cagr"])
            per_level[str(bps)] = mean(vals)
        costs[names[cls.key]] = per_level
    res["costs"] = costs

    # ---- 6: stress ----
    print("Stress tests ...")
    stress = {}
    for cls in ALL:
        s = tester.stress(tester.Experiment(cls.key, method="stress"))
        stress[names[cls.key]] = {r["scenario"]: {"return": r["return"], "max_drawdown": r["max_drawdown"]} for r in s["scenarios"]}
    res["stress"] = stress
    res["scenarios"] = {s: simulator.ABOUT[s] for s in simulator.SCENARIOS}

    # ---- 7: one rule across all twelve companies ----
    print("Portfolios across the whole basket ...")
    markets = [load(s) for s in BASKET]
    bench = load(BENCH)
    port = {}
    port_curves = {}
    for label, cls, cfg in [
        ("Momentum, 10% per company", Momentum, Config(sizing=sizing.FixedPercent(0.10), max_position=0.20)),
        ("Moving average cross, 10% per company", SMACross, Config(sizing=sizing.FixedPercent(0.10), max_position=0.20)),
        ("Buy and hold, equal weight", BuyHold, Config(sizing=sizing.FixedPercent(1 / len(BASKET)), max_position=0.20)),
    ]:
        r = run_backtest(markets, cls, {}, cfg)
        m = metrics.summarise(r, bench)
        port[label] = {k: m[k] for k in ("cagr", "sharpe", "max_drawdown", "excess_cagr", "beta", "trades",
                                          "avg_exposure", "costs_pct", "dividends", "volatility")}
        port_curves[label] = (r["times"], [e / r["equity"][0] for e in r["equity"]])
        bench_curve = m["benchmark_curve"]
    port["S&P 500 Total Return"] = {"cagr": metrics.summarise(run_backtest([bench], BuyHold, {}, Config(execution=execution.preset("zero"))))["cagr"]}
    res["portfolio"] = port

    # ---- 8: the worked example ----
    print("The worked example ...")
    ex = tester.walk_forward(experiment("sma", "MSFT", "walk_forward"))
    ex_bt = tester.backtest(experiment("sma", "MSFT"))
    pmap = tester.parameter_map(experiment("sma", "MSFT"))
    sample = [f for f in ex_bt["main"]["fills"]][:3]
    res["example"] = {"folds": ex["folds"], "metrics": ex["main"]["metrics"], "hold": ex["buy_hold"]["metrics"],
                      "efficiency": ex["efficiency"], "parameter_map": pmap, "sample_fills": sample}
    with open(os.path.join(OUT, "research_results.json"), "w", encoding="utf-8") as fh:
        json.dump(clean(res), fh, indent=1, default=str)

    draw_charts(res, ex, port_curves, bench_curve)
    print("\nSaved output/research_results.json and the charts.")


# ---------------- charts ----------------
def draw_charts(res, ex, port_curves, bench_curve):
    strat_names = list(res["backtest"])
    short = {n: n.replace("Moving average cross", "MA cross").replace("RSI mean reversion", "RSI reversion") for n in strat_names}

    # the engine, as a flow of boxes
    fig, ax = plt.subplots(figsize=(10, 2.6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 2.6); ax.axis("off")
    steps = [("Market data", "a bar closes"), ("Strategy", "signal, BUY"), ("Portfolio", "size, 10%"),
             ("Order", "BUY 20 shares"), ("Execution", "next open + costs"), ("Position", "20 shares held")]
    for i, (a, b) in enumerate(steps):
        x = 0.1 + i * 1.65
        ax.add_patch(FancyBboxPatch((x, 0.9), 1.35, 1.0, boxstyle="round,pad=0.04,rounding_size=0.12",
                                    fc=TEAL if i in (1, 4) else NAVY, ec="none"))
        ax.text(x + 0.675, 1.52, a, ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        ax.text(x + 0.675, 1.18, b, ha="center", va="center", color="#e8f1f2", fontsize=8)
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 1.62, 1.4), xytext=(x + 1.38, 1.4), arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.5))
    ax.text(5, 0.45, "The strategy only produces the signal. The portfolio sizes it, the execution model prices it.",
            ha="center", color="#444444", fontsize=9)
    fig.savefig(os.path.join(CHARTS, "engine_flow.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # backtest against walk-forward against buy and hold
    fig, ax = plt.subplots(figsize=(10, 4.2))
    xs = range(len(strat_names)); w = 0.27
    ax.bar([x - w for x in xs], [res["walk_forward"][n]["hindsight_cagr"] * 100 for n in strat_names], w, color=GREY, label="Best backtest with hindsight")
    ax.bar(list(xs), [res["walk_forward"][n]["cagr"] * 100 for n in strat_names], w, color=TEAL, label="Walk-forward (unseen years)")
    ax.bar([x + w for x in xs], [res["walk_forward"][n]["hold_cagr"] * 100 for n in strat_names], w, color=NAVY, label="Buy and hold, same years")
    ax.set_xticks(list(xs)); ax.set_xticklabels([short[n] for n in strat_names], fontsize=9)
    ax.set_ylabel("Return a year, %"); ax.axhline(0, color="#999999", lw=0.8)
    style(ax, "The same years three ways, average of twelve companies (Sep 2019 to Sep 2026)")
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    fig.savefig(os.path.join(CHARTS, "backtest_vs_walkforward.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # out-of-sample decay
    oos = res["out_of_sample"]; on = list(oos)
    fig, ax = plt.subplots(figsize=(10, 4))
    xs = range(len(on)); w = 0.36
    ax.bar([x - w / 2 for x in xs], [oos[n]["train_sharpe"] for n in on], w, color=GREY, label="Training years (settings chosen here)")
    ax.bar([x + w / 2 for x in xs], [oos[n]["test_sharpe"] for n in on], w, color=TEAL, label="Test years (never seen)")
    ax.set_xticks(list(xs)); ax.set_xticklabels([short[n] for n in on], fontsize=9); ax.set_ylabel("Sharpe ratio")
    style(ax, "What happens to the best settings on data they have not seen"); ax.legend(frameon=False, fontsize=9)
    fig.savefig(os.path.join(CHARTS, "out_of_sample.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # costs
    fig, ax = plt.subplots(figsize=(10, 4.2))
    colours = [NAVY, TEAL, RED, BLUE, GOLD, "#7d3c98", GREY]
    for n, c in zip(strat_names, colours):
        ys = [res["costs"][n][str(b)] * 100 for b in SLIPPAGE]
        ax.plot([b / 100 for b in SLIPPAGE], ys, marker="o", color=c, lw=2, label=short[n])
    ax.set_xlabel("Slippage per trade, %"); ax.set_ylabel("Return a year, %")
    style(ax, "How each rule copes as trading gets more expensive"); ax.legend(frameon=False, fontsize=8, ncol=4)
    fig.savefig(os.path.join(CHARTS, "cost_sensitivity.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # stress heatmap
    scen = list(res["scenarios"])
    grid = [[res["stress"][n][s]["return"] * 100 for s in scen] for n in strat_names]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    lim = max(abs(v) for row in grid for v in row)
    im = ax.imshow(grid, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(len(scen))); ax.set_xticklabels(scen, fontsize=9)
    ax.set_yticks(range(len(strat_names))); ax.set_yticklabels([short[n] for n in strat_names], fontsize=9)
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, f"{v:+.0f}%", ha="center", va="center", fontsize=8, color="#222222")
    ax.set_title("Stress tests, average return on each synthetic market (three runs)", loc="left", fontsize=12, color=NAVY, fontweight="bold", pad=10)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.savefig(os.path.join(CHARTS, "stress_heatmap.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # portfolios across the basket
    fig, ax = plt.subplots(figsize=(10, 4.2))
    for (label, (times, curve)), c in zip(port_curves.items(), [TEAL, BLUE, NAVY]):
        ax.plot(range(len(curve)), curve, color=c, lw=1.8, label=label)
    ax.plot(range(len(bench_curve)), [b / bench_curve[0] for b in bench_curve], color=GREY, lw=1.5, ls="--", label="S&P 500 Total Return")
    times = next(iter(port_curves.values()))[0]
    ticks = [i for i in range(1, len(times)) if times[i][:4] != times[i - 1][:4]]
    ax.set_xticks(ticks); ax.set_xticklabels([times[i][:4] for i in ticks], fontsize=8)
    ax.set_ylabel("Growth of 1"); style(ax, "One rule across all twelve companies at once"); ax.legend(frameon=False, fontsize=9)
    fig.savefig(os.path.join(CHARTS, "portfolio.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # the worked example, walk-forward on Microsoft
    m = ex["main"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(range(len(m["equity"])), [e / m["equity"][0] for e in m["equity"]], color=TEAL, lw=2, label="Moving average cross, walk-forward")
    hold = ex["buy_hold"]["equity"]
    ax.plot(range(len(hold)), [e / hold[0] for e in hold], color=NAVY, lw=1.5, label="Buy and hold Microsoft")
    if m.get("benchmark_curve"):
        bc = m["benchmark_curve"]
        ax.plot(range(len(bc)), [b / bc[0] for b in bc], color=GREY, lw=1.5, ls="--", label="S&P 500 Total Return")
    for f in ex["folds"]:
        i = m["times"].index(f["test"][0]) if f["test"][0] in m["times"] else None
        if i:
            ax.axvline(i, color="#dddddd", lw=0.8)
    t = m["times"]; ticks = [i for i in range(1, len(t)) if t[i][:4] != t[i - 1][:4]]
    ax.set_xticks(ticks); ax.set_xticklabels([t[i][:4] for i in ticks], fontsize=8)
    ax.set_ylabel("Growth of 1"); style(ax, "Walk-forward on Microsoft, settings re-chosen every year"); ax.legend(frameon=False, fontsize=9)
    fig.savefig(os.path.join(CHARTS, "walkforward_msft.png"), dpi=170, bbox_inches="tight"); plt.close(fig)

    # settings map for the example
    pm = res["example"]["parameter_map"]
    fasts = sorted({r["params"]["fast"] for r in pm}); slows = sorted({r["params"]["slow"] for r in pm})
    grid = [[next((r["sharpe"] for r in pm if r["params"]["fast"] == f and r["params"]["slow"] == s), float("nan")) for s in slows] for f in fasts]
    fig, ax = plt.subplots(figsize=(6, 3.8))
    im = ax.imshow(grid, cmap="YlGn", aspect="auto")
    ax.set_xticks(range(len(slows))); ax.set_xticklabels(slows); ax.set_xlabel("slow average")
    ax.set_yticks(range(len(fasts))); ax.set_yticklabels(fasts); ax.set_ylabel("fast average")
    for i, row in enumerate(grid):
        for j, v in enumerate(row):
            ax.text(j, i, "--" if v != v else f"{v:.2f}", ha="center", va="center", fontsize=9)
    ax.set_title("Sharpe for every setting, Microsoft, ten years", loc="left", fontsize=11, color=NAVY, fontweight="bold", pad=8)
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.savefig(os.path.join(CHARTS, "settings_map_msft.png"), dpi=170, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    main()
