"""
Run Agora and build the dashboard.

This runs four versions of the market (four "scenarios"), prints a short report
for each, saves the raw numbers to output/simulation.json, and drops them into the
dashboard page (Agora Dashboard.html in the folder above).

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
TEMPLATE = os.path.join(HERE, "dashboard_template.html")
OUT_JSON = os.path.join(ROOT, "output", "simulation.json")
OUT_HTML = os.path.join(ROOT, "Agora Dashboard.html")


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

    # real market prices, if they have been downloaded (run fetch_markets.py)
    real_path = os.path.join(ROOT, "output", "real_markets.json")
    if os.path.exists(real_path):
        with open(real_path, encoding="utf-8") as fh:
            real = json.load(fh)
        print(f"\nUsing {len(real['instruments'])} real markets from {real['fetched']}")
    else:
        real = {"fetched": "not downloaded", "usd_to_gbp": 0.79, "instruments": []}
        print("\nNo real market data found (run: python fetch_markets.py)")

    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("__SIM_DATA__", json.dumps(data)).replace("__REAL_DATA__", json.dumps(real))
    for out in (OUT_HTML, os.path.join(ROOT, "index.html")):   # index.html is what GitHub Pages serves
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)

    print(f"Saved {OUT_JSON}")
    print(f"Saved {OUT_HTML}  (open it in a browser)")


if __name__ == "__main__":
    main()
