"""
Run the whole study and write the results.

Takes every strategy, runs it across a basket of real companies, compares each to
its benchmark index, and stress tests it on synthetic markets. Prints a table,
saves the numbers to output/research_results.json, and draws two charts.

    python run_research.py

Coding done with the help of AI, because coding is not the author's strong area.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import feeds
import strategies as S
import tester

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "output")
CHARTS = os.path.join(ROOT, "charts")

BASKET = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "JPM", "WMT", "KO", "BA", "XOM", "JNJ"]
STRESS_SEEDS = [1, 2, 3]
NAVY, TEAL = "#1b2a4a", "#0f8b8d"


def mean(xs):
    xs = [x for x in xs if x == x]                  # drop NaNs
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(CHARTS, exist_ok=True)
    strats = [S.BuyHold(), S.SMACross(), S.Momentum(), S.MeanReversion(), S.Breakout(), S.BuyTheDip()]

    # 1. run every strategy across the basket of real companies
    print("Testing", len(strats), "strategies on", len(BASKET), "companies (10y daily)...\n")
    per_strategy = {}
    for st in strats:
        rets, cagrs, sharpes, dds, excess, wins = [], [], [], [], [], []
        for sym in BASKET:
            f = feeds.historical(sym)
            r = tester.backtest(f, st)
            m = r["metrics"]
            rets.append(m["total_return"]); cagrs.append(m["cagr"]); sharpes.append(m["sharpe"])
            dds.append(m["max_drawdown"]); wins.append(m["win_rate"])
            b = tester.benchmark_compare(f, r)
            if b:
                excess.append(b["excess_cagr"])
        per_strategy[st.name] = {"cagr": mean(cagrs), "sharpe": mean(sharpes),
                                 "max_drawdown": mean(dds), "excess_return": mean(excess),
                                 "win_rate": mean(wins), "total_return": mean(rets)}

    # 2. stress test, averaged over a few synthetic runs so one bad seed does not dominate
    print("Building synthetic markets for the stress test...\n")
    sims = {(sc, sd): feeds.simulated(sc, seed=sd) for sc in ("normal", "crash", "volatile") for sd in STRESS_SEEDS}
    stress = {}
    for st in strats:
        stress[st.name] = {}
        for sc in ("normal", "crash", "volatile"):
            rr = [tester.backtest(sims[(sc, sd)], st)["metrics"]["total_return"] for sd in STRESS_SEEDS]
            stress[st.name][sc] = mean(rr)

    # 3. print the comparison table
    print(f"{'Strategy':<26}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'vs bench':>10}{'Win':>6}   stress N/C/V")
    print("-" * 92)
    for st in strats:
        m = per_strategy[st.name]; sd = stress[st.name]
        print(f"{st.name:<26}{m['cagr']*100:>7.1f}%{m['sharpe']:>8.2f}{m['max_drawdown']*100:>7.1f}%"
              f"{m['excess_return']*100:>9.1f}%{m['win_rate']*100:>5.0f}%   "
              f"{sd['normal']*100:>+5.0f}/{sd['crash']*100:>+5.0f}/{sd['volatile']*100:>+5.0f}%")

    # 4. save the numbers
    with open(os.path.join(OUT, "research_results.json"), "w", encoding="utf-8") as fh:
        json.dump({"basket": BASKET, "per_strategy": per_strategy, "stress": stress}, fh, indent=1)

    # 5. chart A: every strategy on one company, versus buying and holding
    f = feeds.historical("MSFT")
    plt.figure(figsize=(9, 5))
    for st in strats:
        eq = tester.backtest(f, st)["equity"]
        plt.plot(range(len(eq)), [e / eq[0] for e in eq], label=st.name, linewidth=1.4)
    plt.title("Every strategy on Microsoft, 10 years (growth of £1)", color=NAVY)
    plt.legend(fontsize=8); plt.grid(alpha=0.2); plt.tight_layout()
    plt.savefig(os.path.join(CHARTS, "strategies_on_msft.png"), dpi=150)
    plt.close()

    # 6. chart B: average excess return over the benchmark, per strategy
    names = [st.name for st in strats]
    ex = [per_strategy[n]["excess_return"] * 100 for n in names]
    plt.figure(figsize=(9, 5))
    plt.bar(names, ex, color=[TEAL if v >= 0 else "#ef5350" for v in ex])
    plt.axhline(0, color="#333", linewidth=0.8)
    plt.title("Average return versus the benchmark index, across the basket", color=NAVY)
    plt.ylabel("excess return, percentage points")
    plt.xticks(rotation=20, ha="right", fontsize=8); plt.grid(axis="y", alpha=0.2); plt.tight_layout()
    plt.savefig(os.path.join(CHARTS, "excess_return.png"), dpi=150)
    plt.close()

    print("\nSaved output/research_results.json and two charts in charts/.")


if __name__ == "__main__":
    main()
