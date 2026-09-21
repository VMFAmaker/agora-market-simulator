"""
Run the full Agora agent model and print a report.

This runs four versions of the market (four "scenarios"), prints a short report
for each, and saves the raw numbers to output/simulation.json. It is for studying
the agent model. The website page is built separately by build_page.py.

    python run_simulation.py
    python run_simulation.py 7      # use a different random seed

Coding done with the help of AI, because coding is not my strong area.
"""

import json
import os
import sys

from agora import Simulation, Config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_JSON = os.path.join(ROOT, "output", "simulation.json")


def report(name, result):
    s, f = result["summary"], result["facts"]
    print(f"\n[{name}]")
    print("  price {init} -> {final} ({pct:+.1f}%)   low {low}  high {high}"
          "   worst drop {max_drawdown}%".format(**s))
    print(f"  trades {s['n_trades']:,}   forced sales {s['n_liquidations']}   halts {s['n_halts']}")
    print(f"  looks like a real market?  fat tails {f['kurtosis']} "
          f"({'yes' if f['pass_fat_tails'] else 'no'}),   "
          f"clustering {f['vol_clustering']} ({'yes' if f['pass_vol_clustering'] else 'no'})")


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    print(f"Running Agora with seed {seed} ...")

    # each scenario is just a Config with a few settings changed
    scenarios = {
        "baseline": Config(seed=seed),
        "stress": Config(seed=seed, n_leveraged=16, shock_time=1500.0, shock_size=-0.10),
        "breaker": Config(seed=seed, shock_time=1500.0, shock_size=-0.22, breaker_pct=0.13),
        "full": Config(seed=seed, n_meanrev=8, n_breakout=8, n_news=8, n_whale=4, n_panic=7),
    }
    names = {"baseline": "normal market", "stress": "leverage crash",
             "breaker": "crash with circuit breaker", "full": "full market"}

    results = {}
    for key, cfg in scenarios.items():
        results[key] = Simulation(cfg).run()
        report(names[key], results[key])

    data = {"scenarios": results, "default": "baseline"}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh)

    print(f"\nSaved {OUT_JSON}")
    print("To build the website page, run: python build_page.py")


if __name__ == "__main__":
    main()
